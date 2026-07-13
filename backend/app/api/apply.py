"""
PlaceUp Career — Automated Application API.

Endpoints (all require a valid JWT except the internal SES webhook, which is
service-authenticated):

    POST   /api/apply                  start preparing an application (Apply btn)
    GET    /api/apply                  tracker list (kanban board)
    GET    /api/apply/{id}             review payload + tailoring diff
    POST   /api/apply/{id}/approve     the human gate -> enqueue submission
    POST   /api/apply/{id}/cancel      user declines
    PATCH  /api/apply/{id}/status      move a card on the tracker
    GET    /api/apply/profile          reusable ATS answers
    PUT    /api/apply/profile          save reusable ATS answers
    GET    /api/apply/inbox            captured dedicated-inbox messages
    POST   /api/apply/inbox/webhook    SES->Lambda ingestion (service token)

The review-before-submit gate is enforced server-side: `approve` requires
`confirm=true` and only transitions from NEEDS_REVIEW. Submission never runs
inline — it is enqueued on the per-ATS Cloud Tasks queue.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Body, Depends, HTTPException, Request, status

from app.models.application import (
    ApplicationProfile,
    ApplicationStatus,
    ApplyRequest,
    ReviewDecision,
    USER_SETTABLE_STATUSES,
)
from app.security import current_user_id
from app.config import settings
from app.services.apply import apply_queue
from app.services.apply.inbox_ingest import link_to_application, parse_webhook
from app.services.apply.orchestrator import approve_application, prepare_application
from app.services.apply.tailoring_pipeline import run_tailoring

log = logging.getLogger("placeup.apply")


def _apply_enabled() -> None:
    if not settings.apply_feature_enabled:
        raise HTTPException(status_code=503, detail="Application preparation is temporarily unavailable")


router = APIRouter(prefix="/apply", tags=["Apply"], dependencies=[Depends(_apply_enabled)])

_SENSITIVE_PROFILE_KEYS = ("gender", "race", "ethnicity", "veteran", "disability", "ssn", "date_of_birth", "dob")


def _assert_profile_minimized(profile: ApplicationProfile) -> None:
    """Phase 0 data-minimization boundary.

    Voluntary EEO/identity answers are intentionally not persisted until the
    Cloud KMS envelope-encryption layer is configured. Users provide them at
    review time instead, preserving the PDF's least-credential/least-PII rule.
    """
    sensitive_custom = [
        key for key in profile.custom_answers
        if any(token in key.lower() for token in _SENSITIVE_PROFILE_KEYS)
    ]
    if profile.eeo or sensitive_custom:
        raise HTTPException(
            status_code=400,
            detail="Voluntary EEO or identity answers are not stored. Enter them during review.",
        )


def _store():
    # Instantiated per request; cheap (reuses the shared Firestore client).
    from app.db.firestore_apply_store import FirestoreApplyStore

    return FirestoreApplyStore()


@router.post("")
async def start_application(
    payload: ApplyRequest = Body(...),
    uid: str = Depends(current_user_id),
):
    """User clicked Apply. Resolves tier, runs tailoring, prepares the payload
    or fills the browser form, and returns the application in NEEDS_REVIEW."""
    store = _store()

    async def _tailor(**kw):
        return await run_tailoring(store=store, **kw)

    try:
        app = await prepare_application(
            store=store,
            uid=uid,
            job_id=payload.job_id,
            resume_id=payload.resume_id,
            generate_cover_letter=payload.generate_cover_letter,
            notes=payload.notes,
            tailor_fn=_tailor,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - defensive
        log.exception("prepare_application failed")
        raise HTTPException(status_code=500, detail="Could not prepare application") from exc
    return app


@router.get("")
async def list_applications(uid: str = Depends(current_user_id)):
    return _store().list_applications(uid)


@router.get("/profile")
async def get_profile(uid: str = Depends(current_user_id)):
    return _store().get_application_profile(uid) or {"uid": uid}


@router.put("/profile")
async def save_profile(
    payload: ApplicationProfile = Body(...),
    uid: str = Depends(current_user_id),
):
    _assert_profile_minimized(payload)
    data = payload.model_dump(mode="json")
    data["uid"] = uid
    return _store().save_application_profile(uid, data)


@router.get("/inbox")
async def list_inbox(uid: str = Depends(current_user_id)):
    return _store().list_inbox(uid)


@router.get("/{app_id}")
async def get_application(app_id: str, uid: str = Depends(current_user_id)):
    app = _store().get_application(app_id)
    if not app or app.get("uid") != uid:
        raise HTTPException(status_code=404, detail="Application not found")
    return app


@router.post("/{app_id}/approve")
async def approve(
    app_id: str,
    decision: ReviewDecision = Body(...),
    uid: str = Depends(current_user_id),
):
    """The non-optional human gate. Requires confirm=true."""
    store = _store()
    try:
        app = await approve_application(
            store=store,
            uid=uid,
            app_id=app_id,
            confirm=decision.confirm,
            answers=decision.answers,
            enqueue_fn=apply_queue.enqueue_application,
        )
    except PermissionError:
        raise HTTPException(status_code=404, detail="Application not found")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return app


@router.post("/{app_id}/cancel")
async def cancel(app_id: str, uid: str = Depends(current_user_id)):
    store = _store()
    app = store.get_application(app_id)
    if not app or app.get("uid") != uid:
        raise HTTPException(status_code=404, detail="Application not found")
    return store.update_status(uid, app_id, ApplicationStatus.SKIPPED.value)


@router.patch("/{app_id}/status")
async def set_status(
    app_id: str,
    body: dict = Body(...),
    uid: str = Depends(current_user_id),
):
    """Move a card on the tracker. Only user-settable statuses allowed."""
    new_status = str(body.get("status") or "").strip()
    allowed = {s.value for s in USER_SETTABLE_STATUSES}
    if new_status not in allowed:
        raise HTTPException(status_code=400, detail=f"status must be one of {sorted(allowed)}")
    updated = _store().update_status(uid, app_id, new_status)
    if not updated:
        raise HTTPException(status_code=404, detail="Application not found")
    return updated


@router.post("/inbox/webhook")
async def inbox_webhook(request: Request, body: dict = Body(...)):
    """SES -> Lambda -> here. Service-authenticated: the ServiceOnlyGate /
    internal API key protects it; reject anonymous callers."""
    from app.config import settings

    provided = request.headers.get("X-Internal-Api-Key") or ""
    if not settings.internal_api_key or provided != settings.internal_api_key:
        raise HTTPException(status_code=403, detail="forbidden")

    store = _store()
    msg = parse_webhook(body, resolve_uid=store.resolve_uid_from_local)
    if msg is None:
        return {"stored": False, "reason": "unrecognized recipient"}
    apps = store.list_applications(msg.uid)
    msg.app_id = link_to_application(msg, apps)
    saved = store.save_inbox_message(msg.model_dump(mode="json"))
    return {"stored": True, "classification": saved.get("classification"), "linked_app": saved.get("app_id")}

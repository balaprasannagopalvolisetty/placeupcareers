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
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Body, Depends, HTTPException, Query

from app.models.application import (
    ApplicationProfile,
    ApplicationStatus,
    ApplyRequest,
    ReviewDecision,
    USER_SETTABLE_STATUSES,
)
from app.security import current_user_id, require_internal_api_key
from app.config import settings
from app.dependencies import get_db
from app.services.apply import apply_queue
from app.services.apply.inbox_ingest import link_to_application, parse_webhook
from app.services.apply.orchestrator import approve_application, prepare_application
from app.services.apply.tailoring_pipeline import run_tailoring
from app.services.apply.tiers import (
    API_SUBMITTABLE_ATS,
    infer_ats_type,
    is_one_click_ready,
    parse_credentialed,
    tier_for_ats,
)
from app.scrape_constants import FIRST_PARTY_ATS_SOURCES

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


@router.post("/render")
async def render_documents(body: dict = Body(...), uid: str = Depends(current_user_id)):
    """Render a resume spec (+ optional cover letter) to ATS-safe DOCX/PDF for
    the Resume Studio editor's live preview and manual download. Stateless —
    it does not persist; the per-position auto-render happens in the apply
    pipeline. Returns base64 payloads keyed like `resume_pdf`, `resume_docx`,
    `cover_letter_pdf`, `cover_letter_docx`."""
    import base64
    from app.services.apply.resume_renderer import render_all

    resume = body.get("resume") if isinstance(body.get("resume"), dict) else None
    if not resume:
        raise HTTPException(status_code=400, detail="resume spec required")
    cover = body.get("cover_letter")
    cover = cover if isinstance(cover, str) and cover.strip() else None
    try:
        files = render_all(resume, cover)
    except Exception as exc:  # pragma: no cover - defensive
        log.warning("render_documents failed: %s", exc)
        raise HTTPException(status_code=500, detail="Could not render documents")
    return {name.replace(".", "_"): base64.b64encode(data).decode("ascii") for name, data in files.items()}


@router.get("/one-click")
async def one_click_feed(
    limit: int | None = Query(None, ge=1, le=200, description="Legacy page-size alias"),
    page: int = Query(1, ge=1),
    page_size: int = Query(40, ge=1, le=100),
    ready_only: bool = Query(False, description="Only jobs submittable right now"),
    uid: str = Depends(current_user_id),
    db=Depends(get_db),
):
    """Personalized direct-ATS feed for the One-Click Apply tab.

    Every direct ATS role can be opened and tailored. Each job is separately
    flagged `one_click_ready` when PlaceUp can submit it through an approved
    candidate API; all other ATS roles remain available for Prepare + Review.

    Query direct ATS sources at the database boundary. The previous
    implementation fetched a small slice of the entire global inventory and
    filtered ATS types afterwards. High-volume aggregator rows could fill that
    slice (or make it exceed the statement timeout), leaving this page empty
    even while eligible ATS rows existed in the database.
    """
    from app.api.jobs import (
        _active_resume_text,
        _baseline_ats_score,
        _cached_score_job_against_resume,
        _job_effective_datetime,
        _job_matches_role_terms,
        _preference_terms,
        _prepare_resume_tokens,
        _terms_for_role_names,
    )
    from app.services.global_visa_rules import normalize_country_code, resolve_country

    credentialed = parse_credentialed(settings.apply_credentialed_ats)
    preferred_roles, preferred_locations = _preference_terms(uid)
    role_terms = _terms_for_role_names(preferred_roles) if preferred_roles else []
    target_country = None
    for preferred_location in preferred_locations:
        target_country = normalize_country_code(resolve_country(preferred_location))
        if target_country:
            break

    # One-Click is an active direct-ATS inventory, not the Jobs page's strict
    # "posted today" view. A 30-day honest window supplies enough direct ATS
    # roles for saved-role matching while every card still displays its real
    # posting date. The main Jobs page remains last-24-hours by default.
    window_days = 30
    effective_page_size = limit or page_size
    filters = {
        "status": "active",
        "complete_jd_only": True,
        # ATS refreshes fan out over hundreds of boards and do not all finish
        # inside the same 24-hour slice. Seven days is the verification SLA;
        # `honest_since` below still prevents old posting dates being relabelled.
        "seen_since": datetime.now(timezone.utc) - timedelta(days=7),
        "honest_since": datetime.now(timezone.utc) - timedelta(days=window_days),
        "sources": sorted(FIRST_PARTY_ATS_SOURCES),
    }
    if target_country:
        filters["country"] = target_country
    if role_terms:
        filters["title_terms"] = role_terms

    try:
        rows = await db.get_jobs(
            filters=filters,
            limit=max(effective_page_size * 10, 600),
            offset=0,
        )
    except Exception as exc:  # pragma: no cover - defensive
        log.warning("one_click_feed jobs query failed: %s", exc)
        rows = []

    candidates: list[dict] = []
    for row in rows:
        resolved_job_country = normalize_country_code(resolve_country(
            f"{row.get('location') or ''} {row.get('title') or ''}"
        ))
        if target_country and resolved_job_country and resolved_job_country != target_country:
            continue
        ats = infer_ats_type(row) or str(row.get("source") or row.get("source_name") or "ats").strip().lower()
        if preferred_roles and not _job_matches_role_terms(row, preferred_roles, role_terms):
            continue
        ready = settings.apply_live_submit_enabled and is_one_click_ready(ats, credentialed)
        if ready_only and not ready:
            continue
        row = dict(row)
        row["ats_type"] = ats
        row["one_click_ready"] = ready
        candidates.append(row)

    # Hydrate the already-small, role-filtered ATS pool in one indexed query.
    # The scoring excerpt is large enough to include responsibilities and
    # requirements while avoiding repeated NLP passes over long legal/benefits
    # boilerplate. The complete JD remains stored and is fetched by job detail
    # and Prepare; this endpoint never truncates the source record itself.
    try:
        get_descriptions = getattr(db, "get_job_descriptions", None)
        descriptions = (
            await get_descriptions([str(row.get("id") or "") for row in candidates])
            if get_descriptions else {}
        )
        for row in candidates:
            full = descriptions.get(str(row.get("id") or "")) or ""
            if full:
                row["description"] = full[:4000]
    except Exception as exc:  # pragma: no cover - production DB fallback
        log.debug("one_click full-JD hydration skipped: %s", exc)

    resume_text = await _active_resume_text(uid)
    resume_cache = _prepare_resume_tokens(resume_text) if resume_text else None
    for row in candidates:
        title = str(row.get("title") or "")
        description = str(row.get("description") or "")
        if resume_text:
            score = _cached_score_job_against_resume(
                resume_text,
                f"{title}\n{description}",
                resume_cache=resume_cache,
                job_id=str(row.get("id") or ""),
            )
            row["match_score"] = score or _baseline_ats_score(row)
            row["score_type"] = "resume_match" if score else "baseline_ats"
        else:
            row["match_score"] = _baseline_ats_score(row)
            row["score_type"] = "baseline_ats"

    candidates.sort(key=lambda row: (
        -int(row.get("match_score") or 0),
        -(_job_effective_datetime(row).timestamp() if _job_effective_datetime(row) else 0),
        str(row.get("id") or ""),
    ))

    total = len(candidates)
    ready_total = sum(1 for row in candidates if row.get("one_click_ready"))
    total_pages = max(1, (total + effective_page_size - 1) // effective_page_size)
    safe_page = min(page, total_pages)
    start = (safe_page - 1) * effective_page_size
    page_rows = candidates[start:start + effective_page_size]

    jobs: list[dict] = []
    for row in page_rows:
        ats = str(row.get("ats_type") or "")
        info = tier_for_ats(ats)
        jobs.append({
            "job_id": str(row.get("id") or row.get("job_id") or ""),
            "title": row.get("title") or "",
            "company": row.get("company") or "",
            "location": row.get("location") or "",
            "job_url": row.get("job_url") or row.get("source_url") or row.get("url") or "",
            "ats_type": ats,
            "match_score": int(row.get("match_score") or 0),
            "score_type": row.get("score_type") or "baseline_ats",
            "one_click_ready": bool(row.get("one_click_ready")),
            "intake_method": getattr(info, "intake_method", "") if info else "",
            "posted_at": row.get("posted_at") or row.get("first_seen_at"),
            "source": row.get("source") or row.get("source_name") or ats,
        })

    return {
        "jobs": jobs,
        "total": total,
        "ready_total": ready_total,
        "page": safe_page,
        "page_size": effective_page_size,
        "total_pages": total_pages,
        "window_days": window_days,
        "target_roles": preferred_roles,
        "target_country": target_country,
        "credentialed_ats": sorted(credentialed),
        "direct_ats_sources": sorted(FIRST_PARTY_ATS_SOURCES),
        "api_submittable_ats": sorted(API_SUBMITTABLE_ATS),
        "live_submit_enabled": settings.apply_live_submit_enabled,
    }


@router.get("/{app_id}")
async def get_application(app_id: str, uid: str = Depends(current_user_id)):
    app = _store().get_application(app_id)
    if not app or app.get("uid") != uid:
        raise HTTPException(status_code=404, detail="Application not found")
    return app


_DOC_KINDS = {
    "resume_url", "resume_pdf_url", "resume_docx_url",
    "cover_letter_url", "cover_letter_pdf_url", "cover_letter_docx_url",
}


@router.get("/{app_id}/document/{kind}")
async def get_application_document(app_id: str, kind: str, uid: str = Depends(current_user_id)):
    """Stream a stored tailored document (resume/cover letter, PDF/DOCX) for the
    owning user. Keeps the Cloud Storage bucket private — the file is fetched
    server-side after an ownership check rather than exposed via a public URL."""
    from fastapi import Response
    from app.services.apply import doc_storage

    if kind not in _DOC_KINDS:
        raise HTTPException(status_code=400, detail=f"kind must be one of {sorted(_DOC_KINDS)}")
    app = _store().get_application(app_id)
    if not app or app.get("uid") != uid:
        raise HTTPException(status_code=404, detail="Application not found")
    docs = app.get("tailored_documents") or {}
    uri = docs.get(kind) or app.get("tailored_resume_url" if kind.startswith("resume") else "tailored_cover_letter_url")
    if not uri:
        raise HTTPException(status_code=404, detail="Document not available")
    data = doc_storage.read_document(uri)
    if data is None:
        raise HTTPException(status_code=404, detail="Document not available")
    filename = kind.replace("_url", "").replace("_", "-") + (".pdf" if "docx" not in kind else ".docx")
    return Response(
        content=data,
        media_type=doc_storage.content_type_for(uri),
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


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
async def inbox_webhook(
    body: dict = Body(...),
    _: None = Depends(require_internal_api_key),
):
    """SES -> Lambda -> here. Service-authenticated: the ServiceOnlyGate /
    internal API key protects it; reject anonymous callers."""
    store = _store()
    msg = parse_webhook(body, resolve_uid=store.resolve_uid_from_local)
    if msg is None:
        return {"stored": False, "reason": "unrecognized recipient"}
    apps = store.list_applications(msg.uid)
    msg.app_id = link_to_application(msg, apps)
    saved = store.save_inbox_message(msg.model_dump(mode="json"))
    return {"stored": True, "classification": saved.get("classification"), "linked_app": saved.get("app_id")}


@router.post("/internal-submit")
async def internal_submit(
    body: dict = Body(...),
    _: None = Depends(require_internal_api_key),
):
    """Cloud Tasks push target (APPLY_QUEUE_BACKEND=cloudtasks): run the queued
    submission for one application. Internal-key protected — Cloud Tasks adds the
    X-API-Key header when the task is created; the zero-trust middleware and
    route dependency both verify it before any application state is read."""
    app_id = str(body.get("app_id") or "").strip()
    if not app_id:
        raise HTTPException(status_code=400, detail="app_id required")
    from app.services.apply.orchestrator import _run_submit

    result = await _run_submit(_store(), app_id)
    return {"app_id": app_id, "status": (result or {}).get("status"), "confirmation_ref": (result or {}).get("confirmation_ref")}

"""
Apply orchestration — the brain of the automated application system.

Flow (matches doc sections B1 + J, "Review-Before-Submit & Graceful Handoff"):

    prepare_application()   user clicks Apply
        -> resolve ATS tier from the job
        -> run the tailoring pipeline (JD signals -> tailored resume + cover)
        -> Tier A: build the API payload; Tier C: fill the browser form to the
           submit button
        -> status = NEEDS_REVIEW (the non-optional human gate)

    approve_application()   user reviews the exact payload + diff, edits, approves
        -> Tier A -> enqueue API submit on the per-ATS queue
        -> Tier C -> enqueue browser submit
        -> a CAPTCHA/OTP/bot-check flips status to NEEDS_YOU for live handoff

Nothing is ever submitted without `approve_application` and an explicit
`confirm=true`. The orchestrator is deliberately storage-agnostic: it takes a
store object so it is testable without Firestore.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional, Protocol

from app.models.application import (
    Application,
    ApplicationEvent,
    ApplicationStatus,
    ATSTier,
    SubmissionMethod,
)
from app.services.apply.base import get_adapter
from app.services.apply.browser_worker import BrowserApplyWorker, HandoffTrigger
from app.services.apply.tiers import infer_ats_type, is_api_submittable, resolve_tier, tier_for_ats

log = logging.getLogger("placeup.apply")


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


class ApplyStore(Protocol):
    """Minimal persistence surface the orchestrator needs."""

    def get_application(self, app_id: str) -> Optional[dict]: ...
    def save_application(self, app: dict) -> dict: ...
    def get_job(self, job_id: str) -> Optional[dict]: ...
    def get_profile(self, uid: str) -> dict: ...


def _event(app: dict, kind: str, detail: str = "", status: Optional[ApplicationStatus] = None) -> None:
    app.setdefault("history", []).append(
        ApplicationEvent(kind=kind, detail=detail, status=status).model_dump(mode="json")
    )
    app["last_event_at"] = _now().isoformat()
    app["updated_at"] = _now().isoformat()
    if status is not None:
        app["status"] = status.value


async def prepare_application(
    store: ApplyStore,
    uid: str,
    job_id: str,
    resume_id: Optional[str],
    generate_cover_letter: bool,
    notes: str,
    tailor_fn,
) -> dict:
    """Create an application in NEEDS_REVIEW. `tailor_fn` is the tailoring
    pipeline entry point (injected for testability): it returns a dict with
    resume_url / cover_letter_url / match_score / ats_score / jd_signals / diff.
    """
    job = store.get_job(job_id) or {}
    if not job:
        raise ValueError("job not found or unavailable")
    profile = store.get_profile(uid) or {}
    ats_type = infer_ats_type(job)
    info = tier_for_ats(ats_type)
    tier = resolve_tier(ats_type)

    app = Application(
        uid=uid,
        job_id=job_id,
        title=job.get("title") or "",
        company=job.get("company") or "",
        location=job.get("location") or "",
        job_url=job.get("job_url") or job.get("source_url") or job.get("url") or "",
        ats_type=ats_type,
        tier=tier,
        status=ApplicationStatus.PREPARING,
        notes=notes,
    ).model_dump(mode="json")
    _event(app, "created", f"tier={tier.value} ats={ats_type or 'unknown'}")

    # --- tailoring pipeline ---
    try:
        tailored = await tailor_fn(
            uid=uid, job=job, profile=profile, resume_id=resume_id,
            generate_cover_letter=generate_cover_letter,
        )
    except Exception as exc:  # never block the whole apply on tailoring
        log.warning("tailoring failed for job %s: %s", job_id, exc)
        tailored = {}
    app["tailored_resume_url"] = tailored.get("resume_url")
    app["tailored_cover_letter_url"] = tailored.get("cover_letter_url")
    app["tailored_documents"] = tailored.get("documents") or {}
    app["match_score"] = int(tailored.get("match_score") or job.get("match_score") or 0)
    app["ats_score"] = int(tailored.get("ats_score") or 0)
    if tailored:
        _event(app, "tailored", f"match={app['match_score']} ats={app['ats_score']}")

    answers = dict((profile.get("custom_answers") or {}))

    # --- Tier A: build the API payload for review ---
    if is_api_submittable(ats_type):
        adapter = get_adapter(ats_type)
        payload = adapter.build_payload(
            job=job, profile=profile, answers=answers,
            resume_url=app["tailored_resume_url"],
            cover_letter_url=app["tailored_cover_letter_url"],
        )
        if tailored.get("cover_letter"):
            payload.fields["cover_letter"] = tailored["cover_letter"]
        problems = adapter.validate(payload)
        app["submission_method"] = SubmissionMethod.API.value
        app["prepared_payload"] = {
            "endpoint": payload.endpoint,
            "fields": payload.fields,
            "attachments": payload.attachments,
            "eeo_fields": payload.eeo_fields,
            "missing_required": payload.missing_required,
            "notes": payload.notes,
        }
        _event(
            app, "prepared_api",
            "; ".join(problems) if problems else "payload built",
            status=ApplicationStatus.NEEDS_REVIEW,
        )
    else:
        # --- Tier B/C: browser fills the form up to the submit button ---
        app["submission_method"] = SubmissionMethod.BROWSER.value
        worker = BrowserApplyWorker()
        result = await worker.prepare(
            job_url=app["job_url"], adapter_config={}, payload={"profile": profile, "answers": answers},
        )
        app["prepared_payload"] = {"note": result.message}
        app["confirmation_screenshot_url"] = result.screenshot_url
        if result.status is ApplicationStatus.NEEDS_YOU:
            app["needs_you_reason"] = result.handoff.value
            _event(app, "handoff_required", result.message, status=ApplicationStatus.NEEDS_YOU)
        else:
            _event(app, "prepared_browser", result.message, status=ApplicationStatus.NEEDS_REVIEW)

    return store.save_application(app)


async def approve_application(
    store: ApplyStore,
    uid: str,
    app_id: str,
    confirm: bool,
    answers: dict[str, str],
    enqueue_fn,
) -> dict:
    """The human gate. Requires confirm=true. Enqueues the actual submission.

    `enqueue_fn(app_id, ats_type, coro_factory)` is the queue entry point
    (injected). The coroutine factory performs the tier-appropriate submit.
    """
    app = store.get_application(app_id)
    if not app or app.get("uid") != uid:
        raise PermissionError("application not found")
    if not confirm:
        raise ValueError("approval requires explicit confirmation")
    if app.get("status") not in (ApplicationStatus.NEEDS_REVIEW.value,):
        raise ValueError(f"cannot approve from status {app.get('status')}")

    # Merge user edits over the prepared fields.
    if answers:
        app.setdefault("prepared_payload", {}).setdefault("fields", {}).update(answers)
    _event(app, "approved", status=ApplicationStatus.QUEUED)
    # Persist the reviewed fields and QUEUED state before creating Cloud Tasks.
    # A task can dispatch immediately; saving afterward risks submitting the
    # stale, pre-review payload.
    store.save_application(app)

    ats_type = app.get("ats_type") or ""

    async def _do_submit():
        await _run_submit(store, app_id)

    try:
        await enqueue_fn(app_id, ats_type, _do_submit)
    except Exception as exc:
        app["error"] = f"Could not queue submission: {exc}"
        _event(app, "queue_failed", app["error"], status=ApplicationStatus.FAILED)
        return store.save_application(app)
    return store.save_application(app)


async def _run_submit(store: ApplyStore, app_id: str) -> dict:
    """Executed off the queue. Performs the tier-appropriate submission and
    records the terminal (or handoff) state. Idempotent on APPLIED."""
    app = store.get_application(app_id)
    if not app:
        return {}
    if app.get("status") == ApplicationStatus.APPLIED.value:
        return app  # idempotency: already submitted

    _event(app, "submit_started", status=ApplicationStatus.IN_FLIGHT)
    store.save_application(app)

    method = app.get("submission_method")
    try:
        if method == SubmissionMethod.API.value:
            adapter = get_adapter(app.get("ats_type"))
            from app.services.apply.base import PreparedPayload

            pp = PreparedPayload(
                ats_type=app.get("ats_type") or "",
                endpoint=(app.get("prepared_payload") or {}).get("endpoint", ""),
                fields=(app.get("prepared_payload") or {}).get("fields", {}),
                attachments=(app.get("prepared_payload") or {}).get("attachments", {}),
            )
            result = await adapter.submit(pp)
            if result.dry_run:
                app["confirmation_ref"] = result.confirmation_ref or "DRYRUN"
                _event(app, "dry_run_complete", result.message, status=ApplicationStatus.NEEDS_REVIEW)
            elif result.ok:
                app["confirmation_ref"] = result.confirmation_ref
                app["submitted_at"] = _now().isoformat()
                _event(app, "submitted_api", result.message, status=ApplicationStatus.APPLIED)
            elif result.needs_you:
                app["needs_you_reason"] = result.needs_you_reason
                _event(app, "handoff_required", result.message, status=ApplicationStatus.NEEDS_YOU)
            else:
                app["error"] = result.message
                _event(app, "submit_failed", result.message, status=ApplicationStatus.FAILED)
        else:
            worker = BrowserApplyWorker()
            result = await worker.submit(app.get("job_url", ""), adapter_config={}, payload={})
            app["confirmation_screenshot_url"] = result.screenshot_url
            if result.status is ApplicationStatus.APPLIED:
                app["confirmation_ref"] = result.confirmation_ref
                app["submitted_at"] = _now().isoformat()
                _event(app, "submitted_browser", result.message, status=ApplicationStatus.APPLIED)
            elif result.status is ApplicationStatus.NEEDS_YOU:
                app["needs_you_reason"] = result.handoff.value
                _event(app, "handoff_required", result.message, status=ApplicationStatus.NEEDS_YOU)
            else:
                _event(app, "submit_failed", result.message, status=ApplicationStatus.FAILED)
    except NotImplementedError as exc:
        app["error"] = str(exc)
        _event(app, "submit_unavailable", str(exc), status=ApplicationStatus.NEEDS_YOU)
        app["needs_you_reason"] = "manual"
    except Exception as exc:  # pragma: no cover - defensive
        app["error"] = str(exc)
        _event(app, "submit_error", str(exc), status=ApplicationStatus.FAILED)

    return store.save_application(app)

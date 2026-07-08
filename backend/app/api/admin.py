"""Private admin API for operations staff.

Routes require a signed-in user whose email is allowlisted in ADMIN_EMAILS or
whose stored plan is "Admin". The frontend route is intentionally hidden from
normal navigation, but backend authorization is the real protection.
"""
from __future__ import annotations

import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from pydantic import BaseModel

from app.config import settings
from app.db import user_store
from app.db import feedback_store
from app.security import current_user_id
from app.services.global_visa_rules import country_options

router = APIRouter(prefix="/admin", tags=["Admin"])


def _admin_email_set() -> set[str]:
    return {email.strip().lower() for email in settings.admin_emails.split(",") if email.strip()}


async def require_admin_user(user_id: str = Depends(current_user_id)) -> dict:
    user = user_store.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    email = str(user.get("email") or "").lower()
    # SECURITY: admin access is granted ONLY by the ADMIN_EMAILS allowlist.
    # The old `plan == "admin"` shortcut was reachable through the
    # user-writable profile update, making it a privilege-escalation path.
    if email in _admin_email_set():
        return user
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")


@router.get("/summary")
async def admin_summary(_: dict = Depends(require_admin_user)):
    users = user_store.list_users(limit=1000)
    plan_counts: dict[str, int] = {}
    for user in users:
        plan = str(user.get("plan") or "Unknown")
        plan_counts[plan] = plan_counts.get(plan, 0) + 1
    return {
        "users": len(users),
        "plans": plan_counts,
        "payments": {
            "configured": True if settings.free_access_enabled else bool(
                settings.payment_basic_checkout_url
                and settings.payment_pro_checkout_url
                and settings.payment_elite_checkout_url
            ),
            "provider": "free_access" if settings.free_access_enabled else "hosted_checkout",
        },
        "finalscout": {
            "multi_key_configured": bool(settings.finalscout_api_keys or settings.finalscout_api_key),
        },
    }


@router.get("/users")
async def admin_users(
    limit: int = Query(default=200, ge=1, le=1000),
    _: dict = Depends(require_admin_user),
):
    rows = user_store.list_users(limit=limit)
    return {
        "users": [
            {
                "id": row.get("id"),
                "email": row.get("email"),
                "first_name": row.get("first_name"),
                "last_name": row.get("last_name"),
                "plan": row.get("plan") or "Pro",
                "visa_status": row.get("visa_status"),
                "created_at": row.get("created_at"),
                "updated_at": row.get("updated_at"),
            }
            for row in rows
        ]
    }


@router.get("/payments")
async def admin_payments(_: dict = Depends(require_admin_user)):
    return {
        "payments": [],
        "note": (
            "Plan catalog is live; checkout is not required during launch preview."
            if settings.free_access_enabled
            else "Payment provider webhooks are not connected yet; hosted checkout links are configured via environment variables."
        ),
    }


@router.post("/finalscout/upload-csv")
async def admin_finalscout_csv(
    file: UploadFile = File(...),
    limit: int = Query(default=200, ge=1, le=2000),
    dry_run: bool = Query(default=False),
    concurrency: int = Query(default=4, ge=1, le=8),
    _: dict = Depends(require_admin_user),
):
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Upload a CSV file")

    contents = await file.read()
    if len(contents) > 5 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="CSV must be 5 MB or smaller")

    with tempfile.NamedTemporaryFile(delete=False, suffix=".csv") as tmp:
        tmp.write(contents)
        tmp_path = Path(tmp.name)

    try:
        from app.workers.finalscout_batch import run as run_finalscout_batch

        return await run_finalscout_batch(
            limit=limit,
            input_csv=tmp_path,
            state_file=Path("/tmp/finalscout_admin_state.json"),
            dry_run=dry_run,
            concurrency=concurrency,
        )
    finally:
        try:
            tmp_path.unlink(missing_ok=True)
        except Exception:
            pass


# ─── Role requests (approval queue) ──────────────────────────────────

class RoleRequestDecision(BaseModel):
    decision: str            # "approved" | "rejected"
    admin_note: str = ""


@router.get("/role-requests")
async def admin_role_requests(
    status_filter: Optional[str] = Query(default=None, alias="status"),
    limit: int = Query(default=300, ge=1, le=1000),
    admin: dict = Depends(require_admin_user),
):
    return {
        "requests": user_store.list_role_requests(status=status_filter, limit=limit),
        "pending": user_store.count_role_requests("pending"),
    }


@router.post("/role-requests/{request_id}/decision")
async def admin_decide_role_request(
    request_id: str,
    payload: RoleRequestDecision,
    admin: dict = Depends(require_admin_user),
):
    decision = payload.decision.strip().lower()
    if decision not in {"approved", "rejected"}:
        raise HTTPException(status_code=400, detail="decision must be 'approved' or 'rejected'")
    existing = user_store.get_role_request(request_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Role request not found")
    updated = user_store.update_role_request(
        request_id,
        {
            "status": decision,
            "admin_note": payload.admin_note.strip()[:1000],
            "decided_by": admin.get("email") or admin.get("id") or "admin",
            "decided_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    user_store.record_event(
        kind="role_request_decision",
        label=f"Role request {decision}",
        user_id=existing.get("user_id") or "",
        email=existing.get("email") or "",
        actor=admin.get("email") or "admin",
        level="info" if decision == "approved" else "warning",
        meta={"role": existing.get("role"), "request_id": request_id},
    )
    return updated


# ─── Signed agreements ───────────────────────────────────────────────

@router.get("/agreements")
async def admin_agreements(
    limit: int = Query(default=500, ge=1, le=2000),
    _: dict = Depends(require_admin_user),
):
    return {"agreements": user_store.list_agreements(limit=limit)}


# ─── Application / audit event log ───────────────────────────────────

@router.get("/events")
async def admin_events(
    limit: int = Query(default=300, ge=1, le=1000),
    user_id: Optional[str] = Query(default=None),
    kind: Optional[str] = Query(default=None),
    _: dict = Depends(require_admin_user),
):
    return {"events": user_store.list_events(limit=limit, user_id=user_id, kind=kind)}


# ─── Full user detail + account controls ─────────────────────────────

@router.get("/users/{user_id}")
async def admin_user_detail(user_id: str, _: dict = Depends(require_admin_user)):
    user = user_store.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    safe = {k: v for k, v in user.items() if k != "password_hash"}
    try:
        prefs = user_store.get_preferences(user_id)
    except Exception:
        prefs = {}
    try:
        resumes = user_store.list_resumes(user_id)
    except Exception:
        resumes = []
    return {
        "user": safe,
        "preferences": prefs,
        "resumes": resumes,
        "agreement": user_store.get_agreement_for_user(user_id),
        "role_requests": user_store.list_role_requests(user_id=user_id, limit=100),
        "events": user_store.list_events(user_id=user_id, limit=100),
    }


@router.post("/users/{user_id}/password-reset")
async def admin_trigger_password_reset(user_id: str, admin: dict = Depends(require_admin_user)):
    """Issue a password-reset email for a user (admin-initiated)."""
    user = user_store.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    try:
        from app.api.password_reset import forgot_password, ForgotPasswordRequest
        await forgot_password(ForgotPasswordRequest(email=user["email"]))
    except Exception as exc:  # pragma: no cover - best effort
        raise HTTPException(status_code=503, detail=f"Could not send reset email: {exc}")
    user_store.record_event(
        kind="admin_password_reset",
        label="Admin triggered password reset",
        user_id=user_id,
        email=user.get("email") or "",
        actor=admin.get("email") or "admin",
        level="warning",
    )
    return {"ok": True, "email": user["email"]}


@router.post("/users/{user_id}/revoke-sessions")
async def admin_revoke_sessions(user_id: str, admin: dict = Depends(require_admin_user)):
    revoked = user_store.revoke_user_sessions(user_id)
    user_store.record_event(
        kind="admin_revoke_sessions",
        label="Admin revoked all sessions",
        user_id=user_id,
        actor=admin.get("email") or "admin",
        level="warning",
        meta={"revoked": revoked},
    )
    return {"ok": True, "revoked": revoked}


# ─── Scraper coverage (positions + roles per country) ────────────────

# Countries we actively try to cover. Used to render the coverage chart even
# for countries that currently have zero rows.
_COVERAGE_COUNTRIES = country_options()


@router.get("/coverage")
async def admin_coverage(_: dict = Depends(require_admin_user)):
    """Best-effort positions-per-country snapshot from the jobs store."""
    db = None
    try:
        if settings.database_backend == "postgres":
            from app.db.postgres import PostgresClient
            db = PostgresClient()
        elif settings.database_backend == "firestore":
            from app.db.firebase import FirestoreClient
            db = FirestoreClient()
    except Exception:
        db = None

    total = 0
    per_country: list[dict] = []
    if db is not None:
        if hasattr(db, "admin_coverage_snapshot"):
            try:
                return await db.admin_coverage_snapshot(top_limit=10)
            except Exception:
                pass
        try:
            total = await db.count_jobs()
        except Exception:
            total = 0
        for country in _COVERAGE_COUNTRIES:
            code = str(country.get("code") or "")
            name = str(country.get("name") or code)
            try:
                count = await db.count_jobs({"country": code})
            except Exception:
                count = 0
            # Roles the scraper has collected for this country. Best-effort and
            # read-only — guarded so it can never break the positions snapshot.
            top_roles: list[dict] = []
            if count:
                try:
                    top_roles = await db.top_roles_by_country(code, limit=8)
                except Exception:
                    top_roles = []
            per_country.append({"country": code, "country_name": name, "positions": count, "top_roles": top_roles})
    per_country.sort(key=lambda r: r["positions"], reverse=True)
    return {"total_positions": total, "per_country": per_country, "top_roles": []}


# ─── Aggregated metrics for the Overview dashboard (charts) ───────────

def _day_key(iso: str) -> str:
    return (iso or "")[:10]  # YYYY-MM-DD


@router.get("/metrics")
async def admin_metrics(days: int = Query(default=30, ge=7, le=180), _: dict = Depends(require_admin_user)):
    """Everything the Overview dashboard charts need, computed from the user
    store and the audit-event log. All best-effort and read-only."""
    users = user_store.list_users(limit=5000)
    total_users = len(users)

    plan_counts: dict[str, int] = {}
    visa_counts: dict[str, int] = {}
    country_counts: dict[str, int] = {}
    experience_counts: dict[str, int] = {}
    for u in users:
        plan_counts[str(u.get("plan") or "Unknown")] = plan_counts.get(str(u.get("plan") or "Unknown"), 0) + 1
        visa = str(u.get("visa_status") or "Not set")
        visa_counts[visa] = visa_counts.get(visa, 0) + 1
        country = str(u.get("country") or "Unknown")
        country_counts[country] = country_counts.get(country, 0) + 1
        exp = str(u.get("experience_years") or "Not set")
        experience_counts[exp] = experience_counts.get(exp, 0) + 1

    # Signups per day for the last `days` days (fill gaps with 0).
    from datetime import date, timedelta
    today = date.today()
    buckets = {(today - timedelta(days=i)).isoformat(): 0 for i in range(days)}
    for u in users:
        dk = _day_key(str(u.get("created_at") or ""))
        if dk in buckets:
            buckets[dk] += 1
    signups_series = [{"date": d, "count": buckets[d]} for d in sorted(buckets.keys())]

    # Recent activity volume per day + per kind, from the event log.
    events = user_store.list_events(limit=1000)
    ev_by_day = {(today - timedelta(days=i)).isoformat(): 0 for i in range(days)}
    ev_by_kind: dict[str, int] = {}
    errors = 0
    for e in events:
        dk = _day_key(str(e.get("created_at") or ""))
        if dk in ev_by_day:
            ev_by_day[dk] += 1
        k = str(e.get("kind") or "other")
        ev_by_kind[k] = ev_by_kind.get(k, 0) + 1
        if str(e.get("level") or "") == "error":
            errors += 1
    activity_series = [{"date": d, "count": ev_by_day[d]} for d in sorted(ev_by_day.keys())]

    def _top(d: dict[str, int], n: int = 8) -> list[dict]:
        return [{"label": k, "count": v} for k, v in sorted(d.items(), key=lambda kv: kv[1], reverse=True)[:n]]

    fb = feedback_store.feedback_stats()

    return {
        "totals": {
            "users": total_users,
            "events": len(events),
            "errors": errors,
            "feedback": fb["total"],
            "avg_rating": fb["average_rating"],
            "signups_7d": sum(b["count"] for b in signups_series[-7:]),
        },
        "signups_series": signups_series,
        "activity_series": activity_series,
        "by_plan": _top(plan_counts),
        "by_visa": _top(visa_counts),
        "by_country": _top(country_counts),
        "by_experience": _top(experience_counts),
        "by_event_kind": _top(ev_by_kind, 10),
        "feedback": fb,
    }


# ─── User feedback (admin view) ──────────────────────────────────────

@router.get("/feedback")
async def admin_feedback(
    limit: int = Query(default=300, ge=1, le=1000),
    category: Optional[str] = Query(default=None),
    _: dict = Depends(require_admin_user),
):
    return {
        "feedback": feedback_store.list_feedback(limit=limit, category=category),
        "stats": feedback_store.feedback_stats(),
    }


class FeedbackStatusBody(BaseModel):
    status: str


@router.post("/feedback/{feedback_id}/status")
async def admin_set_feedback_status(feedback_id: str, body: FeedbackStatusBody, _: dict = Depends(require_admin_user)):
    updated = feedback_store.set_feedback_status(feedback_id, body.status)
    if not updated:
        raise HTTPException(status_code=404, detail="Feedback not found or invalid status")
    return updated

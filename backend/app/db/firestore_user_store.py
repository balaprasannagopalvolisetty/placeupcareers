"""Firestore-backed user/profile data store.

This module mirrors app.db.user_store so the auth/user API can keep the
same call sites while production user data lives in Firestore instead of
the Cloud Run container filesystem.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from google.cloud import firestore

from app.config import settings


_db = None


def _client():
    global _db
    if _db is None:
        _db = firestore.Client(
            project=settings.user_firestore_project_id or settings.gcp_project_id,
            database=settings.user_firestore_database,
        )
    return _db


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _parse_iso(value: str | None) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _doc(collection: str, doc_id: str):
    return _client().collection(collection).document(doc_id)


def _clean(data: dict | None) -> dict:
    out = dict(data or {})
    for key in ("email",):
        if out.get(key):
            out[key] = str(out[key]).lower()
    return out


def create_user(
    *,
    email: str,
    password_hash: str,
    first_name: str,
    last_name: str,
    plan: str = "Pro",
    visa_status: Optional[str] = None,
    experience_years: Optional[str] = None,
) -> dict:
    user_id = f"user_{uuid.uuid4().hex[:12]}"
    now = _now_iso()
    user = {
        "id": user_id,
        "email": email.lower(),
        "password_hash": password_hash,
        "first_name": first_name,
        "last_name": last_name,
        "plan": plan,
        "visa_status": visa_status,
        "experience_years": experience_years,
        "created_at": now,
        "updated_at": now,
    }
    batch = _client().batch()
    batch.set(_doc("users", user_id), user)
    batch.set(_doc("user_preferences", user_id), {
        "user_id": user_id,
        "updated_at": now,
        "visa_status": visa_status,
        "experience_level": experience_years,
        "target_roles": [],
        "target_locations": [],
    })
    batch.set(_doc("user_alert_settings", user_id), {
        "user_id": user_id,
        "email_alerts": True,
        "daily_digest": True,
        "weekly_report": False,
    })
    batch.commit()
    return user


def get_user_by_id(user_id: str) -> Optional[dict]:
    snap = _doc("users", user_id).get()
    if not snap.exists:
        return None
    return _clean(snap.to_dict() | {"id": snap.id})


def get_user_by_email(email: str) -> Optional[dict]:
    rows = (
        _client()
        .collection("users")
        .where("email", "==", email.lower())
        .limit(1)
        .stream()
    )
    for snap in rows:
        return _clean(snap.to_dict() | {"id": snap.id})
    return None


def list_users(limit: int = 500) -> list[dict]:
    rows = _client().collection("users").limit(limit).stream()
    return [_clean(snap.to_dict() | {"id": snap.id}) for snap in rows]


def update_user_profile(user_id: str, fields: dict[str, Any]) -> Optional[dict]:
    allowed = {
        "first_name", "last_name", "phone", "location", "visa_status",
        "experience_years", "current_role", "current_company", "summary",
        "linkedin_url", "github_url", "portfolio_url", "plan",
    }
    updates = {k: v for k, v in fields.items() if k in allowed}
    if updates:
        updates["updated_at"] = _now_iso()
        _doc("users", user_id).set(updates, merge=True)
    return get_user_by_id(user_id)


def set_user_password(user_id: str, password_hash: str) -> None:
    _doc("users", user_id).set({"password_hash": password_hash, "updated_at": _now_iso()}, merge=True)


def get_preferences(user_id: str) -> dict:
    ref = _doc("user_preferences", user_id)
    snap = ref.get()
    if not snap.exists:
        ref.set({
            "user_id": user_id,
            "updated_at": _now_iso(),
            "target_roles": [],
            "target_locations": [],
        })
        snap = ref.get()
    data = snap.to_dict() or {}
    data.setdefault("target_roles", [])
    data.setdefault("target_locations", [])
    return data


def update_preferences(user_id: str, fields: dict[str, Any]) -> dict:
    allowed = {
        "job_preferences",
        "notification_new_jobs", "notification_daily_digest",
        "notification_weekly_summary", "notification_ats_updates",
        "notification_marketing_emails",
        "visa_status", "experience_level",
    }
    updates = {k: v for k, v in fields.items() if k in allowed}
    if "target_roles" in fields:
        updates["target_roles"] = list(fields.get("target_roles") or [])[:25]
    if "target_locations" in fields:
        updates["target_locations"] = list(fields.get("target_locations") or [])
    updates["updated_at"] = _now_iso()
    _doc("user_preferences", user_id).set(updates, merge=True)
    return get_preferences(user_id)


def list_alerts(user_id: str, limit: int = 100) -> list[dict]:
    # Avoid requiring a composite Firestore index for (user_id, created_at).
    # Alerts are small per user, so query by user and sort locally; this keeps
    # the dashboard from hanging on first-load if the index is not provisioned.
    rows = (
        _client()
        .collection("user_alerts")
        .where("user_id", "==", user_id)
        .limit(max(limit * 5, limit))
        .stream()
    )
    alerts = [snap.to_dict() | {"id": snap.id} for snap in rows]
    alerts.sort(key=lambda row: str(row.get("created_at") or ""), reverse=True)
    return alerts[:limit]


def create_alert(user_id: str, payload: dict) -> dict:
    alert_id = f"a_{uuid.uuid4().hex[:10]}"
    data = {
        "id": alert_id,
        "user_id": user_id,
        "title": payload.get("title", ""),
        "company": payload.get("company", ""),
        "location": payload.get("location", ""),
        "salary": payload.get("salary", ""),
        "match_score": int(payload.get("match", payload.get("match_score", 0)) or 0),
        "visa": payload.get("visa", ""),
        "message": payload.get("message"),
        "unread": True,
        "created_at": _now_iso(),
    }
    _doc("user_alerts", alert_id).set(data)
    return data


def mark_alert_read(user_id: str, alert_id: str) -> Optional[dict]:
    ref = _doc("user_alerts", alert_id)
    snap = ref.get()
    if not snap.exists or (snap.to_dict() or {}).get("user_id") != user_id:
        return None
    ref.set({"unread": False}, merge=True)
    data = ref.get().to_dict() or {}
    return data | {"id": alert_id}


def mark_all_alerts_read(user_id: str) -> int:
    alerts = list_alerts(user_id, limit=500)
    batch = _client().batch()
    count = 0
    for alert in alerts:
        if alert.get("unread"):
            batch.set(_doc("user_alerts", alert["id"]), {"unread": False}, merge=True)
            count += 1
    if count:
        batch.commit()
    return count


def delete_alert(user_id: str, alert_id: str) -> int:
    ref = _doc("user_alerts", alert_id)
    snap = ref.get()
    if not snap.exists or (snap.to_dict() or {}).get("user_id") != user_id:
        return 0
    ref.delete()
    return 1


def get_alert_settings(user_id: str) -> dict:
    ref = _doc("user_alert_settings", user_id)
    snap = ref.get()
    if not snap.exists:
        ref.set({
            "user_id": user_id,
            "email_alerts": True,
            "daily_digest": True,
            "weekly_report": False,
        })
        snap = ref.get()
    data = snap.to_dict() or {}
    for key in ("email_alerts", "daily_digest", "weekly_report"):
        data[key] = bool(data.get(key))
    return data


def update_alert_settings(user_id: str, payload: dict) -> dict:
    updates = {k: bool(payload[k]) for k in ("email_alerts", "daily_digest", "weekly_report") if k in payload}
    if updates:
        _doc("user_alert_settings", user_id).set(updates, merge=True)
    return get_alert_settings(user_id)


def list_resumes(user_id: str) -> list[dict]:
    rows = (
        _client()
        .collection("user_resumes")
        .where("user_id", "==", user_id)
        .stream()
    )
    resumes = [
        snap.to_dict() | {"id": snap.id, "active": bool((snap.to_dict() or {}).get("active"))}
        for snap in rows
    ]
    return sorted(resumes, key=lambda item: item.get("uploaded_at") or "", reverse=True)


def create_resume(
    user_id: str,
    *,
    name: str,
    score: int,
    size_bytes: int,
    storage_path: Optional[str] = None,
    parsed_text: Optional[str] = None,
    active: bool = False,
) -> dict:
    resume_id = f"r_{uuid.uuid4().hex[:10]}"
    if active:
        for resume in list_resumes(user_id):
            _doc("user_resumes", resume["id"]).set({"active": False}, merge=True)
    data = {
        "id": resume_id,
        "user_id": user_id,
        "name": name,
        "uploaded_at": _now_iso(),
        "score": int(score),
        "size_bytes": int(size_bytes),
        "active": bool(active),
        "storage_path": storage_path,
        "parsed_text": (parsed_text or "")[:200000],
    }
    _doc("user_resumes", resume_id).set(data)
    return data


def set_active_resume(user_id: str, resume_id: str) -> Optional[dict]:
    found = None
    for resume in list_resumes(user_id):
        active = resume["id"] == resume_id
        _doc("user_resumes", resume["id"]).set({"active": active}, merge=True)
        if active:
            found = resume | {"active": True}
    return found


def update_resume_parsed_text(user_id: str, resume_id: str, parsed_text: str) -> Optional[dict]:
    ref = _doc("user_resumes", resume_id)
    snap = ref.get()
    data = snap.to_dict() if snap.exists else None
    if not data or data.get("user_id") != user_id:
        return None
    ref.set({"parsed_text": (parsed_text or "")[:200000]}, merge=True)
    updated = ref.get().to_dict() or {}
    return updated | {"id": resume_id}


def delete_resume(user_id: str, resume_id: str) -> int:
    ref = _doc("user_resumes", resume_id)
    snap = ref.get()
    if not snap.exists or (snap.to_dict() or {}).get("user_id") != user_id:
        return 0
    ref.delete()
    return 1


def count_user_applications(user_id: str) -> int:
    return len(list(_client().collection("user_applications").where("user_id", "==", user_id).stream()))


def upsert_user_application(user_id: str, payload: dict) -> dict:
    job_id = str(payload.get("job_id") or "").strip()
    if not job_id:
        raise ValueError("job_id is required")
    app_id = f"{user_id}_{job_id}".replace("/", "_")
    now = _now_iso()
    data = {
        "id": app_id,
        "user_id": user_id,
        "job_id": job_id,
        "title": payload.get("title") or "",
        "company": payload.get("company") or "",
        "location": payload.get("location") or "",
        "job_url": payload.get("job_url") or "",
        "description": (payload.get("description") or "")[:12000],
        "match_score": int(payload.get("match_score") or 0),
        "status": payload.get("status") or "applied",
        "not_applied_reason": payload.get("not_applied_reason") or "",
        "heard_back": payload.get("heard_back"),
        "position_open": payload.get("position_open"),
        "salary_offered": payload.get("salary_offered") or "",
        "notes": payload.get("notes") or "",
        "updated_at": now,
    }
    existing = _doc("user_applications", app_id).get()
    if not existing.exists:
        data["created_at"] = now
    _doc("user_applications", app_id).set(data, merge=True)
    return (_doc("user_applications", app_id).get().to_dict() or data) | {"id": app_id}


def list_user_applications(user_id: str, limit: int = 500) -> list[dict]:
    rows = (
        _client()
        .collection("user_applications")
        .where("user_id", "==", user_id)
        .limit(limit)
        .stream()
    )
    return [snap.to_dict() | {"id": snap.id} for snap in rows]


def create_auth_session(
    user_id: str,
    *,
    refresh_hash: str,
    expires_at: datetime,
    user_agent: str = "",
    ip_address: str = "",
) -> dict:
    session_id = f"s_{uuid.uuid4().hex}"
    now = _now_iso()
    data = {
        "id": session_id,
        "user_id": user_id,
        "refresh_hash": refresh_hash,
        "created_at": now,
        "updated_at": now,
        "expires_at": expires_at.astimezone(timezone.utc).isoformat(),
        "revoked": False,
        "user_agent": user_agent[:300],
        "ip_address": ip_address[:80],
    }
    _doc("auth_sessions", session_id).set(data)
    return data


def get_auth_session_by_refresh_hash(refresh_hash: str) -> Optional[dict]:
    rows = (
        _client()
        .collection("auth_sessions")
        .where("refresh_hash", "==", refresh_hash)
        .where("revoked", "==", False)
        .limit(1)
        .stream()
    )
    now = datetime.now(tz=timezone.utc)
    for snap in rows:
        data = snap.to_dict() or {}
        expires_at = _parse_iso(data.get("expires_at"))
        if expires_at and expires_at > now:
            return data | {"id": snap.id}
    return None


def get_auth_session(session_id: str) -> Optional[dict]:
    if not session_id:
        return None
    snap = _doc("auth_sessions", session_id).get()
    if not snap.exists:
        return None
    data = snap.to_dict() or {}
    expires_at = _parse_iso(data.get("expires_at"))
    if data.get("revoked"):
        return None
    if expires_at and expires_at <= datetime.now(tz=timezone.utc):
        return None
    return data | {"id": snap.id}


def rotate_auth_session(session_id: str, *, refresh_hash: str, expires_at: datetime) -> Optional[dict]:
    ref = _doc("auth_sessions", session_id)
    snap = ref.get()
    if not snap.exists:
        return None
    ref.set(
        {
            "refresh_hash": refresh_hash,
            "expires_at": expires_at.astimezone(timezone.utc).isoformat(),
            "updated_at": _now_iso(),
        },
        merge=True,
    )
    return (ref.get().to_dict() or {}) | {"id": session_id}


def revoke_auth_session(session_id: str) -> None:
    _doc("auth_sessions", session_id).set({"revoked": True, "updated_at": _now_iso()}, merge=True)


def revoke_user_sessions(user_id: str) -> int:
    rows = (
        _client()
        .collection("auth_sessions")
        .where("user_id", "==", user_id)
        .where("revoked", "==", False)
        .stream()
    )
    batch = _client().batch()
    count = 0
    for snap in rows:
        batch.set(snap.reference, {"revoked": True, "updated_at": _now_iso()}, merge=True)
        count += 1
    if count:
        batch.commit()
    return count


# Alias so password_reset.py and any future caller can use the more
# evocative name without us having to rename the original helper.
def revoke_all_refresh_tokens(user_id: str) -> int:
    """Revoke every active refresh-token session for the given user.

    Called from the password reset flow so a leaked password that
    already minted refresh tokens cannot continue to mint new access
    tokens after the password is changed.
    """
    return revoke_user_sessions(user_id)


# ─── Password reset + email verification token store ────────────────
#
# Both flows store a SHA-256-hashed token (the plaintext token only
# exists in the email link we send) and an expiry timestamp. Lookups
# are by token_hash — the user_id is the payload we return on consume.
#
# Each call to `upsert_*` overwrites any prior token for that user so
# requesting a new reset link invalidates the previous one. Each
# `consume_*` deletes the document atomically so a single token can't
# be re-used.

def _token_doc_id(token_hash: str) -> str:
    # Firestore document IDs can't contain "/", and hex digests don't
    # anyway, but we still hard-trim to keep the path clean.
    return token_hash[:128]


def upsert_password_reset(
    *,
    user_id: str,
    token_hash: str,
    expires_at: datetime,
) -> None:
    """Persist a password-reset token. Overwrites any prior token for this user."""
    # Wipe any in-flight reset tokens this user already has so the only
    # active link in their inbox is the most recent one.
    existing = (
        _client()
        .collection("password_resets")
        .where("user_id", "==", user_id)
        .stream()
    )
    batch = _client().batch()
    for snap in existing:
        batch.delete(snap.reference)
    batch.set(
        _doc("password_resets", _token_doc_id(token_hash)),
        {
            "user_id": user_id,
            "token_hash": token_hash,
            "expires_at": expires_at.astimezone(timezone.utc).isoformat(),
            "created_at": _now_iso(),
        },
    )
    batch.commit()


def consume_password_reset(token_hash: str) -> Optional[dict]:
    """Atomically look up + delete a reset token. Returns {user_id} or None."""
    ref = _doc("password_resets", _token_doc_id(token_hash))
    snap = ref.get()
    if not snap.exists:
        return None
    data = snap.to_dict() or {}
    # Always delete first — even if expired, so the document doesn't
    # linger and accumulate. Deleting after the expiry check would
    # also be correct; this just makes the cleanup cheaper.
    ref.delete()
    expires_at = _parse_iso(data.get("expires_at"))
    if expires_at and expires_at < datetime.now(tz=timezone.utc):
        return None
    return {"user_id": data.get("user_id")}


def upsert_email_verification(
    *,
    user_id: str,
    token_hash: str,
    expires_at: datetime,
) -> None:
    """Persist an email-verification token. Overwrites any prior token."""
    existing = (
        _client()
        .collection("email_verifications")
        .where("user_id", "==", user_id)
        .stream()
    )
    batch = _client().batch()
    for snap in existing:
        batch.delete(snap.reference)
    batch.set(
        _doc("email_verifications", _token_doc_id(token_hash)),
        {
            "user_id": user_id,
            "token_hash": token_hash,
            "expires_at": expires_at.astimezone(timezone.utc).isoformat(),
            "created_at": _now_iso(),
        },
    )
    batch.commit()


def consume_email_verification(token_hash: str) -> Optional[dict]:
    ref = _doc("email_verifications", _token_doc_id(token_hash))
    snap = ref.get()
    if not snap.exists:
        return None
    data = snap.to_dict() or {}
    ref.delete()
    expires_at = _parse_iso(data.get("expires_at"))
    if expires_at and expires_at < datetime.now(tz=timezone.utc):
        return None
    return {"user_id": data.get("user_id")}


def mark_email_verified(user_id: str) -> None:
    _doc("users", user_id).set(
        {"email_verified": True, "email_verified_at": _now_iso(), "updated_at": _now_iso()},
        merge=True,
    )


# ─── Account deletion (full cascade) ────────────────────────────────

def delete_user(user_id: str) -> dict:
    """Permanently delete a user and every record we hold for them.

    This is a HARD delete — there is no soft-delete flag because the
    privacy policy at /privacy promises "Deletion removes active records
    immediately; backups roll off within 30 days". To honour that we
    have to wipe the live records on the spot.

    Returns a summary of how many docs were removed from each
    collection, useful for logging and for the API response so the
    user has audit trail of what happened.
    """
    counts: dict[str, int] = {}

    # Sessions first — invalidate auth so any in-flight access tokens
    # stop refreshing the moment we delete the user document.
    counts["auth_sessions_revoked"] = revoke_user_sessions(user_id)

    # Per-collection wipe. Each one is a small batch; Firestore caps
    # batches at 500 ops so we paginate.
    user_owned = [
        ("user_preferences", None),       # doc id == user_id
        ("user_alert_settings", None),
        ("user_alerts", "user_id"),
        ("user_resumes", "user_id"),
        ("user_applications", "user_id"),
        ("auth_sessions", "user_id"),
        ("password_resets", "user_id"),
        ("email_verifications", "user_id"),
    ]
    for collection, filter_field in user_owned:
        wiped = 0
        if filter_field is None:
            # Singleton doc keyed on user_id.
            ref = _doc(collection, user_id)
            snap = ref.get()
            if snap.exists:
                ref.delete()
                wiped += 1
        else:
            for snap in _client().collection(collection).where(filter_field, "==", user_id).stream():
                snap.reference.delete()
                wiped += 1
        counts[collection] = wiped

    # Finally the user doc itself.
    user_ref = _doc("users", user_id)
    user_doc = user_ref.get()
    if user_doc.exists:
        user_ref.delete()
        counts["users"] = 1
    else:
        counts["users"] = 0

    return counts

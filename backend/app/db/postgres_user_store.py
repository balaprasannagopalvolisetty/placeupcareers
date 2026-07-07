"""Postgres/Supabase-backed user & related data store.

Drop-in replacement for app.db.firestore_user_store: identical function
signatures and return shapes (plain dicts, ISO-8601 string timestamps),
so every call site through app.db.user_store keeps working unchanged.

Selected via USER_DATABASE_BACKEND=postgres. Uses the same DATABASE_URL
as the jobs store (single Supabase Postgres database).

Every table carries an ``extra`` JSONB column so Firestore fields that
were never modelled explicitly survive the migration and round-trip
through reads.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import create_engine, text

from app.config import settings

_engine = None

# Tables whose singleton rows are keyed on user_id (Firestore doc id == user_id)
_SINGLETON_TABLES = ("user_preferences", "user_alert_settings")


def _eng():
    global _engine
    if _engine is None:
        _engine = create_engine(
            settings.database_url,
            pool_size=max(2, settings.db_pool_size // 2),
            max_overflow=settings.db_max_overflow,
            pool_pre_ping=True,
            pool_recycle=1800,
        )
    return _engine


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _parse_iso(value: str | None) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _to_bool(value: Any) -> Optional[bool]:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"true", "1", "yes", "y", "t"}


def _row_dict(row) -> dict:
    """Row -> plain dict shaped like the old Firestore document."""
    d = dict(row._mapping)
    extra = d.pop("extra", None) or {}
    if isinstance(extra, str):
        try:
            extra = json.loads(extra)
        except ValueError:
            extra = {}
    return {**extra, **d}


def _clean(data: dict | None) -> dict:
    out = dict(data or {})
    for key in ("email",):
        if out.get(key):
            out[key] = str(out[key]).lower()
    return out


def _jd(value) -> str:
    return json.dumps(value if value is not None else {})


# ─── Users ───────────────────────────────────────────────────────────


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
    with _eng().begin() as cx:
        cx.execute(
            text(
                """
                insert into users (id, email, password_hash, first_name, last_name,
                                   plan, visa_status, experience_years, created_at, updated_at)
                values (:id, :email, :ph, :fn, :ln, :plan, :vs, :xp, :now, :now)
                """
            ),
            {"id": user_id, "email": email.lower(), "ph": password_hash, "fn": first_name,
             "ln": last_name, "plan": plan, "vs": visa_status, "xp": experience_years, "now": now},
        )
        cx.execute(
            text(
                """
                insert into user_preferences (user_id, updated_at, visa_status, experience_level,
                                              target_roles, target_locations)
                values (:uid, :now, :vs, :xp, '[]'::jsonb, '[]'::jsonb)
                on conflict (user_id) do nothing
                """
            ),
            {"uid": user_id, "now": now, "vs": visa_status, "xp": experience_years},
        )
        cx.execute(
            text(
                """
                insert into user_alert_settings (user_id, email_alerts, daily_digest, weekly_report)
                values (:uid, true, true, false)
                on conflict (user_id) do nothing
                """
            ),
            {"uid": user_id},
        )
    return {
        "id": user_id, "email": email.lower(), "password_hash": password_hash,
        "first_name": first_name, "last_name": last_name, "plan": plan,
        "visa_status": visa_status, "experience_years": experience_years,
        "created_at": now, "updated_at": now,
    }


def get_user_by_id(user_id: str) -> Optional[dict]:
    with _eng().begin() as cx:
        row = cx.execute(text("select * from users where id = :id"), {"id": user_id}).fetchone()
    return _clean(_row_dict(row)) if row else None


def get_user_by_email(email: str) -> Optional[dict]:
    with _eng().begin() as cx:
        row = cx.execute(
            text("select * from users where lower(email) = :email limit 1"),
            {"email": (email or "").lower()},
        ).fetchone()
    return _clean(_row_dict(row)) if row else None


def get_user_by_phone(phone: str) -> Optional[dict]:
    raw_phone = str(phone or "").strip()
    if not raw_phone:
        return None
    digits = "".join(ch for ch in raw_phone if ch.isdigit())
    with _eng().begin() as cx:
        row = cx.execute(
            text("select * from users where phone = :p limit 1"), {"p": raw_phone}
        ).fetchone()
        if not row and digits:
            row = cx.execute(
                text(
                    "select * from users where regexp_replace(coalesce(phone, ''), '\\D', '', 'g') = :d limit 1"
                ),
                {"d": digits},
            ).fetchone()
    return _clean(_row_dict(row)) if row else None


def list_users(limit: int = 500) -> list[dict]:
    with _eng().begin() as cx:
        rows = cx.execute(text("select * from users limit :n"), {"n": limit}).fetchall()
    return [_clean(_row_dict(r)) for r in rows]


_PROFILE_FIELDS = {
    "first_name", "last_name", "phone", "location", "visa_status",
    "experience_years", "current_role", "current_company", "summary",
    "linkedin_url", "github_url", "portfolio_url", "plan",
}


def update_user_profile(user_id: str, fields: dict[str, Any]) -> Optional[dict]:
    updates = {k: v for k, v in fields.items() if k in _PROFILE_FIELDS}
    if updates:
        updates["updated_at"] = _now_iso()
        sets = ", ".join(f'"{k}" = :{k}' for k in updates)
        with _eng().begin() as cx:
            cx.execute(text(f"update users set {sets} where id = :_uid"), {**updates, "_uid": user_id})
    return get_user_by_id(user_id)


def set_user_password(user_id: str, password_hash: str) -> None:
    with _eng().begin() as cx:
        cx.execute(
            text("update users set password_hash = :ph, updated_at = :now where id = :id"),
            {"ph": password_hash, "now": _now_iso(), "id": user_id},
        )


# ─── Preferences ─────────────────────────────────────────────────────


def get_preferences(user_id: str) -> dict:
    with _eng().begin() as cx:
        row = cx.execute(
            text("select * from user_preferences where user_id = :uid"), {"uid": user_id}
        ).fetchone()
        if not row:
            cx.execute(
                text(
                    """
                    insert into user_preferences (user_id, updated_at, target_roles, target_locations)
                    values (:uid, :now, '[]'::jsonb, '[]'::jsonb)
                    on conflict (user_id) do nothing
                    """
                ),
                {"uid": user_id, "now": _now_iso()},
            )
            row = cx.execute(
                text("select * from user_preferences where user_id = :uid"), {"uid": user_id}
            ).fetchone()
    data = _row_dict(row) if row else {"user_id": user_id}
    data["target_roles"] = data.get("target_roles") or []
    data["target_locations"] = data.get("target_locations") or []
    return data


_PREF_SIMPLE = {"visa_status", "experience_level"}
_PREF_BOOLS = {
    "notification_new_jobs", "notification_daily_digest",
    "notification_weekly_summary", "notification_ats_updates",
    "notification_marketing_emails",
}


def update_preferences(user_id: str, fields: dict[str, Any]) -> dict:
    get_preferences(user_id)  # ensure the row exists
    sets, params = [], {"_uid": user_id, "_now": _now_iso()}
    for k in _PREF_SIMPLE & set(fields):
        sets.append(f"{k} = :{k}")
        params[k] = fields[k]
    for k in _PREF_BOOLS & set(fields):
        sets.append(f"{k} = :{k}")
        params[k] = _to_bool(fields[k])
    if "job_preferences" in fields:
        sets.append("job_preferences = cast(:job_preferences as jsonb)")
        params["job_preferences"] = _jd(fields.get("job_preferences"))
    if "target_roles" in fields:
        sets.append("target_roles = cast(:target_roles as jsonb)")
        params["target_roles"] = _jd(list(fields.get("target_roles") or [])[:25])
    if "target_locations" in fields:
        sets.append("target_locations = cast(:target_locations as jsonb)")
        params["target_locations"] = _jd(list(fields.get("target_locations") or []))
    sets.append("updated_at = :_now")
    with _eng().begin() as cx:
        cx.execute(text(f"update user_preferences set {', '.join(sets)} where user_id = :_uid"), params)
    return get_preferences(user_id)


# ─── Alerts ──────────────────────────────────────────────────────────


def list_alerts(user_id: str, limit: int = 100) -> list[dict]:
    with _eng().begin() as cx:
        rows = cx.execute(
            text(
                "select * from user_alerts where user_id = :uid order by created_at desc limit :n"
            ),
            {"uid": user_id, "n": limit},
        ).fetchall()
    return [_row_dict(r) for r in rows]


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
    with _eng().begin() as cx:
        cx.execute(
            text(
                """
                insert into user_alerts (id, user_id, title, company, location, salary,
                                         match_score, visa, message, unread, created_at)
                values (:id, :user_id, :title, :company, :location, :salary,
                        :match_score, :visa, :message, :unread, :created_at)
                """
            ),
            data,
        )
    return data


def mark_alert_read(user_id: str, alert_id: str) -> Optional[dict]:
    with _eng().begin() as cx:
        row = cx.execute(
            text(
                "update user_alerts set unread = false where id = :aid and user_id = :uid returning *"
            ),
            {"aid": alert_id, "uid": user_id},
        ).fetchone()
    return _row_dict(row) if row else None


def mark_all_alerts_read(user_id: str) -> int:
    with _eng().begin() as cx:
        res = cx.execute(
            text("update user_alerts set unread = false where user_id = :uid and unread"),
            {"uid": user_id},
        )
    return res.rowcount or 0


def delete_alert(user_id: str, alert_id: str) -> int:
    with _eng().begin() as cx:
        res = cx.execute(
            text("delete from user_alerts where id = :aid and user_id = :uid"),
            {"aid": alert_id, "uid": user_id},
        )
    return res.rowcount or 0


def get_alert_settings(user_id: str) -> dict:
    with _eng().begin() as cx:
        row = cx.execute(
            text("select * from user_alert_settings where user_id = :uid"), {"uid": user_id}
        ).fetchone()
        if not row:
            cx.execute(
                text(
                    """
                    insert into user_alert_settings (user_id, email_alerts, daily_digest, weekly_report)
                    values (:uid, true, true, false)
                    on conflict (user_id) do nothing
                    """
                ),
                {"uid": user_id},
            )
            row = cx.execute(
                text("select * from user_alert_settings where user_id = :uid"), {"uid": user_id}
            ).fetchone()
    data = _row_dict(row) if row else {"user_id": user_id}
    for key in ("email_alerts", "daily_digest", "weekly_report"):
        data[key] = bool(data.get(key))
    return data


def update_alert_settings(user_id: str, payload: dict) -> dict:
    updates = {k: bool(payload[k]) for k in ("email_alerts", "daily_digest", "weekly_report") if k in payload}
    if updates:
        get_alert_settings(user_id)  # ensure row exists
        sets = ", ".join(f"{k} = :{k}" for k in updates)
        with _eng().begin() as cx:
            cx.execute(
                text(f"update user_alert_settings set {sets} where user_id = :_uid"),
                {**updates, "_uid": user_id},
            )
    return get_alert_settings(user_id)


# ─── Resumes ─────────────────────────────────────────────────────────


def list_resumes(user_id: str) -> list[dict]:
    with _eng().begin() as cx:
        rows = cx.execute(
            text("select * from user_resumes where user_id = :uid order by uploaded_at desc"),
            {"uid": user_id},
        ).fetchall()
    out = []
    for r in rows:
        d = _row_dict(r)
        d["active"] = bool(d.get("active"))
        out.append(d)
    return out


def create_resume(
    user_id: str,
    *,
    name: str,
    score: int,
    size_bytes: int,
    storage_path: Optional[str] = None,
    parsed_text: Optional[str] = None,
    parsed_json: Optional[dict[str, Any]] = None,
    active: bool = False,
) -> dict:
    resume_id = f"r_{uuid.uuid4().hex[:10]}"
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
        "parsed_json": parsed_json or {},
    }
    with _eng().begin() as cx:
        if active:
            cx.execute(
                text("update user_resumes set active = false where user_id = :uid"),
                {"uid": user_id},
            )
        cx.execute(
            text(
                """
                insert into user_resumes (id, user_id, name, uploaded_at, score, size_bytes,
                                          active, storage_path, parsed_text, parsed_json)
                values (:id, :user_id, :name, :uploaded_at, :score, :size_bytes,
                        :active, :storage_path, :parsed_text, cast(:parsed_json as jsonb))
                """
            ),
            {**data, "parsed_json": _jd(data["parsed_json"])},
        )
    return data


def set_active_resume(user_id: str, resume_id: str) -> Optional[dict]:
    with _eng().begin() as cx:
        cx.execute(
            text("update user_resumes set active = (id = :rid) where user_id = :uid"),
            {"rid": resume_id, "uid": user_id},
        )
        row = cx.execute(
            text("select * from user_resumes where id = :rid and user_id = :uid and active"),
            {"rid": resume_id, "uid": user_id},
        ).fetchone()
    if not row:
        return None
    d = _row_dict(row)
    d["active"] = True
    return d


def update_resume_parsed_text(user_id: str, resume_id: str, parsed_text: str) -> Optional[dict]:
    with _eng().begin() as cx:
        row = cx.execute(
            text(
                """
                update user_resumes set parsed_text = :pt
                where id = :rid and user_id = :uid
                returning *
                """
            ),
            {"pt": (parsed_text or "")[:200000], "rid": resume_id, "uid": user_id},
        ).fetchone()
    return _row_dict(row) if row else None


def delete_resume(user_id: str, resume_id: str) -> int:
    with _eng().begin() as cx:
        res = cx.execute(
            text("delete from user_resumes where id = :rid and user_id = :uid"),
            {"rid": resume_id, "uid": user_id},
        )
    return res.rowcount or 0


# ─── Applications ────────────────────────────────────────────────────


def count_user_applications(user_id: str) -> int:
    with _eng().begin() as cx:
        return int(
            cx.execute(
                text("select count(*) from user_applications where user_id = :uid"),
                {"uid": user_id},
            ).scalar()
            or 0
        )


def upsert_user_application(user_id: str, payload: dict) -> dict:
    job_id = str(payload.get("job_id") or "").strip()
    if not job_id:
        raise ValueError("job_id is required")
    app_id = f"{user_id}_{job_id}".replace("/", "_")
    now = _now_iso()
    params = {
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
        "heard_back": _to_bool(payload.get("heard_back")),
        "position_open": _to_bool(payload.get("position_open")),
        "salary_offered": payload.get("salary_offered") or "",
        "notes": payload.get("notes") or "",
        "now": now,
    }
    with _eng().begin() as cx:
        row = cx.execute(
            text(
                """
                insert into user_applications (id, user_id, job_id, title, company, location,
                    job_url, description, match_score, status, not_applied_reason, heard_back,
                    position_open, salary_offered, notes, created_at, updated_at)
                values (:id, :user_id, :job_id, :title, :company, :location, :job_url,
                    :description, :match_score, :status, :not_applied_reason, :heard_back,
                    :position_open, :salary_offered, :notes, :now, :now)
                on conflict (id) do update set
                    title = excluded.title, company = excluded.company,
                    location = excluded.location, job_url = excluded.job_url,
                    description = excluded.description, match_score = excluded.match_score,
                    status = excluded.status, not_applied_reason = excluded.not_applied_reason,
                    heard_back = excluded.heard_back, position_open = excluded.position_open,
                    salary_offered = excluded.salary_offered, notes = excluded.notes,
                    updated_at = excluded.updated_at
                returning *
                """
            ),
            params,
        ).fetchone()
    return _row_dict(row)


def list_user_applications(user_id: str, limit: int = 500) -> list[dict]:
    with _eng().begin() as cx:
        rows = cx.execute(
            text("select * from user_applications where user_id = :uid limit :n"),
            {"uid": user_id, "n": limit},
        ).fetchall()
    return [_row_dict(r) for r in rows]


# ─── Tailor queue ────────────────────────────────────────────────────


def _tailor_day_key(value: Optional[datetime] = None) -> str:
    dt = value or datetime.now(tz=timezone.utc)
    return dt.astimezone(timezone.utc).date().isoformat()


def list_tailor_queue(user_id: str, limit: int = 100) -> list[dict]:
    with _eng().begin() as cx:
        rows = cx.execute(
            text(
                "select * from user_tailor_queue where user_id = :uid order by created_at desc nulls last limit :n"
            ),
            {"uid": user_id, "n": limit},
        ).fetchall()
    return [_row_dict(r) for r in rows]


def count_tailor_requests_today(user_id: str, day_key: Optional[str] = None) -> int:
    day = day_key or _tailor_day_key()
    with _eng().begin() as cx:
        return int(
            cx.execute(
                text(
                    "select count(*) from user_tailor_queue where user_id = :uid and queued_day = :day"
                ),
                {"uid": user_id, "day": day},
            ).scalar()
            or 0
        )


def upsert_tailor_queue_item(user_id: str, payload: dict, *, daily_limit: int = 25) -> dict:
    job_id = str(payload.get("job_id") or "").strip()
    if not job_id:
        raise ValueError("job_id is required")
    item_id = f"{user_id}_{job_id}".replace("/", "_")
    now = _now_iso()
    day_key = _tailor_day_key()
    with _eng().begin() as cx:
        existing = cx.execute(
            text("select * from user_tailor_queue where id = :id"), {"id": item_id}
        ).fetchone()
        if not existing and count_tailor_requests_today(user_id, day_key) >= daily_limit:
            raise ValueError(f"Daily tailor queue limit reached ({daily_limit} jobs). Try again tomorrow.")
        params = {
            "id": item_id,
            "user_id": user_id,
            "job_id": job_id,
            "title": payload.get("title") or "",
            "company": payload.get("company") or "",
            "location": payload.get("location") or "",
            "job_url": payload.get("job_url") or "",
            "description": (payload.get("description") or "")[:50000],
            "match_score": int(payload.get("match_score") or 0),
            "status": (dict(existing._mapping).get("status") or "queued") if existing else "queued",
            "queued_day": (dict(existing._mapping).get("queued_day") or day_key) if existing else day_key,
            "now": now,
        }
        row = cx.execute(
            text(
                """
                insert into user_tailor_queue (id, user_id, job_id, title, company, location,
                    job_url, description, match_score, status, queued_day, created_at, updated_at)
                values (:id, :user_id, :job_id, :title, :company, :location, :job_url,
                    :description, :match_score, :status, :queued_day, :now, :now)
                on conflict (id) do update set
                    title = excluded.title, company = excluded.company,
                    location = excluded.location, job_url = excluded.job_url,
                    description = excluded.description, match_score = excluded.match_score,
                    status = excluded.status, queued_day = excluded.queued_day,
                    updated_at = excluded.updated_at
                returning *
                """
            ),
            params,
        ).fetchone()
    return _row_dict(row)


def get_tailor_queue_item(user_id: str, item_id: str) -> Optional[dict]:
    with _eng().begin() as cx:
        row = cx.execute(
            text("select * from user_tailor_queue where id = :id and user_id = :uid"),
            {"id": item_id, "uid": user_id},
        ).fetchone()
    return _row_dict(row) if row else None


_TAILOR_UPDATE_FIELDS = {
    "status", "ats_score", "generated_at", "keyword_targets",
    "last_format", "filename", "summary",
}


def update_tailor_queue_item(user_id: str, item_id: str, fields: dict[str, Any]) -> Optional[dict]:
    if not get_tailor_queue_item(user_id, item_id):
        return None
    sets, params = [], {"_id": item_id, "_now": _now_iso()}
    for k in _TAILOR_UPDATE_FIELDS & set(fields):
        if k == "keyword_targets":
            sets.append("keyword_targets = cast(:keyword_targets as jsonb)")
            params[k] = _jd(fields[k])
        elif k == "ats_score":
            sets.append("ats_score = :ats_score")
            params[k] = int(fields[k] or 0)
        else:
            sets.append(f'"{k}" = :{k}')
            params[k] = fields[k]
    sets.append("updated_at = :_now")
    with _eng().begin() as cx:
        cx.execute(text(f"update user_tailor_queue set {', '.join(sets)} where id = :_id"), params)
    return get_tailor_queue_item(user_id, item_id)


# ─── Auth sessions ───────────────────────────────────────────────────


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
    with _eng().begin() as cx:
        cx.execute(
            text(
                """
                insert into auth_sessions (id, user_id, refresh_hash, created_at, updated_at,
                                           expires_at, revoked, user_agent, ip_address)
                values (:id, :user_id, :refresh_hash, :created_at, :updated_at,
                        :expires_at, :revoked, :user_agent, :ip_address)
                """
            ),
            data,
        )
    return data


def get_auth_session_by_refresh_hash(refresh_hash: str) -> Optional[dict]:
    with _eng().begin() as cx:
        row = cx.execute(
            text(
                "select * from auth_sessions where refresh_hash = :rh and not revoked limit 1"
            ),
            {"rh": refresh_hash},
        ).fetchone()
    if not row:
        return None
    data = _row_dict(row)
    expires_at = _parse_iso(data.get("expires_at"))
    if expires_at and expires_at > datetime.now(tz=timezone.utc):
        return data
    return None


def get_auth_session(session_id: str) -> Optional[dict]:
    if not session_id:
        return None
    with _eng().begin() as cx:
        row = cx.execute(
            text("select * from auth_sessions where id = :id"), {"id": session_id}
        ).fetchone()
    if not row:
        return None
    data = _row_dict(row)
    if data.get("revoked"):
        return None
    expires_at = _parse_iso(data.get("expires_at"))
    if expires_at and expires_at <= datetime.now(tz=timezone.utc):
        return None
    return data


def rotate_auth_session(session_id: str, *, refresh_hash: str, expires_at: datetime) -> Optional[dict]:
    with _eng().begin() as cx:
        row = cx.execute(
            text(
                """
                update auth_sessions
                set refresh_hash = :rh, expires_at = :exp, updated_at = :now
                where id = :id
                returning *
                """
            ),
            {
                "rh": refresh_hash,
                "exp": expires_at.astimezone(timezone.utc).isoformat(),
                "now": _now_iso(),
                "id": session_id,
            },
        ).fetchone()
    return _row_dict(row) if row else None


def revoke_auth_session(session_id: str) -> None:
    with _eng().begin() as cx:
        cx.execute(
            text("update auth_sessions set revoked = true, updated_at = :now where id = :id"),
            {"now": _now_iso(), "id": session_id},
        )


def revoke_user_sessions(user_id: str) -> int:
    with _eng().begin() as cx:
        res = cx.execute(
            text(
                "update auth_sessions set revoked = true, updated_at = :now "
                "where user_id = :uid and not revoked"
            ),
            {"now": _now_iso(), "uid": user_id},
        )
    return res.rowcount or 0


def revoke_all_refresh_tokens(user_id: str) -> int:
    """Revoke every active refresh-token session for the given user."""
    return revoke_user_sessions(user_id)


# ─── Password reset + email verification tokens ──────────────────────


def _token_key(token_hash: str) -> str:
    return token_hash[:128]


def _upsert_token(table: str, *, user_id: str, token_hash: str, expires_at: datetime) -> None:
    with _eng().begin() as cx:
        cx.execute(text(f"delete from {table} where user_id = :uid"), {"uid": user_id})
        cx.execute(
            text(
                f"""
                insert into {table} (token_hash, user_id, expires_at, created_at)
                values (:th, :uid, :exp, :now)
                on conflict (token_hash) do update set
                    user_id = excluded.user_id, expires_at = excluded.expires_at,
                    created_at = excluded.created_at
                """
            ),
            {
                "th": _token_key(token_hash),
                "uid": user_id,
                "exp": expires_at.astimezone(timezone.utc).isoformat(),
                "now": _now_iso(),
            },
        )


def _consume_token(table: str, token_hash: str) -> Optional[dict]:
    with _eng().begin() as cx:
        row = cx.execute(
            text(f"delete from {table} where token_hash = :th returning *"),
            {"th": _token_key(token_hash)},
        ).fetchone()
    if not row:
        return None
    data = dict(row._mapping)
    expires_at = _parse_iso(data.get("expires_at"))
    if expires_at and expires_at < datetime.now(tz=timezone.utc):
        return None
    return {"user_id": data.get("user_id")}


def upsert_password_reset(*, user_id: str, token_hash: str, expires_at: datetime) -> None:
    _upsert_token("password_resets", user_id=user_id, token_hash=token_hash, expires_at=expires_at)


def consume_password_reset(token_hash: str) -> Optional[dict]:
    return _consume_token("password_resets", token_hash)


def upsert_email_verification(*, user_id: str, token_hash: str, expires_at: datetime) -> None:
    _upsert_token("email_verifications", user_id=user_id, token_hash=token_hash, expires_at=expires_at)


def consume_email_verification(token_hash: str) -> Optional[dict]:
    return _consume_token("email_verifications", token_hash)


def mark_email_verified(user_id: str) -> None:
    now = _now_iso()
    with _eng().begin() as cx:
        cx.execute(
            text(
                "update users set email_verified = true, email_verified_at = :now, updated_at = :now "
                "where id = :id"
            ),
            {"now": now, "id": user_id},
        )


# ─── Account deletion (full cascade) ─────────────────────────────────


def delete_user(user_id: str) -> dict:
    """Permanently delete a user and every record we hold for them (hard delete)."""
    counts: dict[str, int] = {}
    counts["auth_sessions_revoked"] = revoke_user_sessions(user_id)

    user_owned = [
        ("user_preferences", "user_id"),
        ("user_alert_settings", "user_id"),
        ("user_alerts", "user_id"),
        ("user_resumes", "user_id"),
        ("user_applications", "user_id"),
        ("auth_sessions", "user_id"),
        ("password_resets", "user_id"),
        ("email_verifications", "user_id"),
        ("agreements", "user_id"),
        ("role_requests", "user_id"),
    ]
    with _eng().begin() as cx:
        for table, field in user_owned:
            res = cx.execute(
                text(f"delete from {table} where {field} = :uid"), {"uid": user_id}
            )
            counts[table] = res.rowcount or 0
        res = cx.execute(text("delete from users where id = :uid"), {"uid": user_id})
        counts["users"] = res.rowcount or 0
    return counts


# ─── Legal agreements ────────────────────────────────────────────────


def record_agreement(
    *,
    user_id: str,
    email: str,
    version: str,
    documents: list[str] | None = None,
    ip_address: str = "",
    user_agent: str = "",
    accepted: bool = True,
) -> dict:
    agreement_id = f"agr_{uuid.uuid4().hex[:12]}"
    record = {
        "id": agreement_id,
        "user_id": user_id,
        "email": (email or "").lower(),
        "version": version,
        "documents": documents or ["terms", "privacy"],
        "accepted": accepted,
        "ip_address": ip_address,
        "user_agent": user_agent,
        "created_at": _now_iso(),
    }
    with _eng().begin() as cx:
        cx.execute(
            text(
                """
                insert into agreements (id, user_id, email, version, documents, accepted,
                                        ip_address, user_agent, created_at)
                values (:id, :user_id, :email, :version, cast(:documents as jsonb),
                        :accepted, :ip_address, :user_agent, :created_at)
                """
            ),
            {**record, "documents": _jd(record["documents"])},
        )
    return record


def list_agreements(limit: int = 1000) -> list[dict]:
    with _eng().begin() as cx:
        rows = cx.execute(text("select * from agreements limit :n"), {"n": limit}).fetchall()
    return [_row_dict(r) for r in rows]


def get_agreement_for_user(user_id: str) -> Optional[dict]:
    with _eng().begin() as cx:
        row = cx.execute(
            text(
                "select * from agreements where user_id = :uid order by created_at desc limit 1"
            ),
            {"uid": user_id},
        ).fetchone()
    return _row_dict(row) if row else None


# ─── Role requests ───────────────────────────────────────────────────


def create_role_request(
    *,
    user_id: str,
    email: str,
    role: str,
    country: str = "",
    note: str = "",
) -> dict:
    request_id = f"rr_{uuid.uuid4().hex[:12]}"
    now = _now_iso()
    record = {
        "id": request_id,
        "user_id": user_id,
        "email": (email or "").lower(),
        "role": role.strip(),
        "country": country.strip(),
        "note": note.strip()[:1000],
        "status": "pending",
        "admin_note": "",
        "decided_by": "",
        "decided_at": "",
        "created_at": now,
        "updated_at": now,
    }
    with _eng().begin() as cx:
        cx.execute(
            text(
                """
                insert into role_requests (id, user_id, email, "role", country, note, status,
                                           admin_note, decided_by, decided_at, created_at, updated_at)
                values (:id, :user_id, :email, :role, :country, :note, :status,
                        :admin_note, :decided_by, :decided_at, :created_at, :updated_at)
                """
            ),
            record,
        )
    return record


def list_role_requests(
    *, status: Optional[str] = None, user_id: Optional[str] = None, limit: int = 500
) -> list[dict]:
    where, params = [], {"n": limit}
    if status:
        where.append("status = :status")
        params["status"] = status
    if user_id:
        where.append("user_id = :uid")
        params["uid"] = user_id
    clause = f"where {' and '.join(where)}" if where else ""
    with _eng().begin() as cx:
        rows = cx.execute(
            text(f"select * from role_requests {clause} order by created_at desc limit :n"),
            params,
        ).fetchall()
    return [_row_dict(r) for r in rows]


def get_role_request(request_id: str) -> Optional[dict]:
    with _eng().begin() as cx:
        row = cx.execute(
            text("select * from role_requests where id = :id"), {"id": request_id}
        ).fetchone()
    return _row_dict(row) if row else None


_ROLE_REQUEST_COLUMNS = {
    "user_id", "email", "role", "country", "note", "status",
    "admin_note", "decided_by", "decided_at",
}


def update_role_request(request_id: str, fields: dict[str, Any]) -> Optional[dict]:
    if not get_role_request(request_id):
        return None
    sets, params = [], {"_id": request_id, "_now": _now_iso()}
    extra_updates = {}
    for k, v in fields.items():
        if k in _ROLE_REQUEST_COLUMNS:
            sets.append(f'"{k}" = :{k}')
            params[k] = v
        else:
            extra_updates[k] = v
    if extra_updates:
        sets.append("extra = extra || cast(:_extra as jsonb)")
        params["_extra"] = _jd(extra_updates)
    sets.append("updated_at = :_now")
    with _eng().begin() as cx:
        cx.execute(text(f"update role_requests set {', '.join(sets)} where id = :_id"), params)
    return get_role_request(request_id)


def count_role_requests(status: Optional[str] = None) -> int:
    q = "select count(*) from role_requests"
    params = {}
    if status:
        q += " where status = :status"
        params["status"] = status
    with _eng().begin() as cx:
        return int(cx.execute(text(q), params).scalar() or 0)


# ─── Admin audit / application event log ─────────────────────────────


def record_event(
    *,
    kind: str,
    label: str = "",
    user_id: str = "",
    email: str = "",
    actor: str = "",
    level: str = "info",
    meta: dict | None = None,
) -> dict:
    event_id = f"evt_{uuid.uuid4().hex[:12]}"
    record = {
        "id": event_id,
        "kind": kind,
        "label": label or kind.replace("_", " ").title(),
        "user_id": user_id,
        "email": (email or "").lower(),
        "actor": actor,
        "level": level,
        "meta": meta or {},
        "created_at": _now_iso(),
    }
    try:
        with _eng().begin() as cx:
            cx.execute(
                text(
                    """
                    insert into admin_events (id, kind, label, user_id, email, actor, level, meta, created_at)
                    values (:id, :kind, :label, :user_id, :email, :actor, :level,
                            cast(:meta as jsonb), :created_at)
                    """
                ),
                {**record, "meta": _jd(record["meta"])},
            )
    except Exception:  # never let audit logging break the request path
        pass
    return record


def list_events(
    *, limit: int = 300, user_id: Optional[str] = None, kind: Optional[str] = None
) -> list[dict]:
    where, params = [], {"n": limit}
    if user_id:
        where.append("user_id = :uid")
        params["uid"] = user_id
    if kind:
        where.append("kind = :kind")
        params["kind"] = kind
    clause = f"where {' and '.join(where)}" if where else ""
    with _eng().begin() as cx:
        rows = cx.execute(
            text(f"select * from admin_events {clause} order by created_at desc limit :n"),
            params,
        ).fetchall()
    return [_row_dict(r) for r in rows]


# ─── Waitlist (private-beta invite gate) ─────────────────────────────


def _waitlist_id(email: str) -> str:
    import hashlib

    return hashlib.sha256(email.strip().lower().encode("utf-8")).hexdigest()[:32]


def add_waitlist_entry(
    email: str,
    *,
    name: Optional[str] = None,
    source: str = "invite_gate",
    ip_address: str = "",
    user_agent: str = "",
) -> dict:
    normalized = email.strip().lower()
    now = _now_iso()
    params = {
        "id": _waitlist_id(normalized),
        "email": normalized,
        "name": (name or "").strip()[:120],
        "source": source,
        "last_ip": ip_address[:64],
        "last_user_agent": user_agent[:256],
        "now": now,
    }
    with _eng().begin() as cx:
        row = cx.execute(
            text(
                """
                insert into waitlist (id, email, name, source, last_ip, last_user_agent,
                                      notified, created_at, updated_at)
                values (:id, :email, :name, :source, :last_ip, :last_user_agent,
                        false, :now, :now)
                on conflict (id) do update set
                    name = excluded.name, source = excluded.source,
                    last_ip = excluded.last_ip, last_user_agent = excluded.last_user_agent,
                    updated_at = excluded.updated_at
                returning *
                """
            ),
            params,
        ).fetchone()
    data = _row_dict(row)
    data.pop("id", None)  # firestore version did not include the doc id
    return data


def list_waitlist(limit: int = 1000) -> list[dict]:
    with _eng().begin() as cx:
        rows = cx.execute(
            text("select * from waitlist order by created_at limit :n"), {"n": limit}
        ).fetchall()
    out = []
    for r in rows:
        d = _row_dict(r)
        d.pop("id", None)
        out.append(d)
    return out


def count_waitlist() -> int:
    with _eng().begin() as cx:
        return int(cx.execute(text("select count(*) from waitlist")).scalar() or 0)


# ─── User feedback ───────────────────────────────────────────────────

VALID_FEEDBACK_CATEGORIES = {"general", "bug", "feature_request", "job_quality", "ux", "pricing", "other"}


def create_feedback(
    *,
    user_id: str,
    email: str = "",
    rating: int,
    category: str = "general",
    message: str = "",
    page: str = "",
    user_agent: str = "",
) -> dict:
    fid = f"fb_{uuid.uuid4().hex[:12]}"
    rating = max(1, min(5, int(rating)))
    cat = category if category in VALID_FEEDBACK_CATEGORIES else "other"
    record: dict[str, Any] = {
        "id": fid,
        "user_id": user_id,
        "email": (email or "").lower(),
        "rating": rating,
        "category": cat,
        "message": (message or "").strip()[:4000],
        "page": (page or "")[:200],
        "user_agent": (user_agent or "")[:256],
        "status": "new",
        "created_at": _now_iso(),
    }
    with _eng().begin() as cx:
        cx.execute(
            text(
                """
                insert into user_feedback (id, user_id, email, rating, category, message,
                                           page, user_agent, status, created_at)
                values (:id, :user_id, :email, :rating, :category, :message,
                        :page, :user_agent, :status, :created_at)
                """
            ),
            record,
        )
    return record


def list_feedback(*, limit: int = 500, category: Optional[str] = None) -> list[dict]:
    where, params = "", {"n": limit}
    if category:
        where = "where category = :cat"
        params["cat"] = category
    with _eng().begin() as cx:
        rows = cx.execute(
            text(f"select * from user_feedback {where} order by created_at desc limit :n"),
            params,
        ).fetchall()
    return [_row_dict(r) for r in rows]


def feedback_stats() -> dict:
    with _eng().begin() as cx:
        rows = cx.execute(text("select rating, category from user_feedback")).fetchall()
    total = len(rows)
    dist = {str(i): 0 for i in range(1, 6)}
    by_category: dict[str, int] = {}
    rating_sum = 0
    for r in rows:
        rating = int(r._mapping.get("rating") or 0)
        if 1 <= rating <= 5:
            dist[str(rating)] += 1
            rating_sum += rating
        c = str(r._mapping.get("category") or "other")
        by_category[c] = by_category.get(c, 0) + 1
    avg = round(rating_sum / total, 2) if total else 0.0
    return {
        "total": total,
        "average_rating": avg,
        "distribution": dist,
        "by_category": by_category,
    }


def set_feedback_status(feedback_id: str, status: str) -> Optional[dict]:
    if status not in {"new", "reviewed", "resolved"}:
        return None
    with _eng().begin() as cx:
        row = cx.execute(
            text(
                "update user_feedback set status = :st, updated_at = :now where id = :id returning *"
            ),
            {"st": status, "now": _now_iso(), "id": feedback_id},
        ).fetchone()
    return _row_dict(row) if row else None

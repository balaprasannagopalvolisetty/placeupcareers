"""
PlaceUp Career — User & related data store (SQLite-backed).

Provides synchronous helpers around the `users`, `user_preferences`,
`user_alerts`, `user_alert_settings`, and `user_resumes` tables that the
SQLiteClient initializes. Endpoints call these helpers directly so we
don't have to widen the SQLite client interface for every CRUD call.

In production, swap the implementation for Firestore by importing
`get_firestore_db()` from `app.db.firebase` and re-implementing the
same methods. The signatures match what the API layer expects.
"""
from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from app.db.local_db import DB_PATH, SQLiteClient


def _conn() -> sqlite3.Connection:
    # Ensure tables exist by touching the SQLiteClient lazily.
    SQLiteClient()
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _row_to_dict(row: sqlite3.Row | None) -> dict | None:
    if row is None:
        return None
    return {key: row[key] for key in row.keys()}


# ─── Users ──────────────────────────────────────────────────────────────────


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
    conn = _conn()
    try:
        conn.execute(
            """
            INSERT INTO users (
                id, email, password_hash, first_name, last_name, plan,
                visa_status, experience_years, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                email.lower(),
                password_hash,
                first_name,
                last_name,
                plan,
                visa_status,
                experience_years,
                now,
                now,
            ),
        )
        # Seed a preferences row.
        conn.execute(
            """
            INSERT INTO user_preferences (user_id, updated_at, visa_status, experience_level)
            VALUES (?, ?, ?, ?)
            """,
            (user_id, now, visa_status, experience_years),
        )
        # Seed alert settings.
        conn.execute(
            "INSERT INTO user_alert_settings (user_id) VALUES (?)",
            (user_id,),
        )
        conn.commit()
    finally:
        conn.close()
    return get_user_by_id(user_id)  # type: ignore[return-value]


def get_user_by_id(user_id: str) -> Optional[dict]:
    conn = _conn()
    try:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return _row_to_dict(row)
    finally:
        conn.close()


def get_user_by_email(email: str) -> Optional[dict]:
    conn = _conn()
    try:
        row = conn.execute(
            "SELECT * FROM users WHERE email = ?",
            (email.lower(),),
        ).fetchone()
        return _row_to_dict(row)
    finally:
        conn.close()


def update_user_profile(user_id: str, fields: dict[str, Any]) -> Optional[dict]:
    allowed = {
        "first_name", "last_name", "phone", "location", "visa_status",
        "experience_years", "current_role", "summary",
        "linkedin_url", "github_url", "portfolio_url", "plan",
    }
    sets = {k: v for k, v in fields.items() if k in allowed}
    if not sets:
        return get_user_by_id(user_id)

    sets["updated_at"] = _now_iso()
    set_clause = ", ".join(f"{k} = ?" for k in sets.keys())
    values = list(sets.values()) + [user_id]
    conn = _conn()
    try:
        conn.execute(f"UPDATE users SET {set_clause} WHERE id = ?", values)
        conn.commit()
    finally:
        conn.close()
    return get_user_by_id(user_id)


def set_user_password(user_id: str, password_hash: str) -> None:
    conn = _conn()
    try:
        conn.execute(
            "UPDATE users SET password_hash = ?, updated_at = ? WHERE id = ?",
            (password_hash, _now_iso(), user_id),
        )
        conn.commit()
    finally:
        conn.close()


# ─── Preferences ────────────────────────────────────────────────────────────


def get_preferences(user_id: str) -> dict:
    conn = _conn()
    try:
        row = conn.execute(
            "SELECT * FROM user_preferences WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        if row is None:
            now = _now_iso()
            conn.execute(
                "INSERT INTO user_preferences (user_id, updated_at) VALUES (?, ?)",
                (user_id, now),
            )
            conn.commit()
            row = conn.execute(
                "SELECT * FROM user_preferences WHERE user_id = ?",
                (user_id,),
            ).fetchone()
        return _row_to_dict(row) or {}
    finally:
        conn.close()


def update_preferences(user_id: str, fields: dict[str, Any]) -> dict:
    allowed = {
        "job_preferences",
        "notification_new_jobs", "notification_daily_digest",
        "notification_weekly_summary", "notification_ats_updates",
        "notification_marketing_emails",
        "visa_status", "experience_level",
    }
    sets = {k: v for k, v in fields.items() if k in allowed}
    sets["updated_at"] = _now_iso()
    # Coerce booleans into INTEGER.
    for key in (
        "notification_new_jobs", "notification_daily_digest",
        "notification_weekly_summary", "notification_ats_updates",
        "notification_marketing_emails",
    ):
        if key in sets:
            sets[key] = int(bool(sets[key]))

    # Ensure a row exists.
    get_preferences(user_id)

    set_clause = ", ".join(f"{k} = ?" for k in sets.keys())
    values = list(sets.values()) + [user_id]
    conn = _conn()
    try:
        conn.execute(f"UPDATE user_preferences SET {set_clause} WHERE user_id = ?", values)
        conn.commit()
    finally:
        conn.close()
    return get_preferences(user_id)


# ─── Alerts ─────────────────────────────────────────────────────────────────


def list_alerts(user_id: str, limit: int = 100) -> list[dict]:
    conn = _conn()
    try:
        rows = conn.execute(
            "SELECT * FROM user_alerts WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
        return [_row_to_dict(r) for r in rows if r]  # type: ignore[misc]
    finally:
        conn.close()


def create_alert(user_id: str, payload: dict) -> dict:
    alert_id = f"a_{uuid.uuid4().hex[:10]}"
    now = _now_iso()
    conn = _conn()
    try:
        conn.execute(
            """
            INSERT INTO user_alerts (
                id, user_id, title, company, location, salary, match_score,
                visa, message, unread, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
            """,
            (
                alert_id,
                user_id,
                payload.get("title", ""),
                payload.get("company", ""),
                payload.get("location", ""),
                payload.get("salary", ""),
                int(payload.get("match", payload.get("match_score", 0)) or 0),
                payload.get("visa", ""),
                payload.get("message"),
                now,
            ),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM user_alerts WHERE id = ?", (alert_id,)).fetchone()
        return _row_to_dict(row) or {}
    finally:
        conn.close()


def mark_alert_read(user_id: str, alert_id: str) -> Optional[dict]:
    conn = _conn()
    try:
        conn.execute(
            "UPDATE user_alerts SET unread = 0 WHERE id = ? AND user_id = ?",
            (alert_id, user_id),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM user_alerts WHERE id = ? AND user_id = ?",
            (alert_id, user_id),
        ).fetchone()
        return _row_to_dict(row)
    finally:
        conn.close()


def mark_all_alerts_read(user_id: str) -> int:
    conn = _conn()
    try:
        cur = conn.execute(
            "UPDATE user_alerts SET unread = 0 WHERE user_id = ? AND unread = 1",
            (user_id,),
        )
        conn.commit()
        return cur.rowcount
    finally:
        conn.close()


def delete_alert(user_id: str, alert_id: str) -> int:
    conn = _conn()
    try:
        cur = conn.execute(
            "DELETE FROM user_alerts WHERE id = ? AND user_id = ?",
            (alert_id, user_id),
        )
        conn.commit()
        return cur.rowcount
    finally:
        conn.close()


def get_alert_settings(user_id: str) -> dict:
    conn = _conn()
    try:
        row = conn.execute(
            "SELECT * FROM user_alert_settings WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        if row is None:
            conn.execute("INSERT INTO user_alert_settings (user_id) VALUES (?)", (user_id,))
            conn.commit()
            row = conn.execute(
                "SELECT * FROM user_alert_settings WHERE user_id = ?",
                (user_id,),
            ).fetchone()
        d = _row_to_dict(row) or {}
        # Coerce ints to bool.
        for key in ("email_alerts", "daily_digest", "weekly_report"):
            d[key] = bool(d.get(key))
        return d
    finally:
        conn.close()


def update_alert_settings(user_id: str, payload: dict) -> dict:
    sets = {}
    for key in ("email_alerts", "daily_digest", "weekly_report"):
        if key in payload:
            sets[key] = int(bool(payload[key]))
    if not sets:
        return get_alert_settings(user_id)

    # Ensure row exists.
    get_alert_settings(user_id)

    set_clause = ", ".join(f"{k} = ?" for k in sets.keys())
    values = list(sets.values()) + [user_id]
    conn = _conn()
    try:
        conn.execute(f"UPDATE user_alert_settings SET {set_clause} WHERE user_id = ?", values)
        conn.commit()
    finally:
        conn.close()
    return get_alert_settings(user_id)


# ─── Resumes ────────────────────────────────────────────────────────────────


def list_resumes(user_id: str) -> list[dict]:
    conn = _conn()
    try:
        rows = conn.execute(
            "SELECT * FROM user_resumes WHERE user_id = ? ORDER BY uploaded_at DESC",
            (user_id,),
        ).fetchall()
        out = []
        for r in rows:
            d = _row_to_dict(r) or {}
            d["active"] = bool(d.get("active"))
            out.append(d)
        return out
    finally:
        conn.close()


def create_resume(
    user_id: str,
    *,
    name: str,
    score: int,
    size_bytes: int,
    storage_path: Optional[str] = None,
    active: bool = False,
) -> dict:
    resume_id = f"r_{uuid.uuid4().hex[:10]}"
    now = _now_iso()
    conn = _conn()
    try:
        if active:
            conn.execute("UPDATE user_resumes SET active = 0 WHERE user_id = ?", (user_id,))
        conn.execute(
            """
            INSERT INTO user_resumes (
                id, user_id, name, uploaded_at, score, size_bytes, active, storage_path
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (resume_id, user_id, name, now, int(score), int(size_bytes), int(bool(active)), storage_path),
        )
        conn.commit()
    finally:
        conn.close()
    return next((r for r in list_resumes(user_id) if r["id"] == resume_id), {})


def set_active_resume(user_id: str, resume_id: str) -> Optional[dict]:
    conn = _conn()
    try:
        conn.execute("UPDATE user_resumes SET active = 0 WHERE user_id = ?", (user_id,))
        cur = conn.execute(
            "UPDATE user_resumes SET active = 1 WHERE id = ? AND user_id = ?",
            (resume_id, user_id),
        )
        conn.commit()
        if cur.rowcount == 0:
            return None
    finally:
        conn.close()
    return next((r for r in list_resumes(user_id) if r["id"] == resume_id), None)


def delete_resume(user_id: str, resume_id: str) -> int:
    conn = _conn()
    try:
        cur = conn.execute(
            "DELETE FROM user_resumes WHERE id = ? AND user_id = ?",
            (resume_id, user_id),
        )
        conn.commit()
        return cur.rowcount
    finally:
        conn.close()


def count_user_applications(user_id: str) -> int:
    conn = _conn()
    try:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM user_applications WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        return int(row["n"]) if row else 0
    finally:
        conn.close()

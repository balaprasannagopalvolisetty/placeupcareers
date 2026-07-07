"""Firestore-backed waitlist store for the private-beta invite gate.

People who don't have an invite code leave their email here so we can
notify them at public launch. Doc IDs are a SHA-256 of the normalized
email, which makes writes idempotent — resubmitting the same address
updates the existing entry instead of duplicating it, and we never leak
"already registered" to the caller.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any, Optional

from app.config import settings

if settings.user_database_backend != "postgres":
    from app.db.firestore_user_store import _client

_COLLECTION = "waitlist"


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _doc_id(email: str) -> str:
    return hashlib.sha256(email.strip().lower().encode("utf-8")).hexdigest()[:32]


def add_waitlist_entry(
    email: str,
    *,
    name: Optional[str] = None,
    source: str = "invite_gate",
    ip_address: str = "",
    user_agent: str = "",
) -> dict:
    """Idempotent upsert of a waitlist signup keyed by normalized email."""
    normalized = email.strip().lower()
    ref = _client().collection(_COLLECTION).document(_doc_id(normalized))
    snapshot = ref.get()
    now = _now_iso()
    data: dict[str, Any] = {
        "email": normalized,
        "name": (name or "").strip()[:120],
        "source": source,
        "updated_at": now,
        # Keep only coarse request metadata for abuse triage; no tracking.
        "last_ip": ip_address[:64],
        "last_user_agent": user_agent[:256],
        "notified": False,
    }
    if snapshot.exists:
        existing = snapshot.to_dict() or {}
        data["created_at"] = existing.get("created_at", now)
        data["notified"] = bool(existing.get("notified", False))
    else:
        data["created_at"] = now
    ref.set(data)
    return data


def list_waitlist(limit: int = 1000) -> list[dict]:
    docs = (
        _client()
        .collection(_COLLECTION)
        .order_by("created_at")
        .limit(limit)
        .stream()
    )
    return [doc.to_dict() or {} for doc in docs]


def count_waitlist() -> int:
    return sum(1 for _ in _client().collection(_COLLECTION).stream())


# ─── Supabase/Postgres backend override ──────────────────────────────
# When USER_DATABASE_BACKEND=postgres the Firestore implementations above
# are replaced by the Postgres ones (same signatures, same return shapes).
if settings.user_database_backend == "postgres":
    from app.db.postgres_user_store import (  # noqa: F811, E402
        add_waitlist_entry,
        count_waitlist,
        list_waitlist,
    )

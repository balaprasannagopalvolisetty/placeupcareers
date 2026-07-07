"""Firestore-backed user feedback store.

Users submit a rating (1-5), a category, and an optional comment. Admins read
the list and aggregate stats in the admin portal. Kept separate from the user
store so it's easy to reason about and export.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from app.config import settings

if settings.user_database_backend != "postgres":
    from app.db.firestore_user_store import _client

_COLLECTION = "user_feedback"

VALID_CATEGORIES = {"general", "bug", "feature_request", "job_quality", "ux", "pricing", "other"}


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


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
    cat = category if category in VALID_CATEGORIES else "other"
    record: dict[str, Any] = {
        "id": fid,
        "user_id": user_id,
        "email": (email or "").lower(),
        "rating": rating,
        "category": cat,
        "message": (message or "").strip()[:4000],
        "page": (page or "")[:200],
        "user_agent": (user_agent or "")[:256],
        "status": "new",          # new | reviewed | resolved
        "created_at": _now_iso(),
    }
    _client().collection(_COLLECTION).document(fid).set(record)
    return record


def list_feedback(*, limit: int = 500, category: Optional[str] = None) -> list[dict]:
    q = _client().collection(_COLLECTION).order_by("created_at", direction="DESCENDING")
    if category:
        q = q.where("category", "==", category)
    return [d.to_dict() or {} for d in q.limit(limit).stream()]


def feedback_stats() -> dict:
    """Aggregate for the admin portal: count, average rating, distribution
    (1-5) and per-category counts."""
    items = [d.to_dict() or {} for d in _client().collection(_COLLECTION).stream()]
    total = len(items)
    dist = {str(i): 0 for i in range(1, 6)}
    by_category: dict[str, int] = {}
    rating_sum = 0
    for it in items:
        r = int(it.get("rating") or 0)
        if 1 <= r <= 5:
            dist[str(r)] += 1
            rating_sum += r
        c = str(it.get("category") or "other")
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
    ref = _client().collection(_COLLECTION).document(feedback_id)
    snap = ref.get()
    if not snap.exists:
        return None
    ref.update({"status": status, "updated_at": _now_iso()})
    return ref.get().to_dict()


# ─── Supabase/Postgres backend override ──────────────────────────────
# When USER_DATABASE_BACKEND=postgres the Firestore implementations above
# are replaced by the Postgres ones (same signatures, same return shapes).
if settings.user_database_backend == "postgres":
    from app.db.postgres_user_store import (  # noqa: F811, E402
        create_feedback,
        feedback_stats,
        list_feedback,
        set_feedback_status,
    )

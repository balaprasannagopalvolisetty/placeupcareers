"""
Per-user alert feed and alert preference endpoints.

Backed by the SQLite `user_alerts` and `user_alert_settings` tables.
Endpoints require a valid JWT bearer token.
"""
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Body, Depends, HTTPException

from app.db import user_store
from app.dependencies import get_db
from app.models.alert import AlertCreateRequest, AlertItem, AlertSetting
from app.security import current_user_id

router = APIRouter(prefix="/alerts", tags=["Alerts"])


def _humanize(iso: Optional[str]) -> str:
    if not iso:
        return "just now"
    try:
        ts = datetime.fromisoformat(iso)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        delta = datetime.now(timezone.utc) - ts
        s = int(delta.total_seconds())
        if s < 60:
            return f"{s}s ago"
        if s < 3600:
            return f"{s // 60}m ago"
        if s < 86400:
            return f"{s // 3600}h ago"
        return f"{s // 86400}d ago"
    except Exception:
        return "recently"


def _row_to_alert(row: dict) -> AlertItem:
    match_score = int(row.get("match_score") or 0)
    return AlertItem(
        id=str(row.get("id")),
        title=row.get("title") or "",
        company=row.get("company") or "",
        location=row.get("location") or "",
        salary=row.get("salary") or "",
        match=match_score,
        match_score=match_score,
        visa=row.get("visa") or "",
        time=_humanize(row.get("created_at")),
        message=row.get("message"),
        created_at=row.get("created_at"),
        unread=bool(row.get("unread")),
    )


@router.get("", response_model=List[AlertItem])
async def get_alerts(user_id: str = Depends(current_user_id)):
    return [_row_to_alert(r) for r in user_store.list_alerts(user_id)]


@router.get("/digest")
async def alerts_digest(user_id: str = Depends(current_user_id), db=Depends(get_db)):
    """Personalized alert digest: how many NEW positions landed in the database
    for each of the user's target roles (last 24h / 7d). Powers the summary
    band at the top of the Alerts page; "top picks" come from /jobs/top-matches.
    """
    from datetime import timedelta

    from app.api.jobs import _taxonomy_terms

    prefs = user_store.get_preferences(user_id)
    roles = [str(r).strip() for r in (prefs.get("target_roles") or []) if str(r).strip()][:6]
    now = datetime.now(timezone.utc)
    since_24h = now - timedelta(hours=24)
    since_7d = now - timedelta(days=7)

    role_counts: list[dict] = []
    total_24h = 0
    total_7d = 0
    for role in roles:
        try:
            terms = _taxonomy_terms(None, role) or [role]
        except Exception:
            terms = [role]
        try:
            # first_seen_since (not seen_since): the scraper re-sees active jobs
            # every cycle, so last_seen_at is recent for almost everything and
            # made 24h ~= 7d ~= total. first_seen_at counts genuinely NEW rows.
            count_24h = await db.count_jobs(filters={"status": "active", "title_terms": terms, "first_seen_since": since_24h})
            count_7d = await db.count_jobs(filters={"status": "active", "title_terms": terms, "first_seen_since": since_7d})
        except Exception:
            count_24h, count_7d = 0, 0
        total_24h += count_24h
        total_7d += count_7d
        role_counts.append({"role": role, "new_24h": count_24h, "new_7d": count_7d})

    return {
        "generated_at": now.isoformat(),
        "target_roles": role_counts,
        "total_new_24h": total_24h,
        "total_new_7d": total_7d,
        "has_target_roles": bool(roles),
    }


@router.get("/added-series")
async def alerts_added_series(
    days: int = 14,
    scope: str = "targets",
    user_id: str = Depends(current_user_id),
    db=Depends(get_db),
):
    """Daily count of NEW positions added to the database (by first_seen_at).

    Powers the interactive Alerts chart. ``scope=targets`` limits to the user's
    saved target roles; ``scope=all`` counts every new active posting. Always
    returns a dense, zero-filled series so the chart has no gaps.
    """
    days = max(7, min(int(days), 60))
    title_terms: list[str] | None = None
    if scope != "all":
        from app.api.jobs import _taxonomy_terms

        prefs = user_store.get_preferences(user_id)
        roles = [str(r).strip() for r in (prefs.get("target_roles") or []) if str(r).strip()][:8]
        terms: list[str] = []
        for role in roles:
            try:
                terms.extend(_taxonomy_terms(None, role) or [role])
            except Exception:
                terms.append(role)
        title_terms = list(dict.fromkeys(terms)) or None

    try:
        series = await db.jobs_added_daily(days=days, title_terms=title_terms)
    except Exception:
        series = []
    total = sum(int(point.get("count") or 0) for point in series)
    peak = max((int(point.get("count") or 0) for point in series), default=0)
    return {
        "days": days,
        "scope": "targets" if title_terms else "all",
        "series": series,
        "total_added": total,
        "peak_day": peak,
    }


@router.post("", response_model=AlertItem)
async def create_alert(
    payload: AlertCreateRequest = Body(...),
    user_id: str = Depends(current_user_id),
):
    row = user_store.create_alert(user_id, payload.model_dump())
    return _row_to_alert(row)


@router.patch("/{alert_id}/read", response_model=AlertItem)
async def mark_alert_read(alert_id: str, user_id: str = Depends(current_user_id)):
    row = user_store.mark_alert_read(user_id, alert_id)
    if not row:
        raise HTTPException(status_code=404, detail="Alert not found")
    return _row_to_alert(row)


@router.post("/read-all")
async def mark_all_alerts_read(user_id: str = Depends(current_user_id)):
    updated = user_store.mark_all_alerts_read(user_id)
    return {"updated": updated}


@router.delete("/{alert_id}")
async def delete_alert(alert_id: str, user_id: str = Depends(current_user_id)):
    n = user_store.delete_alert(user_id, alert_id)
    if n == 0:
        raise HTTPException(status_code=404, detail="Alert not found")
    return {"deleted": alert_id}


@router.get("/settings", response_model=AlertSetting)
async def get_alert_settings(user_id: str = Depends(current_user_id)):
    raw = user_store.get_alert_settings(user_id)
    return AlertSetting(
        email_alerts=bool(raw.get("email_alerts", True)),
        daily_digest=bool(raw.get("daily_digest", True)),
        weekly_report=bool(raw.get("weekly_report", False)),
    )


@router.put("/settings", response_model=AlertSetting)
async def update_alert_settings(
    settings: AlertSetting = Body(...),
    user_id: str = Depends(current_user_id),
):
    raw = user_store.update_alert_settings(user_id, settings.model_dump())
    return AlertSetting(
        email_alerts=bool(raw.get("email_alerts", True)),
        daily_digest=bool(raw.get("daily_digest", True)),
        weekly_report=bool(raw.get("weekly_report", False)),
    )

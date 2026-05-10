"""
Per-user alert feed and alert preference endpoints.

Backed by the SQLite `user_alerts` and `user_alert_settings` tables.
Endpoints require a valid JWT bearer token.
"""
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Body, Depends, HTTPException

from app.db import user_store
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
    return AlertItem(
        id=str(row.get("id")),
        title=row.get("title") or "",
        company=row.get("company") or "",
        location=row.get("location") or "",
        salary=row.get("salary") or "",
        match=int(row.get("match_score") or 0),
        visa=row.get("visa") or "",
        time=_humanize(row.get("created_at")),
        unread=bool(row.get("unread")),
    )


@router.get("", response_model=List[AlertItem])
async def get_alerts(user_id: str = Depends(current_user_id)):
    return [_row_to_alert(r) for r in user_store.list_alerts(user_id)]


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

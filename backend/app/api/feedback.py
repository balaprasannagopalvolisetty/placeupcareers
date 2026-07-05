"""User feedback submission endpoint.

Authenticated users submit a rating + optional comment. Admin reads live in
app/api/admin.py (require_admin_user). Zero-trust: this is a protected route,
so the middleware already requires a valid session; we additionally bind the
feedback to the caller's own user id from the token (never from the body).
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Body, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from app.db import feedback_store
from app.db import user_store
from app.security import current_user_id

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/feedback", tags=["Feedback"])


class FeedbackRequest(BaseModel):
    rating: int = Field(ge=1, le=5)
    category: str = Field(default="general", max_length=40)
    message: str = Field(default="", max_length=4000)
    page: str = Field(default="", max_length=200)


@router.post("")
async def submit_feedback(
    request: Request,
    payload: FeedbackRequest = Body(...),
    user_id: str = Depends(current_user_id),
):
    user = user_store.get_user_by_id(user_id) or {}
    try:
        record = feedback_store.create_feedback(
            user_id=user_id,
            email=str(user.get("email") or ""),
            rating=payload.rating,
            category=payload.category,
            message=payload.message,
            page=payload.page,
            user_agent=request.headers.get("user-agent", ""),
        )
    except Exception:
        logger.exception("feedback write failed for user=%s", user_id)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="We couldn't save your feedback right now. Please try again shortly.",
        )
    # Also drop an audit event so it shows in the activity log.
    try:
        user_store.record_event(
            kind="feedback",
            label=f"Feedback ({payload.rating}★)",
            user_id=user_id,
            email=str(user.get("email") or ""),
            meta={"category": record["category"], "rating": payload.rating},
        )
    except Exception:
        pass
    return {"ok": True, "message": "Thanks for the feedback!", "id": record["id"]}

"""Invite gate endpoints for the private beta.

Security model
--------------
- The invite code lives ONLY on the server (settings.invite_code, override
  via the INVITE_CODE env var). The frontend never embeds it, so it can't
  be scraped out of the JS bundle.
- A correct code mints a short-lived HMAC-signed invite token. That token
  (not the code) is what the frontend stores and what /api/auth/signup
  requires, so replaying old localStorage flags or hand-crafting requests
  doesn't work.
- Comparison is constant-time (secrets.compare_digest) to avoid timing
  side channels, and the /api/invite/* paths ride the strict "auth"
  rate-limit bucket (20/min/IP) to slow brute-force guessing.
- The waitlist endpoint answers identically whether the email is new or
  already enrolled, so it can't be used to enumerate signups.
"""
from __future__ import annotations

import logging
import secrets

from fastapi import APIRouter, Body, Depends, HTTPException, Request, status
from pydantic import BaseModel, EmailStr, Field

from app.config import settings
from app.db import waitlist_store
from app.security import create_invite_token, require_internal_api_key

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/invite", tags=["Invite"])


def _client_ip(request: Request) -> str:
    for header in ("cf-connecting-ip", "true-client-ip"):
        value = request.headers.get(header)
        if value:
            return value.strip()
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",", 1)[0].strip()
    return request.client.host if request.client else ""


class InviteValidateRequest(BaseModel):
    code: str = Field(min_length=1, max_length=128)


class WaitlistRequest(BaseModel):
    email: EmailStr
    name: str | None = Field(default=None, max_length=120)


@router.get("/status")
async def invite_status():
    """Lets the frontend know whether the gate is active (post-launch it
    just renders sign-in directly). Reveals nothing about the code."""
    return {"invite_required": settings.invite_gate_enabled}


@router.post("/validate")
async def validate_invite_code(request: Request, payload: InviteValidateRequest = Body(...)):
    supplied = payload.code.strip()
    if not settings.invite_gate_enabled:
        # Gate is off — everyone is "invited".
        return {"valid": True, "invite_token": create_invite_token()}
    if not settings.invite_code:
        logger.error("Invite gate enabled but INVITE_CODE is empty; rejecting all codes.")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Invite validation is temporarily unavailable.",
        )
    if secrets.compare_digest(supplied, settings.invite_code):
        logger.info("Invite code accepted ip=%s", _client_ip(request))
        return {"valid": True, "invite_token": create_invite_token()}
    logger.info("Invite code rejected ip=%s", _client_ip(request))
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="That invite code isn't valid.",
    )


@router.post("/waitlist")
async def join_waitlist(request: Request, payload: WaitlistRequest = Body(...)):
    try:
        waitlist_store.add_waitlist_entry(
            str(payload.email),
            name=payload.name,
            ip_address=_client_ip(request),
            user_agent=request.headers.get("user-agent", ""),
        )
    except Exception:
        logger.exception("waitlist write failed")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="We couldn't save your email right now. Please try again shortly.",
        )
    # Same response whether the email was new or already enrolled — no
    # enumeration signal.
    return {"ok": True, "message": "You're on the list. We'll email you when PlaceUp opens up."}


@router.get("/waitlist", dependencies=[Depends(require_internal_api_key)])
async def export_waitlist(limit: int = 1000):
    """Admin-only export (X-API-Key = INTERNAL_API_KEY) for launch emails."""
    entries = waitlist_store.list_waitlist(limit=min(max(limit, 1), 5000))
    return {"count": len(entries), "entries": entries}

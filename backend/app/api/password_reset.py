"""
Password reset + email verification endpoints.

These exist on day one for two reasons:

1. **OAuth consent screens** (Google, LinkedIn) require a public
   privacy policy URL and a working "forgot password" path before
   they will lift your app out of testing mode.
2. **Security baseline** — any production auth system without these
   flows forces support staff to reset passwords manually, which
   inevitably ends in someone emailing a plaintext password.

What's wired up
---------------
- `POST /api/auth/forgot-password`  → mints a short-lived token, stores
  the hash in Firestore, and *would* email it. The actual email send
  is a single TODO in `_send_email()` waiting on whichever provider
  you choose (SendGrid / Postmark / SES / Resend).
- `POST /api/auth/reset-password`   → verifies the token + new password.
- `POST /api/auth/verify-email`     → marks the address verified once
  the user clicks the link in their inbox.
- `POST /api/auth/resend-verification` → throttled re-send.

We never reveal whether an email is registered — the response is the
same shape whether the user exists or not. That blocks the common
account-enumeration recon technique.
"""

from __future__ import annotations

import hashlib
import logging
import os
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Body, HTTPException, status
from pydantic import BaseModel, EmailStr, Field

from app.db import user_store
from app.security import hash_password

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["Auth"])


# ─── Token policy ─────────────────────────────────────────────────────
RESET_TOKEN_TTL = timedelta(minutes=30)
VERIFY_TOKEN_TTL = timedelta(hours=48)


def _hash_token(raw: str) -> str:
    # Tokens go on the wire in plaintext (in the email link); on the
    # server side we only store sha256(token) so a DB dump doesn't
    # let an attacker mint password resets.
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _generate_token() -> str:
    return secrets.token_urlsafe(32)


def _frontend_base() -> str:
    return os.getenv("FRONTEND_URL", "https://placeupcareer.com").split(",", 1)[0].strip().rstrip("/")


def _send_email(to: str, subject: str, body: str) -> None:
    """Send a transactional email via the shared provider-agnostic sender.

    Configure delivery with EMAIL_PROVIDER + the matching key (see
    app/services/email.py). Failures are logged, not raised, so the
    forgot-password endpoint stays uniform (never reveals whether an
    address exists).
    """
    from app.services.email import send_email, EmailDeliveryError
    try:
        send_email(to, subject, html=body)
    except EmailDeliveryError as exc:
        logger.error("Password/verification email to %s failed: %s", to, exc)


# ─── Schemas ──────────────────────────────────────────────────────────

class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str = Field(..., min_length=20, max_length=128)
    new_password: str = Field(..., min_length=8, max_length=128)


class VerifyEmailRequest(BaseModel):
    token: str = Field(..., min_length=20, max_length=128)


class ResendVerificationRequest(BaseModel):
    email: EmailStr


class AckResponse(BaseModel):
    ok: bool = True
    message: str = (
        "If an account exists for that email, we've sent instructions. "
        "Check your inbox (and spam folder)."
    )


# ─── Endpoints ────────────────────────────────────────────────────────

@router.post("/auth/forgot-password", response_model=AckResponse)
@router.post("/forgot-password", response_model=AckResponse)
async def forgot_password(payload: ForgotPasswordRequest):
    """Initiate a password reset. Always returns 200 to prevent account
    enumeration — only attackers can tell the difference between
    "no such email" and "email sent"."""
    email = payload.email.lower().strip()
    user = user_store.get_user_by_email(email)
    if user:
        token = _generate_token()
        user_store.upsert_password_reset(
            user_id=user["id"],
            token_hash=_hash_token(token),
            expires_at=datetime.now(tz=timezone.utc) + RESET_TOKEN_TTL,
        )
        link = f"{_frontend_base()}/reset-password?token={token}"
        _send_email(
            to=email,
            subject="Reset your PlaceUp password",
            body=(
                f"<p>Hi {user.get('first_name') or 'there'},</p>"
                f"<p>Use this link to reset your password (expires in 30 minutes):</p>"
                f"<p><a href='{link}'>{link}</a></p>"
                "<p>If you didn't request this, you can ignore this email.</p>"
            ),
        )
    return AckResponse()


@router.post("/auth/reset-password")
@router.post("/reset-password")
async def reset_password(payload: ResetPasswordRequest):
    """Complete a password reset. Token may only be used once."""
    record = user_store.consume_password_reset(_hash_token(payload.token))
    if not record:
        # Same response shape for invalid + expired so timing can't be
        # used to distinguish the two cases.
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This password-reset link is invalid or has expired. Request a new one.",
        )
    user_store.set_user_password(record["user_id"], hash_password(payload.new_password))
    # Also revoke active refresh tokens — a leaked password may have
    # already been used to mint sessions we don't want left alive.
    try:
        user_store.revoke_all_refresh_tokens(record["user_id"])
    except AttributeError:
        logger.warning(
            "user_store.revoke_all_refresh_tokens not implemented; existing sessions remain valid."
        )
    return {"ok": True}


@router.post("/verify-email")
async def verify_email(payload: VerifyEmailRequest):
    """Mark the user's email verified."""
    record = user_store.consume_email_verification(_hash_token(payload.token))
    if not record:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Verification link is invalid or has expired.",
        )
    user_store.mark_email_verified(record["user_id"])
    return {"ok": True}


@router.post("/resend-verification", response_model=AckResponse)
async def resend_verification(payload: ResendVerificationRequest):
    """Re-send the verification email. Rate-limited by the global limiter."""
    email = payload.email.lower().strip()
    user = user_store.get_user_by_email(email)
    if user and not user.get("email_verified"):
        token = _generate_token()
        user_store.upsert_email_verification(
            user_id=user["id"],
            token_hash=_hash_token(token),
            expires_at=datetime.now(tz=timezone.utc) + VERIFY_TOKEN_TTL,
        )
        link = f"{_frontend_base()}/verify-email?token={token}"
        _send_email(
            to=email,
            subject="Confirm your PlaceUp email",
            body=(
                "<p>Welcome to PlaceUp Careers.</p>"
                f"<p>Tap the link to confirm this is your email address (expires in 48 hours):</p>"
                f"<p><a href='{link}'>{link}</a></p>"
            ),
        )
    return AckResponse()

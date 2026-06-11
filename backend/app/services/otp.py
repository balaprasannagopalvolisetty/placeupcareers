"""
Email one-time-passcode (OTP) service for signup verification and login MFA.

Production hardening:
- Codes are 6 random digits, stored only as a SHA-256 hash (never in plaintext).
- 10-minute expiry (configurable via OTP_CODE_TTL_MINUTES / settings).
- Max 5 verify attempts per code, then it's invalidated.
- Resend throttled to 1 per 30s per (email, purpose).
- Backed by Firestore collection `email_otps`, keyed by purpose+email.

Public API:
    request_otp(email, purpose) -> None        (raises OtpError on throttle/email fail)
    verify_otp(email, code, purpose) -> bool
"""
from __future__ import annotations

import hashlib
import logging
import secrets
from datetime import datetime, timedelta, timezone

from app.config import settings
from app.db.firestore_user_store import _client  # shared Firestore client
from app.services.email import send_email, EmailDeliveryError

logger = logging.getLogger(__name__)

_COLLECTION = "email_otps"
_MAX_ATTEMPTS = 5
_RESEND_COOLDOWN_SECONDS = 30
VALID_PURPOSES = {"signup", "login"}


class OtpError(RuntimeError):
    """Raised on throttling or delivery failure."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _doc_id(email: str, purpose: str) -> str:
    raw = f"{purpose}:{email.strip().lower()}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _hash_code(code: str) -> str:
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


def _ref(email: str, purpose: str):
    return _client().collection(_COLLECTION).document(_doc_id(email, purpose))


def _parse_dt(value) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def request_otp(email: str, purpose: str) -> None:
    """Generate, store, and email a fresh code. Raises OtpError on throttle/fail."""
    email = (email or "").strip().lower()
    if purpose not in VALID_PURPOSES:
        raise OtpError("Invalid OTP purpose")
    if not email:
        raise OtpError("Email is required")

    ref = _ref(email, purpose)
    snap = ref.get()
    if snap.exists:
        created = _parse_dt((snap.to_dict() or {}).get("created_at"))
        if created and (_now() - created).total_seconds() < _RESEND_COOLDOWN_SECONDS:
            raise OtpError("Please wait a few seconds before requesting another code.")

    code = f"{secrets.randbelow(1_000_000):06d}"
    ref.set({
        "email": email,
        "purpose": purpose,
        "code_hash": _hash_code(code),
        "attempts": 0,
        "created_at": _now().isoformat(),
        "expires_at": (_now() + timedelta(minutes=settings.otp_code_ttl_minutes)).isoformat(),
    })

    subject = "Your PlaceUp verification code"
    html = (
        f"<p>Your PlaceUp Career verification code is:</p>"
        f"<p style='font-size:28px;font-weight:700;letter-spacing:4px'>{code}</p>"
        f"<p>It expires in {settings.otp_code_ttl_minutes} minutes. "
        f"If you didn't request this, you can ignore this email.</p>"
    )
    try:
        send_email(email, subject, html=html, text=f"Your PlaceUp code is {code} (expires in {settings.otp_code_ttl_minutes} min).")
    except EmailDeliveryError as exc:
        logger.error("OTP email failed for %s: %s", email, exc)
        raise OtpError("Could not send the verification email. Please try again.") from exc


def verify_otp(email: str, code: str, purpose: str) -> bool:
    """Return True if the code is valid; consume it. False otherwise."""
    email = (email or "").strip().lower()
    code = (code or "").strip()
    if purpose not in VALID_PURPOSES or not email or not code:
        return False

    ref = _ref(email, purpose)
    snap = ref.get()
    if not snap.exists:
        return False
    data = snap.to_dict() or {}

    expires = _parse_dt(data.get("expires_at"))
    if not expires or _now() > expires:
        ref.delete()
        return False

    if int(data.get("attempts", 0)) >= _MAX_ATTEMPTS:
        ref.delete()
        return False

    if not secrets.compare_digest(_hash_code(code), str(data.get("code_hash", ""))):
        ref.update({"attempts": int(data.get("attempts", 0)) + 1})
        return False

    ref.delete()  # single-use
    return True

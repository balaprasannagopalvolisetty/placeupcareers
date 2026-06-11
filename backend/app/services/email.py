"""
Production email delivery — provider-agnostic.

This is the single send path for all transactional email (OTP codes, email
verification, password reset). Pick a provider with env vars; no code change
needed to switch:

    EMAIL_PROVIDER = resend | sendgrid | smtp | console
    EMAIL_FROM     = "PlaceUp <jobs@placeupcareer.com>"   (falls back to settings.email_from)

  Resend:   RESEND_API_KEY
  SendGrid: SENDGRID_API_KEY
  SMTP:     SMTP_HOST, SMTP_PORT, SMTP_USERNAME, SMTP_PASSWORD, SMTP_STARTTLS=true

Behaviour:
- Returns True on a confirmed send, raises EmailDeliveryError on misconfig or
  provider failure (callers that must guarantee delivery — e.g. OTP — surface a
  clear 5xx instead of silently "succeeding").
- "console" provider logs the message instead of sending; intended ONLY for
  local dev. In production (`settings.is_production`) an unconfigured provider
  raises, so you can never ship a silently-dead email path.
"""
from __future__ import annotations

import logging
import os
import smtplib
from email.message import EmailMessage
from typing import Optional

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


class EmailDeliveryError(RuntimeError):
    """Raised when an email could not be delivered."""


def _provider() -> str:
    explicit = os.getenv("EMAIL_PROVIDER", "").strip().lower()
    if explicit:
        return explicit
    if os.getenv("RESEND_API_KEY"):
        return "resend"
    if os.getenv("SENDGRID_API_KEY"):
        return "sendgrid"
    if os.getenv("SMTP_HOST"):
        return "smtp"
    return "console"


def _from_address() -> str:
    return os.getenv("EMAIL_FROM", "").strip() or settings.email_from


def send_email(to: str, subject: str, *, html: str, text: Optional[str] = None) -> bool:
    """Send one transactional email. Returns True or raises EmailDeliveryError."""
    to = (to or "").strip()
    if not to:
        raise EmailDeliveryError("No recipient address")
    sender = _from_address()
    provider = _provider()
    text = text or _html_to_text(html)

    try:
        if provider == "resend":
            return _send_resend(sender, to, subject, html, text)
        if provider == "sendgrid":
            return _send_sendgrid(sender, to, subject, html, text)
        if provider == "smtp":
            return _send_smtp(sender, to, subject, html, text)
        # console
        if settings.is_production:
            raise EmailDeliveryError(
                "No email provider configured (EMAIL_PROVIDER/RESEND_API_KEY/"
                "SENDGRID_API_KEY/SMTP_HOST) — refusing to fake-send in production."
            )
        logger.warning("[email:console] To=%s Subject=%s\n%s", to, subject, text)
        return True
    except EmailDeliveryError:
        raise
    except Exception as exc:  # normalise provider/network errors
        logger.error("Email send failed via %s: %s", provider, exc)
        raise EmailDeliveryError(f"Email send failed: {exc}") from exc


# ─── providers ───────────────────────────────────────────────────────────────

def _send_resend(sender: str, to: str, subject: str, html: str, text: str) -> bool:
    key = os.environ["RESEND_API_KEY"]
    resp = httpx.post(
        "https://api.resend.com/emails",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json={"from": sender, "to": [to], "subject": subject, "html": html, "text": text},
        timeout=15.0,
    )
    if resp.status_code >= 300:
        raise EmailDeliveryError(f"Resend {resp.status_code}: {resp.text[:300]}")
    return True


def _send_sendgrid(sender: str, to: str, subject: str, html: str, text: str) -> bool:
    key = os.environ["SENDGRID_API_KEY"]
    resp = httpx.post(
        "https://api.sendgrid.com/v3/mail/send",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json={
            "personalizations": [{"to": [{"email": to}]}],
            "from": {"email": _bare_address(sender), "name": _display_name(sender)},
            "subject": subject,
            "content": [
                {"type": "text/plain", "value": text},
                {"type": "text/html", "value": html},
            ],
        },
        timeout=15.0,
    )
    if resp.status_code >= 300:
        raise EmailDeliveryError(f"SendGrid {resp.status_code}: {resp.text[:300]}")
    return True


def _send_smtp(sender: str, to: str, subject: str, html: str, text: str) -> bool:
    host = os.environ["SMTP_HOST"]
    port = int(os.getenv("SMTP_PORT", "587"))
    username = os.getenv("SMTP_USERNAME")
    password = os.getenv("SMTP_PASSWORD")
    use_starttls = os.getenv("SMTP_STARTTLS", "true").lower() != "false"

    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(text)
    msg.add_alternative(html, subtype="html")

    with smtplib.SMTP(host, port, timeout=20) as server:
        if use_starttls:
            server.starttls()
        if username and password:
            server.login(username, password)
        server.send_message(msg)
    return True


# ─── helpers ─────────────────────────────────────────────────────────────────

def _bare_address(value: str) -> str:
    if "<" in value and ">" in value:
        return value[value.index("<") + 1 : value.index(">")].strip()
    return value.strip()


def _display_name(value: str) -> str:
    if "<" in value:
        return value[: value.index("<")].strip() or "PlaceUp Career"
    return "PlaceUp Career"


def _html_to_text(html: str) -> str:
    import re
    text = re.sub(r"<br\s*/?>", "\n", html or "", flags=re.I)
    text = re.sub(r"</p>", "\n\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    return " ".join(text.split())

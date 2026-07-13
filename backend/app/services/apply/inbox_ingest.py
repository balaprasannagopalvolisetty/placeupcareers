"""
Dedicated-inbox email ingestion (doc sections B6 + E).

Each user gets `first.last@mail.placeupcareer.com`. Inbound mail flows:

    MX(mail.placeupcareer.com) -> AWS SES receipt rule (catch-all) -> S3 (raw MIME)
      -> Lambda (parse) -> forward to user's real email + POST this webhook
      -> FastAPI writes inbox_messages + runs OTP/verification-code extraction
      -> links the message to the matching application by sender/subject.

This module owns the *parsing + classification + linking* half (the part that
runs inside FastAPI). The SES receipt rule, S3 bucket and Lambda are infra
(see deploy docs). Chosen over Gmail restricted-scope OAuth because that forces
an annual CASA Tier 2 assessment and a lifetime 100-user cap (doc section F).

Nothing here sends mail or bypasses any verification — it only captures codes
so the review UI can surface an OTP the user still enters themselves.
"""
from __future__ import annotations

import logging
import re
from typing import Optional

from app.models.application import InboxClassification, InboxMessage

log = logging.getLogger("placeup.apply.inbox")

# OTP / verification-code patterns. Deliberately conservative to avoid pulling
# random 6-digit numbers (years, zip codes) out of marketing mail.
_OTP_PATTERNS = [
    re.compile(r"\b(?:one[-\s]?time|verification|security|access|login|confirmation)\s+code[^0-9]{0,20}(\d{4,8})\b", re.I),
    re.compile(r"\bcode\s+is[:\s]+(\d{4,8})\b", re.I),
    re.compile(r"\b(\d{6})\b\s+is your (?:verification|security|one[-\s]?time) code", re.I),
    re.compile(r"\bOTP[:\s]+(\d{4,8})\b", re.I),
]

_CONFIRMATION_HINTS = (
    "thank you for applying", "application received", "we received your application",
    "your application to", "application confirmation", "successfully submitted",
)
_STATUS_HINTS = (
    "next steps", "interview", "moving forward", "unfortunately", "not moving forward",
    "we regret", "schedule", "assessment", "offer",
)


def extract_otp(text: str) -> Optional[str]:
    """Return the first plausible verification code found, else None."""
    if not text:
        return None
    for pat in _OTP_PATTERNS:
        m = pat.search(text)
        if m:
            return m.group(1)
    return None


def classify(subject: str, body: str) -> InboxClassification:
    blob = f"{subject}\n{body}".lower()
    if extract_otp(f"{subject}\n{body}"):
        return InboxClassification.OTP
    if any(h in blob for h in _CONFIRMATION_HINTS):
        return InboxClassification.CONFIRMATION
    if any(h in blob for h in _STATUS_HINTS):
        return InboxClassification.STATUS
    return InboxClassification.OTHER


def uid_from_inbox_address(to_addr: str, resolve_uid) -> Optional[str]:
    """Map `first.last@mail.placeupcareer.com` back to a uid via `resolve_uid`
    (a lookup callable). Returns None if the address isn't one of ours."""
    addr = (to_addr or "").strip().lower()
    if "@mail.placeupcareer.com" not in addr:
        return None
    local = addr.split("@", 1)[0]
    return resolve_uid(local)


def parse_webhook(payload: dict, resolve_uid) -> Optional[InboxMessage]:
    """Turn the Lambda's POSTed JSON into an InboxMessage.

    Expected shape (produced by the SES->Lambda parser):
        { "to": "...", "from": "...", "subject": "...", "text": "...",
          "s3_key": "...", "received_at": "ISO8601"? }
    """
    to_addr = payload.get("to") or payload.get("recipient") or ""
    uid = uid_from_inbox_address(to_addr, resolve_uid)
    if not uid:
        log.info("inbox webhook: unrecognized recipient %r", to_addr)
        return None
    subject = payload.get("subject") or ""
    body = payload.get("text") or payload.get("body") or ""
    msg = InboxMessage(
        uid=uid,
        from_addr=payload.get("from") or "",
        subject=subject,
        s3_key=payload.get("s3_key"),
        parsed_text=body[:20000],
        extracted_otp=extract_otp(f"{subject}\n{body}"),
        classification=classify(subject, body),
    )
    return msg


def link_to_application(msg: InboxMessage, applications: list[dict]) -> Optional[str]:
    """Best-effort link an inbox message to an application via sender-domain /
    subject/company heuristics. Returns the app id or None."""
    sender_domain = (msg.from_addr.split("@")[-1] if "@" in msg.from_addr else "").lower()
    subj = msg.subject.lower()
    best = None
    for app in applications:
        company = (app.get("company") or "").lower()
        if not company:
            continue
        token = company.split()[0] if company.split() else company
        if token and (token in sender_domain or token in subj):
            best = app.get("id")
            break
    return best

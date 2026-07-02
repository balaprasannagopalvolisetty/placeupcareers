"""Public contact form endpoint."""

from __future__ import annotations

import html
import logging

from fastapi import APIRouter, Body, HTTPException, Request, status
from pydantic import BaseModel, EmailStr, Field

from app.config import settings
from app.services.email import EmailDeliveryError, send_email

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/contact", tags=["Contact"])


class ContactMessage(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    subject: str = Field(default="General Inquiry", max_length=160)
    message: str = Field(min_length=10, max_length=5000)


def _client_ip(request: Request) -> str:
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",", 1)[0].strip()
    return request.client.host if request.client else ""


@router.post("")
async def submit_contact_message(request: Request, payload: ContactMessage = Body(...)):
    recipient = settings.contact_recipient_email.strip() or "operations@placeupcareer.com"
    name = payload.name.strip()
    sender_email = str(payload.email).strip().lower()
    subject = payload.subject.strip() or "General Inquiry"
    message = payload.message.strip()
    ip = _client_ip(request)
    user_agent = request.headers.get("user-agent", "")

    safe_name = html.escape(name)
    safe_sender = html.escape(sender_email)
    safe_subject = html.escape(subject)
    safe_message = html.escape(message).replace("\n", "<br>")

    html_body = f"""
    <h2>New PlaceUp contact message</h2>
    <p><strong>Name:</strong> {safe_name}</p>
    <p><strong>Email:</strong> {safe_sender}</p>
    <p><strong>Subject:</strong> {safe_subject}</p>
    <p><strong>Message:</strong><br>{safe_message}</p>
    <hr>
    <p><strong>IP:</strong> {html.escape(ip)}</p>
    <p><strong>User agent:</strong> {html.escape(user_agent[:500])}</p>
    """
    text_body = (
        "New PlaceUp contact message\n\n"
        f"Name: {name}\n"
        f"Email: {sender_email}\n"
        f"Subject: {subject}\n\n"
        f"{message}\n\n"
        f"IP: {ip}\n"
        f"User agent: {user_agent[:500]}"
    )

    try:
        send_email(
            recipient,
            f"PlaceUp Contact: {subject}",
            html=html_body,
            text=text_body,
        )
    except EmailDeliveryError as exc:
        logger.warning("Contact form delivery failed for %s: %s", sender_email, exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not send your message right now. Please email operations@placeupcareer.com directly.",
        ) from exc

    return {"ok": True, "to": recipient}

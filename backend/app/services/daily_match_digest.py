"""Daily top-match email digest.

Runs in Cloud Run/Cloud Scheduler. Sends only when SMTP settings are present;
otherwise it records what would be sent in logs so the job remains safe.
"""

from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage

from app.config import settings
from app.db import user_store
from app.dependencies import get_db
from app.api.jobs import _active_resume_text, _preference_terms, _score_job_against_resume, _baseline_ats_score

logger = logging.getLogger(__name__)


def _send_email(to_email: str, subject: str, body: str) -> bool:
    if not (settings.smtp_host and settings.smtp_user and settings.smtp_password):
        logger.info("SMTP not configured; digest preview for %s:\n%s", to_email, body[:1200])
        return False
    msg = EmailMessage()
    msg["From"] = settings.email_from
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.set_content(body)
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30) as smtp:
        smtp.starttls()
        smtp.login(settings.smtp_user, settings.smtp_password)
        smtp.send_message(msg)
    return True


async def send_daily_match_digests(limit_users: int = 500) -> dict:
    db_gen = get_db()
    db = next(db_gen)
    users = user_store.list_users(limit=limit_users)
    sent = 0
    previewed = 0
    skipped = 0
    for user in users:
        user_id = user.get("id")
        email = user.get("email")
        if not user_id or not email:
            skipped += 1
            continue
        settings_row = user_store.get_alert_settings(user_id)
        prefs = user_store.get_preferences(user_id)
        if settings_row.get("email_alerts") is False or settings_row.get("daily_digest") is False:
            skipped += 1
            continue
        resume_text = await _active_resume_text(user_id)
        preferred_roles, _ = _preference_terms(user_id)
        filters = {"title_terms": preferred_roles[:5]} if preferred_roles else {}
        jobs = await db.get_jobs(filters=filters, limit=1000, offset=0)
        ranked = []
        for job in jobs:
            score = _score_job_against_resume(resume_text, f"{job.get('title') or ''}\n{job.get('description') or ''}") if resume_text else _baseline_ats_score(job)
            ranked.append((score, job))
        ranked.sort(key=lambda item: item[0], reverse=True)
        top = ranked[:10]
        if not top:
            skipped += 1
            continue
        lines = [
            f"Good morning {user.get('first_name') or ''},",
            "",
            "Your top 10 PlaceUp Career matches for today:",
            "",
        ]
        for idx, (score, job) in enumerate(top, start=1):
            url = f"{settings.frontend_url.rstrip('/')}/dashboard/jobs/{job.get('id')}"
            lines.append(f"{idx}. {score}% - {job.get('title')} at {job.get('company')} - {url}")
        lines.append("")
        lines.append("Open each link in PlaceUp Career to review the match and apply.")
        did_send = _send_email(email, "Your top 10 job matches from PlaceUp Career", "\n".join(lines))
        if did_send:
            sent += 1
        else:
            previewed += 1
    try:
        next(db_gen)
    except StopIteration:
        pass
    return {"users": len(users), "sent": sent, "previewed": previewed, "skipped": skipped}

"""Quality fixes for noisy job-board payloads."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any


_BOARD_COMPANIES = {"linkedin", "indeed", "glassdoor", "ziprecruiter", "zip_recruiter", "google"}


def clean_job_company(company: Any, description: Any = "") -> str:
    """Return the employer, not the board, when a source page leaks into company."""
    current = str(company or "").strip()
    text = str(description or "")
    if current.lower() not in _BOARD_COMPANIES:
        return current

    patterns = (
        r"Company logo for,\s*([^.\n\r]+)",
        r"\nCompany\s*-\s*([^\n\r]+)",
    )
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            candidate = _clean_company_candidate(match.group(1))
            if candidate:
                return candidate
    return current


def clean_job_description(description: Any) -> str:
    """Trim board chrome/header text while keeping the real job description."""
    text = str(description or "").strip()
    if not text:
        return ""

    markers = (
        r"\bAbout the job\b",
        r"\bJob Description\b",
        r"\bDescription\s*\n",
    )
    for marker in markers:
        match = re.search(marker, text, flags=re.IGNORECASE)
        if match and match.start() > 0:
            text = text[match.start():].strip()
            break
    return text


def infer_posted_at(posted_at: Any, description: Any = "", *, now: datetime | None = None) -> Any:
    """Fill missing posted_at from LinkedIn-style relative dates in the text."""
    if posted_at:
        return posted_at

    text = str(description or "")
    if not text:
        return posted_at

    base = now or datetime.now(timezone.utc)
    match = re.search(
        r"\b(?:reposted\s+)?(\d+)\s+(minute|hour|day|week|month)s?\s+ago\b",
        text,
        flags=re.IGNORECASE,
    )
    if not match:
        if re.search(r"\b(just now|recently)\b", text, flags=re.IGNORECASE):
            return base
        return posted_at

    amount = int(match.group(1))
    unit = match.group(2).lower()
    if unit == "minute":
        delta = timedelta(minutes=amount)
    elif unit == "hour":
        delta = timedelta(hours=amount)
    elif unit == "day":
        delta = timedelta(days=amount)
    elif unit == "week":
        delta = timedelta(weeks=amount)
    else:
        delta = timedelta(days=amount * 30)
    return base - delta


def _clean_company_candidate(value: str) -> str:
    text = re.sub(r"\s+", " ", value or "").strip(" .,-")
    if not text or text.lower() in _BOARD_COMPANIES:
        return ""
    return text[:180]

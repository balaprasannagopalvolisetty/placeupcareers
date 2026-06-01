"""Quality fixes for noisy job-board payloads."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any


_BOARD_COMPANIES = {"linkedin", "indeed", "glassdoor", "ziprecruiter", "zip_recruiter", "google"}
_GENERIC_JOB_TITLE_RE = re.compile(
    r"(?i)\b("
    r"jobs?|openings?|hiring|career|careers|job alert|saved jobs|similar jobs|"
    r"view all|search results"
    r")\b"
)


def clean_job_company(company: Any, description: Any = "", title: Any = "") -> str:
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
    candidate = _company_from_linkedin_snippet(str(title or ""), text)
    if candidate:
        return candidate
    return ""


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


def is_probably_job_search_page(title: Any, company: Any = "", description: Any = "", source: Any = "") -> bool:
    """Reject search/category pages that masquerade as job cards.

    LinkedIn/Google/Glassdoor search pages often expose anchors like
    "Senior Security Engineer jobs". Those are not postings, have no employer
    or JD, and should never be loaded into the production jobs table.
    """
    title_text = str(title or "").strip()
    low_title = title_text.lower()
    source_text = str(source or "").lower()
    board_company = str(company or "").strip().lower() in _BOARD_COMPANIES
    if not title_text:
        return True
    if re.search(r"(?i)\bjobs?\s*$", title_text) and ("linkedin" in source_text or board_company):
        return True
    if _GENERIC_JOB_TITLE_RE.search(title_text) and len(str(description or "").split()) < 25:
        return True
    if board_company and not _company_from_linkedin_snippet(title_text, str(description or "")):
        return True
    return False


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
    if not text or (text.lower() in _BOARD_COMPANIES and text.lower() != "google"):
        return ""
    if _GENERIC_JOB_TITLE_RE.search(text):
        return ""
    return text[:180]


def _company_from_linkedin_snippet(title: str, description: str) -> str:
    """Extract employer from compact LinkedIn snippets.

    Examples:
      "Security Engineer Security Engineer Google Atlanta, GA 5 hours ago"
      "Product Security Engineer - Public Sector Scale AI St Louis, MO 1 day ago"
    """
    text = re.sub(r"\s+", " ", description or "").strip()
    title_clean = re.sub(r"\s+", " ", title or "").strip()
    if not text or not title_clean:
        return ""

    rest = text
    title_re = re.escape(title_clean)
    rest = re.sub(rf"(?i)^{title_re}\s+{title_re}\s+", "", rest).strip()
    rest = re.sub(rf"(?i)^{title_re}\s+", "", rest).strip()
    if not rest or rest == text:
        return ""

    # Company is usually before a location token or applicant/date chrome.
    stop_match = re.search(
        r"\s(?:[A-Z][a-zA-Z .'-]+,\s*(?:[A-Z]{2}|United States|Canada)|"
        r"Remote\b|United States\b|Canada\b|"
        r"Be an early applicant\b|\d+\s+(?:minute|hour|day|week|month)s?\s+ago\b|"
        r"Reposted\b|Promoted\b)",
        rest,
    )
    candidate = rest[:stop_match.start()].strip(" .,-") if stop_match else rest.strip(" .,-")
    # Keep multi-word companies like Amazon Web Services (AWS), but avoid
    # swallowing a whole sentence if the snippet shape changed.
    words = candidate.split()
    if len(words) > 8:
        candidate = " ".join(words[:8])
    return _clean_company_candidate(candidate)

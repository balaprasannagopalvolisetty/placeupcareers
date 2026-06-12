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
_SCAM_RE = re.compile(
    r"(?i)\b("
    r"pay\s+(?:a\s+)?(?:fee|deposit|training fee)|"
    r"send\s+money|wire\s+transfer|western\s+union|moneygram|"
    r"crypto(?:currency)?|bitcoin|gift\s+cards?|"
    r"whatsapp|telegram|signal\s+only|"
    r"no\s+interview\s+required|guaranteed\s+(?:job|offer|placement)|"
    r"work\s+from\s+home\s+and\s+earn|earn\s+\$?\d+.*(?:daily|weekly)|"
    r"processing\s+fee|background\s+check\s+fee|equipment\s+fee|"
    r"upload\s+(?:your\s+)?(?:ssn|social security|passport|bank details)"
    r")\b"
)
_JOB_DETAIL_MARKER_RE = re.compile(
    r"(?i)\b("
    r"responsibilities|requirements|qualifications|about the job|job description|"
    r"what you'?ll do|what you will do|minimum qualifications|basic qualifications|"
    r"job duties|preferred qualifications|benefits"
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


_MD_ESCAPE_RE = re.compile(r"\\([\\`*_{}\[\]()#+\-.!|>~])")


def strip_markdown_escapes(text: str) -> str:
    r"""Remove backslash-escaped Markdown punctuation left by scrapers.

    Sources that convert HTML to Markdown (LinkedIn, JobSpy, etc.) escape
    punctuation, so JDs render with artifacts like "F1\-OPT", "pre\-sales",
    or "8 to 12 years\." — unprofessional and noisy. Unescape them.
    """
    return _MD_ESCAPE_RE.sub(r"\1", text or "")


# UI chrome that scrapers swallow from job boards (Job Bank, CareerBeacon...).
# These fragments are pure navigation noise — never part of a real JD.
_BOARD_CHROME_PATTERNS = (
    re.compile(r"\b\d{2,6}\s+\d{1,3}\s+Loading, please wait\.{0,3}\s*Cancel\s*", re.I),
    re.compile(r"Loading, please wait\.{0,3}\s*Cancel\s*", re.I),
    re.compile(r"Save to favourites\s*(?:Your favourites\s*)?To add a job posting to your favourites[^.]*\.\s*(?:Sign in or sign up[^.]*\.)?\s*", re.I),
    re.compile(r"Direct Apply\s*(?:Direct Apply\s*)?Sign in to apply directly on Job Bank[^.]*\.\s*(?:Sign up\b)?\s*", re.I),
    re.compile(r"Save to favourites\s*", re.I),
)


def strip_board_chrome(text: str) -> str:
    for pattern in _BOARD_CHROME_PATTERNS:
        text = pattern.sub(" ", text)
    return re.sub(r"[ \t]{2,}", " ", text).strip()


def clean_job_description(description: Any) -> str:
    """Trim board chrome/header text while keeping the real job description."""
    text = str(description or "").strip()
    if not text:
        return ""

    text = strip_markdown_escapes(text)
    text = strip_board_chrome(text)

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


def is_probably_fake_or_scam_job(title: Any, company: Any = "", description: Any = "", url: Any = "") -> bool:
    """Reject obvious scam/fake postings before they reach master_jobs.

    This is intentionally conservative. It only catches high-confidence scam
    language and board/search artifacts, so legitimate early-career postings
    with short descriptions are not discarded just because they are concise.
    """
    title_text = str(title or "").strip()
    company_text = str(company or "").strip()
    desc_text = str(description or "").strip()
    url_text = str(url or "").strip().lower()
    combined = f"{title_text}\n{company_text}\n{desc_text}\n{url_text}"
    if _SCAM_RE.search(combined):
        return True
    if not title_text or not company_text:
        return True
    lowered_title = title_text.lower()
    if lowered_title in {"job", "jobs", "careers", "open positions", "job openings"}:
        return True
    if _GENERIC_JOB_TITLE_RE.search(title_text) and len(desc_text.split()) < 40:
        return True
    return False


def has_usable_job_description(description: Any, *, min_words: int = 35) -> bool:
    text = str(description or "").strip()
    if not text:
        return False
    words = re.findall(r"\b[a-zA-Z][a-zA-Z0-9+#./-]*\b", text)
    if len(words) >= min_words:
        return True
    return len(words) >= 20 and bool(_JOB_DETAIL_MARKER_RE.search(text))


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

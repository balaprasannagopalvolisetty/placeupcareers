"""
Clean-200 global job-board connectors.

Each board here is a free, public, bot-friendly endpoint (JSON or RSS) that
returns HTTP 200 reliably — no auth, no anti-bot, no legal grey area. They
skew remote / English-language / international, which directly serves the
"English-friendly roles worldwide" requirement.

Connectors:
  - RemoteOK         https://remoteok.com/api                 (JSON)
  - Remotive         https://remotive.com/api/remote-jobs     (JSON)
  - Arbeitnow        https://www.arbeitnow.com/api/job-board-api (JSON, EU-heavy)
  - Jobicy           https://jobicy.com/api/v2/remote-jobs     (JSON)
  - We Work Remotely https://weworkremotely.com/remote-jobs.rss (RSS/XML)

Every connector returns list[JobPost]. Parsing helpers are pure
(dict/str -> JobPost|None) so they unit-test without the network.
All postings are stamped extra_metadata.english_friendly and a best-effort
visa_country (ISO2 or None for "remote/unspecified").
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

import httpx
from bs4 import BeautifulSoup

from app.models.job import JobCategory, JobPost, JobSource
from app.utils.deduplication import generate_content_hash, generate_job_id
from app.etl.sources.source_base import safe_get_json, safe_get_text, is_probably_english

logger = logging.getLogger(__name__)


# ─── shared helpers ──────────────────────────────────────────────────────────

def _s(value: Any) -> str:
    """Coerce to a clean string."""
    if value is None:
        return ""
    return str(value).strip()


def _parse_epoch_or_iso(value: Any) -> Optional[datetime]:
    """Parse a posted-at value that may be epoch seconds or an ISO string."""
    if value in (None, "", 0):
        return None
    # epoch seconds (int or numeric string)
    try:
        if isinstance(value, (int, float)) or (isinstance(value, str) and value.isdigit()):
            return datetime.fromtimestamp(int(value), tz=timezone.utc)
    except (ValueError, OSError, OverflowError):
        pass
    # ISO 8601 (tolerate trailing Z)
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def _build(
    *,
    title: str,
    company: str,
    location: str,
    description: str,
    job_url: str,
    source: JobSource,
    source_job_id: str,
    posted_at: Optional[datetime],
    is_remote: bool,
    visa_country: Optional[str],
    english_friendly: bool = True,
    extra: Optional[dict] = None,
) -> Optional[JobPost]:
    """Assemble a JobPost the same way the ATS connectors do (id + content_hash)."""
    title = _s(title)
    company = _s(company)
    if not title or not company:
        return None
    location = _s(location) or ("Remote" if is_remote else "")
    meta: dict[str, Any] = {
        "english_friendly": english_friendly,
        "visa_country": visa_country,    # ISO2 or None (remote/unspecified)
        "board": source.value,
    }
    if extra:
        meta.update({k: v for k, v in extra.items() if v not in (None, "", [], {})})
    return JobPost(
        id=generate_job_id(title, company, location or job_url or source_job_id, visa_country=visa_country),
        title=title,
        company=company,
        location=location,
        description=_s(description),
        job_url=_s(job_url),
        category=JobCategory.OTHER,
        source=source,
        source_job_id=_s(source_job_id),
        posted_at=posted_at,
        is_remote=is_remote,
        content_hash=generate_content_hash(title, company, location, visa_country=visa_country),
        scraped_at=datetime.utcnow(),
        extra_metadata=meta,
    )


# ─── RemoteOK ────────────────────────────────────────────────────────────────

REMOTEOK_URL = "https://remoteok.com/api"


def remoteok_item_to_jobpost(item: dict) -> Optional[JobPost]:
    # RemoteOK's first array element is a legal/metadata object, not a job.
    if not isinstance(item, dict) or not item.get("position"):
        return None
    salary_extra = {
        "salary_min": item.get("salary_min"),
        "salary_max": item.get("salary_max"),
        "tags": item.get("tags") or [],
    }
    return _build(
        title=item.get("position"),
        company=item.get("company"),
        location=item.get("location") or "Remote",
        description=item.get("description"),
        job_url=item.get("url") or item.get("apply_url"),
        source=JobSource.REMOTEOK,
        source_job_id=item.get("id") or item.get("slug"),
        posted_at=_parse_epoch_or_iso(item.get("epoch") or item.get("date")),
        is_remote=True,
        visa_country=None,
        extra=salary_extra,
    )


async def scrape_remoteok(*, client: Optional[httpx.AsyncClient] = None, max_jobs: int = 500) -> list[JobPost]:
    data = await safe_get_json(REMOTEOK_URL, client=client)
    if not isinstance(data, list):
        return []
    out: list[JobPost] = []
    for item in data:
        jp = remoteok_item_to_jobpost(item)
        if jp:
            out.append(jp)
        if len(out) >= max_jobs:
            break
    return out


# ─── Remotive ────────────────────────────────────────────────────────────────

REMOTIVE_URL = "https://remotive.com/api/remote-jobs"


def remotive_item_to_jobpost(item: dict) -> Optional[JobPost]:
    if not isinstance(item, dict):
        return None
    return _build(
        title=item.get("title"),
        company=item.get("company_name"),
        location=item.get("candidate_required_location") or "Remote",
        description=item.get("description"),
        job_url=item.get("url"),
        source=JobSource.REMOTIVE,
        source_job_id=item.get("id"),
        posted_at=_parse_epoch_or_iso(item.get("publication_date")),
        is_remote=True,
        visa_country=None,
        extra={"job_type": item.get("job_type"), "category": item.get("category"), "salary": item.get("salary")},
    )


async def scrape_remotive(*, client: Optional[httpx.AsyncClient] = None, max_jobs: int = 500) -> list[JobPost]:
    data = await safe_get_json(REMOTIVE_URL, client=client)
    jobs = (data or {}).get("jobs") if isinstance(data, dict) else None
    if not isinstance(jobs, list):
        return []
    out: list[JobPost] = []
    for item in jobs[:max_jobs]:
        jp = remotive_item_to_jobpost(item)
        if jp:
            out.append(jp)
    return out


# ─── Arbeitnow (EU / Germany-heavy, English-friendly) ────────────────────────

ARBEITNOW_URL = "https://www.arbeitnow.com/api/job-board-api"


def arbeitnow_item_to_jobpost(item: dict) -> Optional[JobPost]:
    if not isinstance(item, dict):
        return None
    tags = item.get("tags") or []
    is_remote = bool(item.get("remote"))
    # visa hint surfaces in tags on some Arbeitnow posts
    visa_flag = any("visa" in _s(t).lower() for t in tags)
    title = item.get("title")
    description = item.get("description")
    return _build(
        title=title,
        company=item.get("company_name"),
        location=item.get("location") or ("Remote" if is_remote else ""),
        description=description,
        job_url=item.get("url"),
        source=JobSource.ARBEITNOW,
        source_job_id=item.get("slug"),
        posted_at=_parse_epoch_or_iso(item.get("created_at")),
        is_remote=is_remote,
        visa_country=None,  # location strings are free-text; resolved by geo layer downstream
        # Arbeitnow is EU-wide (often German employers) → confirm English per posting
        english_friendly=is_probably_english(f"{_s(title)} {_s(description)}"),
        extra={"tags": tags, "job_types": item.get("job_types") or [], "visa_mentioned": visa_flag},
    )


async def scrape_arbeitnow(*, client: Optional[httpx.AsyncClient] = None, max_jobs: int = 500) -> list[JobPost]:
    data = await safe_get_json(ARBEITNOW_URL, client=client)
    jobs = (data or {}).get("data") if isinstance(data, dict) else None
    if not isinstance(jobs, list):
        return []
    out: list[JobPost] = []
    for item in jobs[:max_jobs]:
        jp = arbeitnow_item_to_jobpost(item)
        if jp:
            out.append(jp)
    return out


# ─── Jobicy ──────────────────────────────────────────────────────────────────

JOBICY_URL = "https://jobicy.com/api/v2/remote-jobs"


def jobicy_item_to_jobpost(item: dict) -> Optional[JobPost]:
    if not isinstance(item, dict):
        return None
    return _build(
        title=item.get("jobTitle"),
        company=item.get("companyName"),
        location=item.get("jobGeo") or "Remote",
        description=item.get("jobExcerpt") or item.get("jobDescription"),
        job_url=item.get("url"),
        source=JobSource.JOBICY,
        source_job_id=item.get("id"),
        posted_at=_parse_epoch_or_iso(item.get("pubDate")),
        is_remote=True,
        visa_country=None,
        extra={"job_type": item.get("jobType"), "job_level": item.get("jobLevel"),
               "salary_min": item.get("annualSalaryMin"), "salary_max": item.get("annualSalaryMax")},
    )


async def scrape_jobicy(*, client: Optional[httpx.AsyncClient] = None, max_jobs: int = 500) -> list[JobPost]:
    data = await safe_get_json(JOBICY_URL, client=client)
    jobs = (data or {}).get("jobs") if isinstance(data, dict) else None
    if not isinstance(jobs, list):
        return []
    out: list[JobPost] = []
    for item in jobs[:max_jobs]:
        jp = jobicy_item_to_jobpost(item)
        if jp:
            out.append(jp)
    return out


# ─── We Work Remotely (RSS / XML) ────────────────────────────────────────────

WWR_URL = "https://weworkremotely.com/remote-jobs.rss"


def wwr_item_to_jobpost(item) -> Optional[JobPost]:
    """Parse one <item> element (BeautifulSoup tag) from the WWR RSS feed.

    Titles look like "Company Name: Job Title" — split on the first colon.
    """
    def _text(tag_name: str) -> str:
        el = item.find(tag_name)
        return el.get_text(strip=True) if el else ""

    raw_title = _text("title")
    if not raw_title:
        return None
    if ":" in raw_title:
        company, _, title = raw_title.partition(":")
        company, title = company.strip(), title.strip()
    else:
        company, title = "", raw_title.strip()
    if not title:
        title, company = company, ""

    region = _text("region") or "Remote"
    link = _text("link")
    posted = _parse_epoch_or_iso(_text("pubDate")) or _parse_rfc822(_text("pubDate"))
    return _build(
        title=title,
        company=company or "Unknown",
        location=region,
        description=_text("description"),
        job_url=link,
        source=JobSource.WEWORKREMOTELY,
        source_job_id=link,
        posted_at=posted,
        is_remote=True,
        visa_country=None,
        extra={"category": _text("category")},
    )


def _parse_rfc822(value: str) -> Optional[datetime]:
    """RSS pubDate is RFC-822 (e.g. 'Mon, 02 Jun 2026 12:00:00 +0000')."""
    if not value:
        return None
    try:
        from email.utils import parsedate_to_datetime
        return parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None


def parse_wwr_rss(xml_text: str, *, max_jobs: int = 500) -> list[JobPost]:
    soup = BeautifulSoup(xml_text, "xml")
    out: list[JobPost] = []
    for item in soup.find_all("item")[:max_jobs]:
        jp = wwr_item_to_jobpost(item)
        if jp:
            out.append(jp)
    return out


async def scrape_weworkremotely(*, client: Optional[httpx.AsyncClient] = None, max_jobs: int = 500) -> list[JobPost]:
    text = await safe_get_text(WWR_URL, client=client)
    if not text:
        return []
    try:
        return parse_wwr_rss(text, max_jobs=max_jobs)
    except Exception as exc:  # malformed feed → skip, never raise
        logger.warning("WWR RSS parse failed: %s", exc)
        return []

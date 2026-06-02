"""
Official government job-portal connectors (clean 200, country-tagged).

Unlike the remote boards in free_boards.py, these are national portals, so
every posting carries a definite `visa_country` (ISO2). They sit in
non-English-speaking countries, so postings are language-filtered: only
English-friendly roles are kept (requirement B4) — the per-job
`english_friendly` flag is set via source_base.is_probably_english().

Implemented (shape confirmed against the live API):
  - JobTech Dev / Platsbanken (Sweden)  https://jobsearch.api.jobtechdev.se/search
    Open API, no auth, returns clean JSON 200.

Documented next (POST APIs — add once a live sample is captured):
  - MyCareersFuture (Singapore), France Travail (OAuth), NAV (Norway, token).
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Optional

import httpx

from app.models.job import JobCategory, JobPost, JobSource
from app.utils.deduplication import generate_content_hash, generate_job_id
from app.etl.sources.source_base import safe_get_json, is_probably_english

logger = logging.getLogger(__name__)


def _s(v: Any) -> str:
    return "" if v is None else str(v).strip()


def _parse_iso(value: Any) -> Optional[datetime]:
    if not value or not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


# ─── JobTech Dev / Platsbanken (Sweden, SE) ──────────────────────────────────

JOBTECH_URL = "https://jobsearch.api.jobtechdev.se/search"
JOBTECH_COUNTRY = "SE"


def jobtech_hit_to_jobpost(hit: dict) -> Optional[JobPost]:
    """Map one JobTech `hits[]` element to a JobPost.

    Field names verified against the live API response. Note: their
    `workplace_address.country_code` is an internal taxonomy code (e.g. "199"),
    NOT ISO — so we hard-tag SE (this is Sweden's national board).
    """
    if not isinstance(hit, dict):
        return None
    title = _s(hit.get("headline"))
    employer = hit.get("employer") or {}
    company = _s(employer.get("name") or employer.get("workplace"))
    if not title or not company:
        return None

    addr = hit.get("workplace_address") or {}
    city = _s(addr.get("city") or addr.get("municipality"))
    location = ", ".join(p for p in (city, "Sweden") if p) or "Sweden"

    desc_obj = hit.get("description") or {}
    description = _s(desc_obj.get("text"))
    job_url = _s(hit.get("webpage_url"))
    field = (hit.get("occupation_field") or {}).get("label")

    english = is_probably_english(f"{title} {description}")
    return JobPost(
        id=generate_job_id(title, company, location, visa_country=JOBTECH_COUNTRY),
        title=title,
        company=company,
        location=location,
        description=description,
        job_url=job_url,
        category=JobCategory.OTHER,
        source=JobSource.JOBTECH,
        source_job_id=_s(hit.get("id")),
        posted_at=_parse_iso(hit.get("publication_date")),
        is_remote=False,
        content_hash=generate_content_hash(title, company, location, visa_country=JOBTECH_COUNTRY),
        scraped_at=datetime.utcnow(),
        extra_metadata={
            "english_friendly": english,
            "visa_country": JOBTECH_COUNTRY,
            "board": JobSource.JOBTECH.value,
            "occupation_field": field,
            "vacancies": hit.get("number_of_vacancies"),
            "deadline": hit.get("application_deadline"),
        },
    )


async def scrape_jobtech(
    *,
    client: Optional[httpx.AsyncClient] = None,
    max_jobs: int = 500,
    query: str = "",
) -> list[JobPost]:
    """Fetch recent Swedish postings. `q` empty = all; we page in 100s."""
    out: list[JobPost] = []
    page_size = min(100, max_jobs)
    offset = 0
    while len(out) < max_jobs:
        params = {"limit": page_size, "offset": offset, "sort": "pubdate-desc"}
        if query:
            params["q"] = query
        data = await safe_get_json(JOBTECH_URL, client=client, params=params)
        hits = (data or {}).get("hits") if isinstance(data, dict) else None
        if not hits:
            break
        for hit in hits:
            jp = jobtech_hit_to_jobpost(hit)
            if jp:
                out.append(jp)
        if len(hits) < page_size:
            break
        offset += page_size
    return out[:max_jobs]


# name -> connector coroutine factory
OFFICIAL_PORTAL_SOURCES = {
    "jobtech": scrape_jobtech,
}

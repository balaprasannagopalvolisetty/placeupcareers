from __future__ import annotations

import html
import logging
import re
from typing import Any

from app.config import settings
from app.etl.api_sources.http import get_json
from app.etl.api_sources.schema import FetchParams, NormalizedJob, clean_text, iso_or_none, stable_job_id

logger = logging.getLogger(__name__)

COUNTRY_ALIASES = {
    "US": "us",
    "USA": "us",
    "GB": "gb",
    "UK": "gb",
    "DE": "de",
    "NL": "nl",
    "FR": "fr",
    "CA": "ca",
    "AU": "au",
    "IT": "it",
    "ES": "es",
    "PL": "pl",
}


async def fetch(params: FetchParams) -> list[NormalizedJob]:
    app_id = settings.adzuna_app_id.strip()
    app_key = settings.adzuna_app_key.strip()
    if not app_id or not app_key:
        logger.info("Adzuna skipped: ADZUNA_APP_ID/ADZUNA_APP_KEY not configured")
        return []

    country = COUNTRY_ALIASES.get(params.country.upper(), params.country.lower())
    url = f"https://api.adzuna.com/v1/api/jobs/{country}/search/{max(params.page, 1)}"
    data = await get_json(
        url,
        params={
            "app_id": app_id,
            "app_key": app_key,
            "what": params.query,
            "results_per_page": min(max(params.per_page, 1), 50),
            "content-type": "application/json",
            "sort_by": "date",
        },
    )
    rows = data.get("results") if isinstance(data, dict) else []
    jobs: list[NormalizedJob] = []
    for row in rows or []:
        job = _normalize(row, country)
        if job:
            jobs.append(job)
    return jobs


def _normalize(row: dict[str, Any], country: str) -> NormalizedJob | None:
    source_id = clean_text(row.get("id"))
    title = clean_text(row.get("title"))
    company = clean_text((row.get("company") or {}).get("display_name"))
    url = clean_text(row.get("redirect_url"))
    if not source_id or not title or not company or not url:
        return None
    location = clean_text((row.get("location") or {}).get("display_name")) or country.upper()
    description = clean_text(html.unescape(re.sub(r"<[^>]+>", " ", str(row.get("description") or ""))))
    category = clean_text((row.get("category") or {}).get("label"))
    tags = [tag for tag in [category, clean_text(row.get("contract_type")), clean_text(row.get("contract_time"))] if tag]
    return NormalizedJob(
        job_id=stable_job_id("adzuna", source_id),
        source="adzuna",
        source_job_id=source_id,
        title=title,
        company=company,
        location=location,
        country=country.upper(),
        remote="remote" in f"{title} {location} {description}".lower(),
        url=url,
        description=description,
        posted_date=iso_or_none(row.get("created")),
        salary_min=row.get("salary_min"),
        salary_max=row.get("salary_max"),
        raw_tags=tags,
        raw=row,
    )


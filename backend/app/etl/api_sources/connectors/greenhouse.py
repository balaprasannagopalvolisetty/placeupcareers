from __future__ import annotations

import html
import logging
import re
from typing import Any

from app.etl.api_sources.http import get_json
from app.etl.api_sources.schema import NormalizedJob, clean_text, iso_or_none, stable_job_id

logger = logging.getLogger(__name__)


async def fetch_board(token: str) -> list[NormalizedJob]:
    token = token.strip()
    if not token:
        return []
    url = f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs"
    data = await get_json(url, params={"content": "true"})
    rows = data.get("jobs") if isinstance(data, dict) else []
    jobs: list[NormalizedJob] = []
    for row in rows or []:
        job = _normalize(row, token)
        if job:
            jobs.append(job)
    return jobs


def _normalize(row: dict[str, Any], token: str) -> NormalizedJob | None:
    source_id = clean_text(row.get("id"))
    title = clean_text(row.get("title"))
    company = clean_text(token.replace("-", " ").replace("_", " ").title())
    url = clean_text(row.get("absolute_url"))
    if not source_id or not title or not url:
        return None
    offices = row.get("offices") if isinstance(row.get("offices"), list) else []
    locations = [clean_text(office.get("name")) for office in offices if isinstance(office, dict)]
    location = ", ".join([loc for loc in locations if loc]) or "Global"
    country = _infer_country(location)
    content = row.get("content") or ""
    description = clean_text(html.unescape(re.sub(r"<[^>]+>", " ", str(content))))
    departments = row.get("departments") if isinstance(row.get("departments"), list) else []
    tags = [clean_text(dept.get("name")) for dept in departments if isinstance(dept, dict) and clean_text(dept.get("name"))]
    return NormalizedJob(
        job_id=stable_job_id("greenhouse", source_id),
        source="greenhouse",
        source_job_id=source_id,
        title=title,
        company=company,
        location=location,
        country=country,
        remote="remote" in f"{title} {location} {description}".lower(),
        url=url,
        description=description,
        posted_date=iso_or_none(row.get("updated_at")),
        raw_tags=tags,
        raw=row,
    )


def _infer_country(location: str) -> str:
    low = location.lower()
    if "canada" in low or "toronto" in low or "vancouver" in low:
        return "CA"
    if "london" in low or "united kingdom" in low or "uk" in low:
        return "GB"
    if "germany" in low or "berlin" in low or "munich" in low:
        return "DE"
    if "netherlands" in low or "amsterdam" in low:
        return "NL"
    if "france" in low or "paris" in low:
        return "FR"
    if "remote" in low or "global" in low:
        return "US"
    return "US"


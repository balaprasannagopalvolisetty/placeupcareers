"""Remotive connector — free public JSON feed of remote, English-language roles.

https://remotive.com/api/remote-jobs  (no auth). Emits NormalizedJob.
"""
from __future__ import annotations

import html
import logging
import re
from typing import Any

from app.etl.api_sources.http import get_json
from app.etl.api_sources.schema import NormalizedJob, clean_text, iso_or_none, stable_job_id

logger = logging.getLogger(__name__)

REMOTIVE_URL = "https://remotive.com/api/remote-jobs"
_VISA_HINTS = ("visa", "sponsorship", "relocation", "relocate")


def _country(location: str) -> str:
    low = location.lower()
    table = {
        "usa": "US", "united states": "US", "canada": "CA", "uk": "GB",
        "united kingdom": "GB", "germany": "DE", "netherlands": "NL", "france": "FR",
        "ireland": "IE", "australia": "AU", "singapore": "SG", "spain": "ES",
    }
    for needle, code in table.items():
        if needle in low:
            return code
    return ""


def _normalize(row: dict[str, Any]) -> NormalizedJob | None:
    if not isinstance(row, dict):
        return None
    source_id = clean_text(row.get("id"))
    title = clean_text(row.get("title"))
    company = clean_text(row.get("company_name"))
    url = clean_text(row.get("url"))
    if not source_id or not title or not company or not url:
        return None
    location = clean_text(row.get("candidate_required_location")) or "Remote"
    description = clean_text(html.unescape(re.sub(r"<[^>]+>", " ", str(row.get("description") or ""))))
    tags = [clean_text(t) for t in (row.get("tags") or []) if clean_text(t)]
    blob = f"{title} {description} {' '.join(tags)}".lower()
    return NormalizedJob(
        job_id=stable_job_id("remotive", source_id),
        source="remotive",
        source_job_id=source_id,
        title=title,
        company=company,
        location=location,
        country=_country(location),
        remote=True,
        url=url,
        description=description,
        posted_date=iso_or_none(row.get("publication_date")),
        raw_tags=tags,
        sponsor_signal="likely" if any(h in blob for h in _VISA_HINTS) else None,
        raw=row,
    )


async def fetch() -> list[NormalizedJob]:
    data = await get_json(REMOTIVE_URL)
    rows = data.get("jobs") if isinstance(data, dict) else None
    if not isinstance(rows, list):
        return []
    jobs: list[NormalizedJob] = []
    for row in rows:
        job = _normalize(row)
        if job:
            jobs.append(job)
    return jobs

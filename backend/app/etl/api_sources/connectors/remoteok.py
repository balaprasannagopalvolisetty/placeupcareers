"""RemoteOK connector — free public JSON feed of remote, English-language roles.

https://remoteok.com/api  (no auth). The first array element is a legal/
metadata object and is skipped. Emits NormalizedJob for the api_sources runner.
"""
from __future__ import annotations

import logging
from typing import Any

from app.etl.api_sources.http import get_json
from app.etl.api_sources.schema import NormalizedJob, clean_text, iso_or_none, stable_job_id

logger = logging.getLogger(__name__)

REMOTEOK_URL = "https://remoteok.com/api"
_HEADERS = {"User-Agent": "PlaceUpCareerBot/1.0 (+https://placeupcareer.com)"}
_VISA_HINTS = ("visa", "sponsorship", "relocation", "relocate")


def _country(location: str) -> str:
    low = location.lower()
    table = {
        "united states": "US", "usa": "US", "canada": "CA", "united kingdom": "GB",
        "uk": "GB", "germany": "DE", "netherlands": "NL", "france": "FR", "ireland": "IE",
        "australia": "AU", "singapore": "SG", "india": "IN", "spain": "ES",
    }
    for needle, code in table.items():
        if needle in low:
            return code
    return ""  # remote/unspecified → runner fills via infer_country


def _normalize(row: dict[str, Any]) -> NormalizedJob | None:
    if not isinstance(row, dict) or not row.get("position"):
        return None
    source_id = clean_text(row.get("id") or row.get("slug"))
    title = clean_text(row.get("position"))
    company = clean_text(row.get("company"))
    url = clean_text(row.get("url") or row.get("apply_url"))
    if not source_id or not title or not company:
        return None
    location = clean_text(row.get("location")) or "Remote"
    tags = [clean_text(t) for t in (row.get("tags") or []) if clean_text(t)]
    description = clean_text(row.get("description"))
    blob = f"{title} {description} {' '.join(tags)}".lower()
    return NormalizedJob(
        job_id=stable_job_id("remoteok", source_id),
        source="remoteok",
        source_job_id=source_id,
        title=title,
        company=company,
        location=location,
        country=_country(location),
        remote=True,
        url=url,
        description=description,
        posted_date=iso_or_none(row.get("date") or row.get("epoch")),
        salary_min=row.get("salary_min") if isinstance(row.get("salary_min"), (int, float)) else None,
        salary_max=row.get("salary_max") if isinstance(row.get("salary_max"), (int, float)) else None,
        raw_tags=tags,
        sponsor_signal="likely" if any(h in blob for h in _VISA_HINTS) else None,
        raw=row,
    )


async def fetch() -> list[NormalizedJob]:
    data = await get_json(REMOTEOK_URL, headers=_HEADERS)
    if not isinstance(data, list):
        return []
    jobs: list[NormalizedJob] = []
    for row in data:
        job = _normalize(row)
        if job:
            jobs.append(job)
    return jobs

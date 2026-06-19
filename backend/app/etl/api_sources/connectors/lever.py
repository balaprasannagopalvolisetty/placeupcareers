"""Lever public job-board API connector (free, no auth).

  GET https://api.lever.co/v0/postings/{token}?mode=json
Returns full plain-text descriptions and canonical hostedUrl apply links —
the free, direct-career-page equivalent of a paid feed.
"""
from __future__ import annotations

import logging
from typing import Any

from app.etl.api_sources.http import get_json
from app.etl.api_sources.schema import NormalizedJob, clean_text, iso_or_none, stable_job_id
from app.services.job_filters import requires_us_clearance

logger = logging.getLogger(__name__)


async def fetch_board(token: str) -> list[NormalizedJob]:
    token = (token or "").strip()
    if not token:
        return []
    data = await get_json(f"https://api.lever.co/v0/postings/{token}", params={"mode": "json"})
    rows = data if isinstance(data, list) else []
    out: list[NormalizedJob] = []
    for row in rows:
        if isinstance(row, dict):
            job = _normalize(row, token)
            if job:
                out.append(job)
    return out


def _normalize(row: dict[str, Any], token: str) -> NormalizedJob | None:
    title = clean_text(row.get("text"))
    url = clean_text(row.get("hostedUrl") or row.get("applyUrl"))
    if not title or not url:
        return None
    categories = row.get("categories") or {}
    location = clean_text(categories.get("location") if isinstance(categories, dict) else "") or "Remote"
    desc = row.get("descriptionPlain") or row.get("description") or ""
    description = clean_text(desc)
    if requires_us_clearance(f"{title} {description}"):
        return None
    source_id = clean_text(row.get("id")) or url
    return NormalizedJob(
        job_id=stable_job_id("lever", source_id),
        source="lever",
        source_job_id=source_id,
        title=title,
        company=clean_text(token.replace("-", " ").title()),
        location=location,
        country=_country(location),
        remote="remote" in f"{location} {description}".lower(),
        url=url,
        description=description,
        posted_date=iso_or_none(row.get("createdAt")),
        raw_tags=["Lever"],
        raw=row,
    )


def _country(location: str) -> str:
    low = location.lower()
    if "canada" in low: return "CA"
    if "united kingdom" in low or "london" in low: return "GB"
    if "germany" in low: return "DE"
    if "india" in low: return "IN"
    return "US"

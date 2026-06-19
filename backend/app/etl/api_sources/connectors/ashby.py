"""Ashby public job-board API connector (free, no auth).

  GET https://api.ashbyhq.com/posting-api/job-board/{token}
Returns full descriptions + canonical jobUrl apply links.
"""
from __future__ import annotations

import html
import logging
import re
from typing import Any

from app.etl.api_sources.http import get_json
from app.etl.api_sources.schema import NormalizedJob, clean_text, iso_or_none, stable_job_id
from app.services.job_filters import requires_us_clearance

logger = logging.getLogger(__name__)


async def fetch_board(token: str) -> list[NormalizedJob]:
    token = (token or "").strip()
    if not token:
        return []
    data = await get_json(f"https://api.ashbyhq.com/posting-api/job-board/{token}")
    rows = data.get("jobs") if isinstance(data, dict) else []
    out: list[NormalizedJob] = []
    for row in rows or []:
        if isinstance(row, dict):
            job = _normalize(row, token)
            if job:
                out.append(job)
    return out


def _normalize(row: dict[str, Any], token: str) -> NormalizedJob | None:
    title = clean_text(row.get("title"))
    url = clean_text(row.get("jobUrl") or row.get("applyUrl"))
    if not title or not url:
        return None
    location = clean_text(row.get("location") or (row.get("address") or {}).get("postalAddress", "") if isinstance(row.get("address"), dict) else row.get("location")) or "Remote"
    raw_desc = row.get("descriptionPlain") or row.get("descriptionHtml") or ""
    description = clean_text(html.unescape(re.sub(r"<[^>]+>", " ", str(raw_desc))))
    if requires_us_clearance(f"{title} {description}"):
        return None
    source_id = clean_text(row.get("id")) or url
    return NormalizedJob(
        job_id=stable_job_id("ashby", source_id),
        source="ashby",
        source_job_id=source_id,
        title=title,
        company=clean_text(token.replace("-", " ").title()),
        location=location,
        country="US",
        remote=bool(row.get("isRemote")) or "remote" in f"{location} {description}".lower(),
        url=url,
        description=description,
        posted_date=iso_or_none(row.get("publishedAt") or row.get("updatedAt")),
        raw_tags=["Ashby"],
        raw=row,
    )

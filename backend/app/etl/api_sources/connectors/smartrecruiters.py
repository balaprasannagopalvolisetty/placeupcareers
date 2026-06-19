"""SmartRecruiters public postings API connector (free, no auth).

  GET https://api.smartrecruiters.com/v1/companies/{token}/postings
List carries title/location/apply ref; the jobAd section (when present) gives
the description. Canonical apply URL via the posting ref.
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
    data = await get_json(
        f"https://api.smartrecruiters.com/v1/companies/{token}/postings",
        params={"limit": 100},
    )
    rows = data.get("content") if isinstance(data, dict) else []
    out: list[NormalizedJob] = []
    for row in rows or []:
        if isinstance(row, dict):
            job = _normalize(row, token)
            if job:
                out.append(job)
    return out


def _normalize(row: dict[str, Any], token: str) -> NormalizedJob | None:
    title = clean_text(row.get("name"))
    pid = clean_text(row.get("id") or row.get("uuid"))
    if not title or not pid:
        return None
    company = clean_text((row.get("company") or {}).get("name") if isinstance(row.get("company"), dict) else token)
    loc = row.get("location") or {}
    location = clean_text(", ".join([str(loc.get(k, "")) for k in ("city", "region", "country") if loc.get(k)])) or "Remote"
    url = f"https://jobs.smartrecruiters.com/{token}/{pid}"
    job_ad = row.get("jobAd") or {}
    sections = (job_ad.get("sections") if isinstance(job_ad, dict) else {}) or {}
    parts = []
    for key in ("jobDescription", "qualifications", "responsibilities"):
        sec = sections.get(key) or {}
        if isinstance(sec, dict) and sec.get("text"):
            parts.append(str(sec["text"]))
    description = clean_text(html.unescape(re.sub(r"<[^>]+>", " ", " ".join(parts))))
    if requires_us_clearance(f"{title} {description}"):
        return None
    return NormalizedJob(
        job_id=stable_job_id("smartrecruiters", pid),
        source="smartrecruiters",
        source_job_id=pid,
        title=title,
        company=company or clean_text(token),
        location=location,
        country="US",
        remote="remote" in f"{location} {description}".lower(),
        url=url,
        description=description,
        posted_date=iso_or_none(row.get("releasedDate") or row.get("createdOn")),
        raw_tags=["SmartRecruiters"],
        raw=row,
    )

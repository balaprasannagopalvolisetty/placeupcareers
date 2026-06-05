"""Jobicy connector — free public JSON feed of remote, English-language roles.

https://jobicy.com/api/v2/remote-jobs  (no auth). Emits NormalizedJob.
"""
from __future__ import annotations

import html
import logging
import re
from typing import Any

from app.etl.api_sources.http import get_json
from app.etl.api_sources.schema import NormalizedJob, clean_text, iso_or_none, stable_job_id

logger = logging.getLogger(__name__)

JOBICY_URL = "https://jobicy.com/api/v2/remote-jobs"
_VISA_HINTS = ("visa", "sponsorship", "relocation", "relocate")


def _country(geo: str) -> str:
    low = geo.lower()
    table = {
        "usa": "US", "united states": "US", "canada": "CA", "uk": "GB",
        "united kingdom": "GB", "germany": "DE", "netherlands": "NL", "france": "FR",
        "ireland": "IE", "australia": "AU", "singapore": "SG", "europe": "",
    }
    for needle, code in table.items():
        if needle in low:
            return code
    return ""


def _normalize(row: dict[str, Any]) -> NormalizedJob | None:
    if not isinstance(row, dict):
        return None
    source_id = clean_text(row.get("id"))
    title = clean_text(row.get("jobTitle"))
    company = clean_text(row.get("companyName"))
    url = clean_text(row.get("url"))
    if not source_id or not title or not company or not url:
        return None
    geo = clean_text(row.get("jobGeo")) or "Anywhere"
    description = clean_text(html.unescape(re.sub(r"<[^>]+>", " ", str(row.get("jobExcerpt") or row.get("jobDescription") or ""))))
    blob = f"{title} {description}".lower()
    smin = row.get("annualSalaryMin")
    smax = row.get("annualSalaryMax")
    return NormalizedJob(
        job_id=stable_job_id("jobicy", source_id),
        source="jobicy",
        source_job_id=source_id,
        title=title,
        company=company,
        location=geo,
        country=_country(geo),
        remote=True,
        url=url,
        description=description,
        posted_date=iso_or_none(row.get("pubDate")),
        salary_min=float(smin) if isinstance(smin, (int, float, str)) and str(smin).replace(".", "").isdigit() else None,
        salary_max=float(smax) if isinstance(smax, (int, float, str)) and str(smax).replace(".", "").isdigit() else None,
        sponsor_signal="likely" if any(h in blob for h in _VISA_HINTS) else None,
        raw=row,
    )


async def fetch() -> list[NormalizedJob]:
    data = await get_json(JOBICY_URL)
    rows = data.get("jobs") if isinstance(data, dict) else None
    if not isinstance(rows, list):
        return []
    jobs: list[NormalizedJob] = []
    for row in rows:
        job = _normalize(row)
        if job:
            jobs.append(job)
    return jobs

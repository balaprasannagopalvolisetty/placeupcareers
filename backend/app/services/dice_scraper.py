"""
PlaceUp Career — Dice Scraper

Pulls open tech job postings from Dice.com via their public search API
(used by the dice.com web UI itself). No authenticated key is required, but
results may be paginated and rate-limited.

Endpoint discovered from the Dice web app:
    GET https://job-search-api.svc.dhigroupinc.com/v1/dice/jobs/search

Returns normalized JobPost objects compatible with the rest of the pipeline.

This module degrades gracefully — if Dice changes their API contract or
applies anti-bot, the function returns [] and logs a warning instead of
raising.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any, Optional

import httpx

from app.models.job import (
    JobCategory,
    JobPost,
    JobSource,
    SalaryRange,
)
from app.utils.deduplication import generate_content_hash, generate_job_id

logger = logging.getLogger(__name__)


DICE_SEARCH_URL = "https://job-search-api.svc.dhigroupinc.com/v1/dice/jobs/search"

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Origin": "https://www.dice.com",
    "Referer": "https://www.dice.com/",
    "x-api-key": "1YAt0R9wBg4WfsF9VB2778F5CHLAPMVW3WAZcKd8",  # Public key embedded in dice.com JS
}


def _safe_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _parse_dt(value: Any) -> Optional[datetime]:
    if not value:
        return None
    try:
        text = str(value).replace("Z", "+00:00")
        return datetime.fromisoformat(text)
    except (ValueError, TypeError):
        return None


def _parse_salary(salary_text: str) -> Optional[SalaryRange]:
    """Best-effort salary parser for strings like '$120K - $160K' or '120000 - 160000'."""
    if not salary_text:
        return None
    import re

    text = salary_text.replace(",", "").replace("$", "")
    nums = re.findall(r"(\d+(?:\.\d+)?)\s*[Kk]?", text)
    if not nums:
        return None

    multiplier = 1000.0 if "k" in salary_text.lower() else 1.0
    period = "yearly"
    if "hour" in salary_text.lower():
        period = "hourly"
        multiplier = 1.0
    elif "month" in salary_text.lower():
        period = "monthly"

    try:
        values = [float(n) * multiplier for n in nums[:2]]
    except ValueError:
        return None

    min_v = values[0] if values else None
    max_v = values[1] if len(values) > 1 else None
    return SalaryRange(min_salary=min_v, max_salary=max_v, currency="USD", period=period)


async def scrape_dice(
    search_term: str,
    location: str = "United States",
    *,
    results_wanted: int = 100,
    page_size: int = 20,
    posted_within_days: Optional[int] = 14,
    proxy: Optional[str] = None,
) -> list[JobPost]:
    """Scrape Dice for the given query, paginating through results."""
    if not search_term:
        return []

    transport = httpx.AsyncHTTPTransport(retries=2, proxy=proxy) if proxy else None

    def _build_params(*, simple: bool, page_number: int) -> dict[str, Any]:
        params: dict[str, Any] = {
            "q": search_term,
            "countryCode2": "US",
            "page": page_number,
            "pageSize": page_size,
            "fields": (
                "id|jobId|guid|summary|title|postedDate|modifiedDate|jobLocation.displayName|"
                "detailsPageUrl|salary|clientBrandId|companyPageUrl|companyLogoUrl|"
                "positionId|companyName|employmentType|isHighlighted|score|easyApply|"
                "employerType|workFromHomeAvailability|workplaceTypes|isRemote"
            ),
            "culture": "en",
            "includeRemote": "true",
        }
        if not simple:
            params.update({
                "radius": "30",
                "radiusUnit": "mi",
                "facets": "employmentType|postedDate|workFromHomeAvailability|easyApply",
                "recommendations": "true",
                "interactionId": "0",
                "fj": "true",
            })
            if posted_within_days:
                params["filters.postedDate"] = f"LAST_{posted_within_days}_DAYS"
        if location and location.lower() not in {"united states", "usa", "us", ""}:
            params["location"] = location
        return params

    async with httpx.AsyncClient(
        timeout=30.0,
        headers=DEFAULT_HEADERS,
        transport=transport,
        follow_redirects=True,
    ) as client:
        jobs: list[JobPost] = []
        page = 1
        max_pages = max(1, (results_wanted + page_size - 1) // page_size)

        while len(jobs) < results_wanted and page <= max_pages:
            try:
                response = await client.get(DICE_SEARCH_URL, params=_build_params(simple=False, page_number=page))
                if response.status_code >= 500:
                    logger.info("Dice page %s returned %s; retrying with simplified query", page, response.status_code)
                    response = await client.get(DICE_SEARCH_URL, params=_build_params(simple=True, page_number=page))
                if response.status_code == 401 or response.status_code == 403:
                    logger.info(
                        "Dice: unauthorized/forbidden (status=%s). API key or anti-bot may have changed.",
                        response.status_code,
                    )
                    return jobs
                response.raise_for_status()
                payload = response.json()
            except (httpx.HTTPError, ValueError) as exc:
                logger.info("Dice page %s unavailable after fallback (%s)", page, exc)
                break

            items = payload.get("data") if isinstance(payload, dict) else None
            if not isinstance(items, list) or not items:
                break

            for item in items:
                try:
                    job = _dice_item_to_jobpost(item)
                    if job:
                        jobs.append(job)
                        if len(jobs) >= results_wanted:
                            break
                except Exception as exc:  # noqa: BLE001
                    logger.debug("Dice: skip item: %s", exc)
                    continue

            # Polite pacing between pages
            await asyncio.sleep(0.6)
            page += 1

        logger.info("Dice: %s jobs for '%s' @ %s", len(jobs), search_term, location)
        return jobs


def _dice_item_to_jobpost(item: dict) -> Optional[JobPost]:
    title = _safe_str(item.get("title"))
    company = _safe_str(item.get("companyName"))
    location = _safe_str(
        (item.get("jobLocation") or {}).get("displayName")
        if isinstance(item.get("jobLocation"), dict)
        else item.get("jobLocation")
    )

    if not title or not company:
        return None

    description = _safe_str(item.get("summary"))
    detail_url = _safe_str(item.get("detailsPageUrl"))
    if detail_url and not detail_url.startswith("http"):
        detail_url = f"https://www.dice.com{detail_url if detail_url.startswith('/') else '/' + detail_url}"

    salary = _parse_salary(_safe_str(item.get("salary")))
    posted_at = _parse_dt(item.get("postedDate"))

    is_remote = bool(item.get("isRemote"))
    workplace_types = item.get("workplaceTypes") or []
    if isinstance(workplace_types, list) and any(
        "remote" in str(w).lower() for w in workplace_types
    ):
        is_remote = True

    job_id = generate_job_id(title, company, location or detail_url or "remote")

    extra: dict[str, Any] = {
        "ats": "dice",
        "dice_job_id": _safe_str(item.get("jobId") or item.get("id")),
        "guid": _safe_str(item.get("guid")),
        "easy_apply": item.get("easyApply"),
        "employer_type": _safe_str(item.get("employerType")),
        "workplace_types": workplace_types,
        "score": item.get("score"),
        "company_logo_url": _safe_str(item.get("companyLogoUrl")),
        "modified_date": _safe_str(item.get("modifiedDate")),
        "highlighted": item.get("isHighlighted"),
    }

    return JobPost(
        id=job_id,
        title=title,
        company=company,
        location=location,
        description=description,
        job_url=detail_url,
        category=JobCategory.TECHNOLOGY,
        job_type=_safe_str(item.get("employmentType")),
        salary=salary,
        source=JobSource.DICE,
        source_job_id=_safe_str(item.get("jobId") or item.get("id")),
        posted_at=posted_at,
        is_remote=is_remote,
        company_url=_safe_str(item.get("companyPageUrl")),
        company_logo=_safe_str(item.get("companyLogoUrl")),
        content_hash=generate_content_hash(title, company, location or "remote"),
        scraped_at=datetime.utcnow(),
        extra_metadata={k: v for k, v in extra.items() if v not in (None, "", [], {})},
    )

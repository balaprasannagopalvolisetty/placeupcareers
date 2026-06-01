"""ScrapeGraphAI discovery source for direct career pages and job search pages."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any
from urllib.parse import urlparse

from app.config import settings
from app.etl.scrapegraph_targets import iter_targets
from app.models.job import JobCategory, JobPost, JobSource, VisaBadges
from app.services.visa_classifier import classify_job
from app.utils.deduplication import generate_content_hash, generate_job_id

logger = logging.getLogger(__name__)


SCRAPEGRAPH_DISCOVERY_PROMPT = """
Extract current job postings from this page. Return JSON with a top-level
"jobs" array. Each job must include: title, company, location, job_url,
description, posted_at, employment_type, salary_range, visa_notes.

Only include real job postings or job search results visible on this page.
Ignore navigation, cookie banners, unrelated recommendations, duplicate cards,
talent communities, closed jobs, internships unrelated to OPT/CPT, and marketing
text. Prefer roles in PlaceUp target countries and English-friendly postings.
Keep descriptions concise.
"""


def _is_enabled() -> bool:
    if not settings.scrapegraph_discovery_enabled:
        return False
    if not settings.openrouter_api_key.strip():
        logger.warning("ScrapeGraphAI discovery enabled but OPENROUTER_API_KEY is not configured")
        return False
    return True


def _graph_config() -> dict[str, Any]:
    model = settings.openrouter_model.strip() or "anthropic/claude-3.5-haiku"
    if not model.startswith("oneapi/"):
        model = f"oneapi/{model}"
    return {
        "llm": {
            "api_key": settings.openrouter_api_key,
            "model": model,
            "base_url": settings.openrouter_base_url,
            "format": "json",
        },
        "headless": True,
        "verbose": False,
        "html_mode": True,
        "headers": {
            "HTTP-Referer": settings.openrouter_referer,
            "X-Title": "PlaceUp Career",
        },
    }


def _extra_career_urls() -> list[str]:
    return [url.strip() for url in settings.scrapegraph_career_pages.split(",") if url.strip()]


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        for key in ("jobs", "positions", "openings", "results", "items"):
            nested = value.get(key)
            if isinstance(nested, list):
                return nested
    return []


def _first_text(*values: Any) -> str:
    for value in values:
        if value is None:
            continue
        if isinstance(value, (list, tuple)):
            text = "\n".join(str(item).strip() for item in value if str(item).strip())
        elif isinstance(value, dict):
            text = " ".join(str(v).strip() for v in value.values() if str(v).strip())
        else:
            text = str(value).strip()
        if text:
            return text
    return ""


def _normalize_url(url: str, fallback_url: str) -> str:
    clean = (url or "").strip()
    if not clean:
        return fallback_url
    if clean.startswith("/"):
        parsed = urlparse(fallback_url)
        return f"{parsed.scheme}://{parsed.netloc}{clean}"
    return clean


def _parse_posted_at(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _result_to_jobs(result: dict[str, Any], target: dict[str, Any]) -> list[JobPost]:
    from app.services.job_filters import is_target_country_scope, is_target_experience, parse_years

    jobs: list[JobPost] = []
    for raw in _as_list(result):
        if not isinstance(raw, dict):
            continue
        title = _first_text(raw.get("title"), raw.get("job_title"), raw.get("position"))
        company = _first_text(raw.get("company"), raw.get("company_name"), target.get("company"))
        location = _first_text(raw.get("location"), raw.get("job_location"), raw.get("locations"))
        if not title or not company:
            continue
        description = _first_text(
            raw.get("description"),
            raw.get("summary"),
            raw.get("responsibilities"),
            raw.get("requirements"),
            raw.get("visa_notes"),
        )
        job_url = _normalize_url(
            _first_text(raw.get("job_url"), raw.get("apply_url"), raw.get("url"), raw.get("link")),
            str(target.get("url") or ""),
        )
        geo_text = f"{location} {target.get('location') or ''} {title}"
        if not is_target_country_scope(geo_text):
            continue
        ymin, ymax = parse_years(f"{title}\n{description}")
        if not is_target_experience(title, ymin, ymax, max_years=10):
            continue

        job_id = generate_job_id(title, company, location or "Remote")
        visa_notes = _first_text(raw.get("visa_notes"), raw.get("sponsorship"), raw.get("visa"))
        visa_result = classify_job(title=title, company=company, description=f"{description}\n{visa_notes}")
        extra = {
            "scrapegraph_discovery": True,
            "target_kind": target.get("kind"),
            "target_url": target.get("url"),
            "target_query": target.get("query"),
            "years_min": ymin,
            "years_max": ymax,
            "target_experience": True,
            "target_experience_max_years": 10,
        }
        jobs.append(
            JobPost(
                id=job_id,
                title=title,
                company=company,
                location=location or "Remote",
                description=description,
                job_url=job_url,
                category=JobCategory.OTHER,
                job_type=_first_text(raw.get("employment_type"), raw.get("job_type")),
                source=JobSource.SCRAPEGRAPH_DISCOVERY,
                source_job_id=f"{target.get('kind') or 'scrapegraph'}:{generate_content_hash(title, company, job_url or location)}",
                posted_at=_parse_posted_at(raw.get("posted_at") or raw.get("date_posted")),
                content_hash=generate_content_hash(title, company, location or job_url),
                visa=VisaBadges(
                    visa_opt=visa_result.visa_opt,
                    visa_stem_opt=visa_result.visa_stem_opt,
                    visa_h1b=visa_result.visa_h1b,
                    h1b_verified=visa_result.h1b_verified,
                    no_sponsorship=visa_result.should_discard,
                    visa_score=visa_result.score,
                ),
                extra_metadata=extra,
            )
        )
    return jobs


def _run_target(target: dict[str, Any]) -> list[JobPost]:
    from scrapegraphai.graphs import SmartScraperGraph

    graph = SmartScraperGraph(
        prompt=SCRAPEGRAPH_DISCOVERY_PROMPT,
        source=str(target["url"]),
        config=_graph_config(),
    )
    result = graph.run()
    return _result_to_jobs(result if isinstance(result, dict) else {"jobs": result}, target)


async def scrape_scrapegraph_discovery() -> list[JobPost]:
    """Scrape bounded AI-discovery targets with OpenRouter-backed ScrapeGraphAI."""
    if not _is_enabled():
        return []

    targets = iter_targets(extra_career_urls=_extra_career_urls())
    max_urls = settings.scrapegraph_discovery_max_urls
    if max_urls > 0:
        targets = targets[:max_urls]
    if not targets:
        return []

    logger.info("ScrapeGraphAI discovery: scraping %s targets", len(targets))
    semaphore = asyncio.Semaphore(settings.scrapegraph_discovery_concurrency)
    discovered: list[JobPost] = []

    async def _scrape(target: dict[str, Any]) -> None:
        async with semaphore:
            try:
                jobs = await asyncio.wait_for(asyncio.to_thread(_run_target, target), timeout=120)
                discovered.extend(jobs)
                logger.info("ScrapeGraphAI discovery: %s jobs from %s", len(jobs), target.get("url"))
            except ImportError:
                logger.warning("ScrapeGraphAI package is not installed; skipping discovery")
            except Exception as exc:
                logger.info("ScrapeGraphAI discovery skipped target %s: %s", target.get("url"), exc)

    await asyncio.gather(*[_scrape(target) for target in targets])
    logger.info("ScrapeGraphAI discovery: discovered %s jobs", len(discovered))
    return discovered

"""Optional ScrapeGraphAI-powered job detail enrichment."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.config import settings
from app.models.job import JobPost

logger = logging.getLogger(__name__)


SCRAPEGRAPH_JOB_PROMPT = """
Extract a job posting from this page as JSON with these fields:
title, company, location, responsibilities, requirements, nice_to_have,
employment_type, salary_range, visa_notes.
Return concise bullet arrays for responsibilities, requirements, and nice_to_have.
Ignore navigation, cookie notices, unrelated recommended jobs, ads, and page chrome.
"""


def _is_enabled() -> bool:
    return bool(settings.scrapegraph_enabled and settings.openrouter_api_key.strip())


def _needs_enrichment(job: JobPost) -> bool:
    if not getattr(job, "job_url", ""):
        return False
    description = (getattr(job, "description", "") or "").strip()
    return len(description) < settings.scrapegraph_min_description_chars


def _join_points(points: Any) -> str:
    if isinstance(points, list):
        return "\n".join(f"- {str(point).strip()}" for point in points if str(point).strip())
    if isinstance(points, str):
        return points.strip()
    return ""


def _description_from_result(result: dict[str, Any]) -> str:
    sections: list[str] = []
    for label, key in (
        ("Responsibilities", "responsibilities"),
        ("Requirements", "requirements"),
        ("Nice to have", "nice_to_have"),
        ("Visa notes", "visa_notes"),
    ):
        text = _join_points(result.get(key))
        if text:
            sections.append(f"{label}:\n{text}")
    return "\n\n".join(sections).strip()


def _run_scrapegraph(job: JobPost) -> dict[str, Any]:
    from scrapegraphai.graphs import SmartScraperGraph

    model = settings.openrouter_model.strip() or "anthropic/claude-3.5-haiku"
    if not model.startswith("oneapi/"):
        model = f"oneapi/{model}"
    graph_config = {
        "llm": {
            "api_key": settings.openrouter_api_key,
            "model": model,
            "base_url": settings.openrouter_base_url,
            "format": "json",
        },
        "headers": {
            "HTTP-Referer": settings.openrouter_referer,
            "X-Title": "PlaceUp Career",
        },
        "headless": True,
        "verbose": False,
        "html_mode": True,
    }
    graph = SmartScraperGraph(
        prompt=SCRAPEGRAPH_JOB_PROMPT,
        source=job.job_url,
        config=graph_config,
    )
    result = graph.run()
    return result if isinstance(result, dict) else {}


async def enrich_jobs_with_scrapegraph(jobs: list[JobPost]) -> int:
    """Repair thin job details with ScrapeGraphAI when explicitly enabled.

    The feature is intentionally guarded. Broad discovery still comes from
    JobSpy/H1B; this only fills weak descriptions from the canonical detail URL.
    """
    if not _is_enabled():
        if settings.scrapegraph_enabled and not settings.openrouter_api_key.strip():
            logger.warning("ScrapeGraphAI enrichment enabled but OPENROUTER_API_KEY is not configured")
        return 0

    candidates = [job for job in jobs if _needs_enrichment(job)]
    if not candidates:
        return 0

    candidates = candidates[: settings.scrapegraph_max_enrich_per_run]
    logger.info("ScrapeGraphAI: enriching %s thin job descriptions", len(candidates))

    enriched = 0
    semaphore = asyncio.Semaphore(2)

    async def _enrich(job: JobPost) -> None:
        nonlocal enriched
        async with semaphore:
            try:
                result = await asyncio.wait_for(
                    asyncio.to_thread(_run_scrapegraph, job),
                    timeout=75,
                )
                description = _description_from_result(result)
                if len(description) > len((job.description or "").strip()):
                    job.description = description
                    extra = job.extra_metadata or {}
                    if not isinstance(extra, dict):
                        extra = {}
                    extra["scrapegraph"] = {
                        "enriched": True,
                        "fields": sorted(k for k, v in result.items() if v),
                    }
                    job.extra_metadata = extra
                    enriched += 1
            except ImportError:
                logger.warning("ScrapeGraphAI package is not installed; skipping enrichment")
            except Exception as exc:
                logger.info("ScrapeGraphAI enrichment skipped for %s: %s", job.job_url, exc)

    await asyncio.gather(*[_enrich(job) for job in candidates])
    logger.info("ScrapeGraphAI: enriched %s jobs", enriched)
    return enriched

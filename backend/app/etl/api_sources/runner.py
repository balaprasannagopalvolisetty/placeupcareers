from __future__ import annotations

import argparse
import asyncio
import logging
import os
from datetime import datetime
from typing import Awaitable, Callable, Iterable

from sqlalchemy.orm import Session

from app.db.postgres import PostgresClient
from app.etl.api_sources.connectors import adzuna, greenhouse, remoteok, remotive, jobicy, career_site_feed
from app.etl.api_sources.firestore_sink import upsert_jobs as upsert_firestore_jobs
from app.etl.api_sources.registry import ADZUNA_COUNTRIES, load_registry
from app.etl.api_sources.schema import FetchParams, NormalizedJob
from app.etl.loaders.jobs import load_normalized_jobs
from app.etl.master_jobs import rebuild_master_jobs
from app.etl.normalizers.jobs import infer_country
from app.job_taxonomy import all_role_names
from app.services.global_visa_rules import normalize_country_code
from app.utils.deduplication import generate_content_hash

logger = logging.getLogger(__name__)


def _filter_requested_countries(
    rows: list[NormalizedJob],
    countries: list[str] | None,
) -> list[NormalizedJob]:
    """Enforce country isolation for whole-board ATS connectors.

    Greenhouse/Lever/Ashby/SmartRecruiters APIs return an entire company board,
    unlike query-based providers. Without this post-fetch boundary, every one
    of the 32 country matrix jobs persisted the same global board rows. Unknown
    remote locations remain acceptable only for a multi-country/global pass;
    a single-country job must have evidence for that country.
    """
    requested = {
        code
        for value in (countries or [])
        if (code := normalize_country_code(value))
    }
    if not requested:
        return rows
    allow_unknown = len(requested) > 1
    filtered: list[NormalizedJob] = []
    for job in rows:
        country = normalize_country_code(job.country) or normalize_country_code(infer_country(job.location))
        if country in requested or (not country and allow_unknown):
            filtered.append(job)
    return filtered


async def fetch_all(
    *,
    queries: list[str],
    countries: list[str] | None = None,
    sources: str = "adzuna~greenhouse",
    per_page: int = 50,
    on_batch: Callable[[str, list[NormalizedJob]], Awaitable[None]] | None = None,
) -> list[NormalizedJob]:
    enabled = {item.strip().lower() for item in sources.replace(",", "~").split("~") if item.strip()}
    jobs: list[NormalizedJob] = []
    tasks: list[tuple[str, asyncio.Task[list[NormalizedJob]]]] = []

    if "adzuna" in enabled:
        requested_countries = countries or ADZUNA_COUNTRIES
        adzuna_countries = []
        for country in requested_countries:
            normalized_country = adzuna.COUNTRY_ALIASES.get(country.upper(), country.lower())
            if normalized_country in ADZUNA_COUNTRIES:
                adzuna_countries.append(normalized_country)
        for country in list(dict.fromkeys(adzuna_countries)):
            for query in queries:
                tasks.append((f"adzuna:{country}:{query}", asyncio.create_task(
                    adzuna.fetch(FetchParams(query=query, country=country, per_page=per_page))
                )))

    if "greenhouse" in enabled:
        registry = load_registry()
        for token in registry.greenhouse:
            tasks.append((f"greenhouse:{token}", asyncio.create_task(greenhouse.fetch_board(token))))

    # Free, clean-200 global feeds (no auth, no query/country needed — they are
    # whole-feed pulls of remote, English-language roles).
    for name, module in (("remoteok", remoteok), ("remotive", remotive), ("jobicy", jobicy)):
        if name in enabled:
            tasks.append((name, asyncio.create_task(module.fetch())))

    # FREE direct-ATS connectors — public, unauthenticated JSON APIs that return
    # full job descriptions + canonical career-page apply links (the no-cost
    # equivalent of a paid career-site feed). Company tokens come from the
    # existing H-1B sponsor board registry.
    from app.etl.api_sources.connectors import lever, ashby, smartrecruiters
    from app.services.h1b_sponsor_boards import by_ats
    for ats_name, ats_module in (("lever", lever), ("ashby", ashby), ("smartrecruiters", smartrecruiters)):
        if ats_name in enabled:
            for entry in by_ats(ats_name):
                tok = str(entry.get("token") or "").strip()
                if tok and entry.get("active", True):
                    tasks.append((f"{ats_name}:{tok}", asyncio.create_task(ats_module.fetch_board(tok))))

    # Direct ATS / career-site feed via Apify (full JD, real apply links, no
    # aggregator duplicates). Needs APIFY_TOKEN; no-op otherwise.
    if "career_site_feed" in enabled:
        try:
            career_site_feed_limit = max(1, int(os.getenv("CAREER_SITE_FEED_LIMIT", "1200")))
        except ValueError:
            career_site_feed_limit = 1200
        tasks.append(("career_site_feed", asyncio.create_task(
            career_site_feed.fetch(queries, limit=career_site_feed_limit)
        )))

    async def _labeled(label: str, task: asyncio.Task[list[NormalizedJob]]) -> tuple[str, list[NormalizedJob], Exception | None]:
        try:
            return label, await task, None
        except Exception as exc:
            return label, [], exc

    for completed in asyncio.as_completed([_labeled(label, task) for label, task in tasks]):
        label, rows, exc = await completed
        if exc:
            logger.warning("api_source failed source=%s error=%s", label, exc)
            continue
        fetched_count = len(rows)
        rows = _filter_requested_countries(rows, countries)
        logger.info(
            "api_source fetched source=%s count=%s country_eligible=%s",
            label,
            fetched_count,
            len(rows),
        )
        if rows and on_batch:
            await on_batch(label, rows)
        jobs.extend(rows)
    return _dedupe(jobs)


async def run_api_connectors_to_postgres(
    *,
    queries: list[str],
    countries: list[str] | None = None,
    sources: str = "adzuna~greenhouse",
    sync_master: bool = True,
) -> int:
    client = PostgresClient()
    loaded_total = 0
    loaded_batches = 0
    try:
        rebuild_every = max(0, int(os.getenv("API_CONNECTOR_MASTER_REBUILD_EVERY", "10")))
    except ValueError:
        rebuild_every = 10

    async def persist_batch(label: str, rows: list[NormalizedJob]) -> None:
        nonlocal loaded_total, loaded_batches
        normalized = [_to_existing_normalized(job) for job in rows]
        with client.session() as db:
            loaded = load_normalized_jobs(db, normalized)
            loaded_total += loaded
            loaded_batches += 1
            if sync_master and rebuild_every and loaded_batches % rebuild_every == 0:
                rebuild_master_jobs(db=db)
            db.commit()
        logger.info("api_source persisted source=%s loaded=%s total=%s", label, loaded, loaded_total)

    await fetch_all(queries=queries, countries=countries, sources=sources, on_batch=persist_batch)
    if sync_master and loaded_total:
        with client.session() as db:
            rebuild_master_jobs(db=db)
            db.commit()
    return loaded_total


async def run_api_connectors_to_firestore(
    *,
    queries: list[str],
    countries: list[str] | None = None,
    sources: str = "adzuna~greenhouse",
) -> dict[str, int]:
    jobs = await fetch_all(queries=queries, countries=countries, sources=sources)
    return upsert_firestore_jobs(jobs)


def _dedupe(jobs: Iterable[NormalizedJob]) -> list[NormalizedJob]:
    out: list[NormalizedJob] = []
    seen: set[str] = set()
    for job in jobs:
        if job.job_id in seen:
            continue
        seen.add(job.job_id)
        out.append(job)
    return out


def _to_existing_normalized(job: NormalizedJob) -> dict:
    posted = None
    if job.posted_date:
        try:
            posted = datetime.fromisoformat(job.posted_date.replace("Z", "+00:00"))
        except ValueError:
            posted = None
    return {
        "id": job.job_id,
        "company_name": job.company,
        "title": job.title,
        "normalized_title": " ".join(job.title.lower().split()),
        "location": job.location,
        "country": job.country or infer_country(job.location),
        "category": "Other",
        "source_name": job.source,
        "source_job_id": job.source_job_id,
        "source_url": job.url,
        "description": job.description,
        "employment_type": "",
        "remote_type": "remote" if job.remote else "",
        "salary_min": job.salary_min,
        "salary_max": job.salary_max,
        "currency": "USD",
        "visa_opt": False,
        "visa_stem_opt": False,
        "visa_h1b": False,
        "h1b_verified": job.sponsor_signal == "confirmed",
        "visa_score": 50 if job.sponsor_signal == "confirmed" else 25 if job.sponsor_signal == "likely" else 0,
        "content_hash": generate_content_hash(job.title, job.company, job.location),
        "status": "active",
        "posted_at": posted,
        "extra_metadata": {
            "api_source_schema": True,
            "raw_tags": job.raw_tags,
            "sponsor_signal": job.sponsor_signal,
            "ingested_at": job.ingested_at,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run official API/ATS job connectors.")
    parser.add_argument("--sink", choices=["postgres", "firestore"], default="postgres")
    parser.add_argument("--sources", default="adzuna~greenhouse")
    parser.add_argument("--queries", default="")
    parser.add_argument("--countries", default="")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    queries = [q.strip() for q in args.queries.replace("~", ",").split(",") if q.strip()] or all_role_names()
    countries = [c.strip() for c in args.countries.replace("~", ",").split(",") if c.strip()] or None
    if args.sink == "firestore":
        result = asyncio.run(run_api_connectors_to_firestore(queries=queries, countries=countries, sources=args.sources))
        logger.info("api_sources firestore result=%s", result)
    else:
        loaded = asyncio.run(run_api_connectors_to_postgres(queries=queries, countries=countries, sources=args.sources))
        logger.info("api_sources postgres loaded=%s", loaded)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

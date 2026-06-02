"""Production-sized 8-hour job scraper entrypoint for the existing Cloud Run Job.

The Cloud Run job intentionally keeps the historical name
`placeup-job-scraper-6h`; only its schedule/behavior changed to 8 hours.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os

from sqlalchemy import text

from app.db.postgres import PostgresClient
from app.etl.jobs_scraper import run
from app.etl.api_sources.runner import run_api_connectors_to_postgres
from app.config import settings
from app.job_taxonomy import all_role_names, all_taxonomy_scrape_search_terms
from app.services.global_visa_rules import COUNTRY_RULES, TARGET_COUNTRIES

logger = logging.getLogger(__name__)

# Public/API pass must cover every taxonomy role, not just USAJobs. Keep this
# env-tunable because RapidAPI/Dice quotas are operational limits, but the
# production default should collect from all currently wired public sources.
FREE_OPEN_PUBLIC_SOURCES = os.getenv("SCRAPER_PUBLIC_SOURCES", "rapidapi~usajobs~dice")
FREE_OPEN_BOARD_SOURCES = "h1b_sponsor~tier1_ats"
try:
    BATCH_SIZE = max(2, int(os.getenv("SCRAPER_ROLE_BATCH_SIZE", "8")))
except ValueError:
    BATCH_SIZE = 20
try:
    PUBLIC_BATCH_CONCURRENCY = max(0, int(os.getenv("SCRAPER_PUBLIC_BATCH_CONCURRENCY", "2")))
except ValueError:
    PUBLIC_BATCH_CONCURRENCY = 0
ADVISORY_LOCK_KEY = 6412226682826


def _encoded_terms(terms: list[str]) -> str:
    return "~".join(term.replace(" ", "_") for term in terms)


def _target_locations() -> str:
    locations: list[str] = []
    for country_code in sorted(TARGET_COUNTRIES):
        rule = COUNTRY_RULES.get(country_code)
        name = rule.name if rule else country_code
        locations.append(name.replace(" ", "_"))
    return "~".join(locations)


def _configured_public_sources() -> str:
    sources = [source for source in FREE_OPEN_PUBLIC_SOURCES.strip("~ ").split("~") if source]
    if "usajobs" in sources and (not settings.usajobs_api_key.strip() or not settings.usajobs_email.strip()):
        logger.warning("USAJobs public batches disabled because USAJOBS_API_KEY/USAJOBS_EMAIL are not configured.")
        sources = [source for source in sources if source != "usajobs"]
    return "~".join(sources)


def _base_args(**overrides) -> argparse.Namespace:
    values = {
        "locations": _target_locations(),
        "max_per_source": 60,
        "max_per_sponsor": 400,
        "h1b_sponsor_concurrency": 10,
        "jobspy_hours_old": 8,
        "jobspy_page_size": 50,
        "jobspy_max_pages": 25,
        "tiers": "T1~T2",
        "schedule_type": "8h",
        "dry_run": False,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


async def _run_batched() -> int:
    roles = all_role_names()
    terms = all_taxonomy_scrape_search_terms()
    batches = [terms[i:i + BATCH_SIZE] for i in range(0, len(terms), BATCH_SIZE)]
    public_concurrency = PUBLIC_BATCH_CONCURRENCY or len(batches) or 1
    semaphore = asyncio.Semaphore(public_concurrency)
    failures = 0

    logger.info("8h scraper running direct H1B/ATS board pass")
    api_connector_count = await run_api_connectors_to_postgres(
        queries=terms,
        countries=list(sorted(TARGET_COUNTRIES)),
        sources=os.getenv("API_CONNECTOR_SOURCES", "adzuna~greenhouse"),
    )
    logger.info("8h official API/ATS connectors loaded %s jobs", api_connector_count)
    board_code = await run(_base_args(
        queries=_encoded_terms(roles),
        sources=FREE_OPEN_BOARD_SOURCES,
        schedule_type="8h-boards",
    ))
    if board_code:
        failures += 1
        logger.warning("8h scraper board pass failed with code %s", board_code)

    public_sources = _configured_public_sources()
    if not public_sources:
        logger.info("8h scraper public source pass disabled")
        return 1 if board_code else 0

    async def _run_public_batch(index: int, batch: list[str]) -> int:
        async with semaphore:
            logger.info(
                "8h scraper batch %s/%s publishing %s role terms",
                index,
                len(batches),
                len(batch),
            )
            code = await run(_base_args(
                queries=_encoded_terms(batch),
                sources=public_sources,
                schedule_type=f"8h-public-{index:02d}",
            ))
            if code:
                logger.warning("8h scraper public batch %s/%s failed with code %s", index, len(batches), code)
            return code

    logger.info(
        "8h scraper launching %s public batches for %s current roles / %s search terms with concurrency %s",
        len(batches),
        len(roles),
        len(terms),
        public_concurrency,
    )
    public_results = await asyncio.gather(*[
        _run_public_batch(index, batch)
        for index, batch in enumerate(batches, start=1)
    ])
    failures += sum(1 for code in public_results if code)

    return 1 if failures == len(batches) + 1 else 0


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    client = PostgresClient()
    with client.session() as db:
        locked = bool(db.execute(
            text("SELECT pg_try_advisory_lock(:lock_key)"),
            {"lock_key": ADVISORY_LOCK_KEY},
        ).scalar())
        if not locked:
            logger.warning("Another 8h scraper execution is already running; skipping this run.")
            return 0
        try:
            return asyncio.run(_run_batched())
        finally:
            db.execute(
                text("SELECT pg_advisory_unlock(:lock_key)"),
                {"lock_key": ADVISORY_LOCK_KEY},
            )


if __name__ == "__main__":
    raise SystemExit(main())

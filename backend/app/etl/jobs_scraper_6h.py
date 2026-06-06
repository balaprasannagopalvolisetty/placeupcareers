"""Production-sized 6-hour job scraper entrypoint for the existing Cloud Run Job.

The Cloud Run job intentionally keeps the existing production name
`placeup-job-scraper-6h`; do not create a duplicate 8-hour scraper.
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
from app.etl.purge_jobs_except_today import purge_except_day
from app.config import settings
from app.job_taxonomy import all_balanced_taxonomy_scrape_search_terms, all_linkedin_style_role_names, all_role_names
from app.services.global_visa_rules import COUNTRY_RULES, TARGET_COUNTRIES

logger = logging.getLogger(__name__)

# Public/API pass must cover every taxonomy role, not just USAJobs. Keep this
# env-tunable because RapidAPI/Dice quotas are operational limits, but the
# production default should collect from all currently wired public sources.
FREE_OPEN_PUBLIC_SOURCES = os.getenv(
    "SCRAPER_PUBLIC_SOURCES",
    "linkedin~indeed~glassdoor~ziprecruiter~google~rapidapi~usajobs~dice",
)
FREE_OPEN_BOARD_SOURCES = (
    "h1b_sponsor~tier1_ats~remoteok~remotive~arbeitnow~jobicy~weworkremotely~"
    "jobtech~eures~uk_findajob~nhs_jobs~jobbank_ca~ba_jobsuche~france_travail~"
    "mycareersfuture~tyomarkkinatori~nav_arbeidsplassen~monster~jooble~"
    "scrapling_discovery"
)
try:
    BATCH_SIZE = max(2, int(os.getenv("SCRAPER_ROLE_BATCH_SIZE", "8")))
except ValueError:
    BATCH_SIZE = 20
try:
    CANONICAL_ROLE_BATCH_SIZE = max(2, int(os.getenv("SCRAPER_CANONICAL_ROLE_BATCH_SIZE", "5")))
except ValueError:
    CANONICAL_ROLE_BATCH_SIZE = 5
try:
    PUBLIC_BATCH_CONCURRENCY = max(0, int(os.getenv("SCRAPER_PUBLIC_BATCH_CONCURRENCY", "2")))
except ValueError:
    PUBLIC_BATCH_CONCURRENCY = 0
PURGE_EXCEPT_TODAY = os.getenv("SCRAPER_PURGE_EXCEPT_TODAY", "true").strip().lower() not in {"0", "false", "no", "off"}
PURGE_TIMEZONE = os.getenv("SCRAPER_PURGE_TIMEZONE", "America/Chicago").strip() or "America/Chicago"
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
        "schedule_type": "6h",
        "dry_run": False,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


async def _run_batched() -> int:
    roles = all_role_names()
    linkedin_style_roles = all_linkedin_style_role_names()
    terms = all_balanced_taxonomy_scrape_search_terms()
    countries = list(sorted(TARGET_COUNTRIES))
    country_locations = _target_locations()
    role_country_pairs = len(roles) * len(countries)
    batches = [terms[i:i + BATCH_SIZE] for i in range(0, len(terms), BATCH_SIZE)]
    canonical_role_batches = [
        linkedin_style_roles[i:i + CANONICAL_ROLE_BATCH_SIZE]
        for i in range(0, len(linkedin_style_roles), CANONICAL_ROLE_BATCH_SIZE)
    ]
    public_concurrency = PUBLIC_BATCH_CONCURRENCY or len(batches) or 1
    semaphore = asyncio.Semaphore(public_concurrency)
    failures = 0

    logger.info(
        "6h role-country coverage plan: %s canonical roles x %s countries = %s role-country pairs; countries=%s",
        len(roles),
        len(countries),
        role_country_pairs,
        ",".join(countries),
    )

    logger.info("6h scraper running direct H1B/ATS board pass")
    try:
        api_connector_count = await run_api_connectors_to_postgres(
            queries=terms,
            countries=countries,
            sources=os.getenv("API_CONNECTOR_SOURCES", "adzuna~greenhouse~remoteok~remotive~jobicy"),
        )
        logger.info("6h official API/ATS connectors loaded %s jobs", api_connector_count)
    except Exception as exc:
        failures += 1
        logger.warning("6h official API/ATS connector pass failed; continuing with board/public sources: %s", exc)
    board_code = await run(_base_args(
        queries=_encoded_terms(linkedin_style_roles),
        locations=country_locations,
        max_per_source=200,
        sources=FREE_OPEN_BOARD_SOURCES,
        schedule_type="6h-boards",
    ))
    if board_code:
        failures += 1
        logger.warning("6h scraper board pass failed with code %s", board_code)

    public_sources = _configured_public_sources()
    if not public_sources:
        logger.info("6h scraper public source pass disabled")
        return 1 if failures >= 2 else 0

    async def _run_public_batch(index: int, total: int, batch: list[str], *, phase: str, batch_size: int) -> int:
        async with semaphore:
            logger.info(
                "6h scraper %s batch %s/%s publishing %s terms across %s countries (%s role-country attempts)",
                phase,
                index,
                total,
                len(batch),
                len(countries),
                len(batch) * len(countries),
            )
            code = await run(_base_args(
                queries=_encoded_terms(batch),
                locations=country_locations,
                sources=public_sources,
                schedule_type=f"6h-public-{phase}-{index:02d}",
                max_per_source=batch_size,
            ))
            if code:
                logger.warning("6h scraper public %s batch %s/%s failed with code %s", phase, index, total, code)
            return code

    logger.info(
        "6h scraper launching %s LinkedIn-style canonical public batches and %s synonym/coverage batches for %s current roles / %s canonical search names / %s search terms with concurrency %s",
        len(canonical_role_batches),
        len(batches),
        len(roles),
        len(linkedin_style_roles),
        len(terms),
        public_concurrency,
    )
    canonical_results = await asyncio.gather(*[
        _run_public_batch(index, len(canonical_role_batches), batch, phase="canonical", batch_size=90)
        for index, batch in enumerate(canonical_role_batches, start=1)
    ])
    synonym_results = await asyncio.gather(*[
        _run_public_batch(index, len(batches), batch, phase="synonyms", batch_size=60)
        for index, batch in enumerate(batches, start=1)
    ])
    public_results = [*canonical_results, *synonym_results]
    failures += sum(1 for code in public_results if code)

    if PURGE_EXCEPT_TODAY:
        try:
            counts = purge_except_day(day=None, tz_name=PURGE_TIMEZONE, dry_run=False)
            logger.info("6h scraper post-run today-only purge: %s", counts)
        except Exception as exc:
            failures += 1
            logger.warning("6h scraper post-run today-only purge failed: %s", exc)

    total_failure_slots = 2 + len(canonical_role_batches) + len(batches)
    return 1 if failures >= total_failure_slots else 0


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
            logger.warning("Another 6h scraper execution is already running; skipping this run.")
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

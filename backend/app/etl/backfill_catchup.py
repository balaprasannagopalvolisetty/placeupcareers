"""One-shot catch-up backfill to restore job inventory.

Use this after positions were lost (e.g. a destructive today-only purge) or
whenever the board looks thin. It runs the same multi-source pipeline as the
6-hour scraper but with three differences:

* a WIDE time window (``--hours-old``, default 720h = 30 days) so older but
  still-active postings are pulled back in, not just the last few hours;
* the coverage-floor role terms across EVERY target country, so thin
  role/country cells get refilled;
* it NEVER purges — it only inserts/updates, then rebuilds master_jobs.

Run as a Cloud Run Job or locally:

    python -m app.etl.backfill_catchup
    python -m app.etl.backfill_catchup --hours-old 1440        # 60 days
    python -m app.etl.backfill_catchup --max-per-source 200
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import time

from app.db.postgres import PostgresClient
from app.etl.jobs_scraper import run
from app.etl.api_sources.runner import run_api_connectors_to_postgres
from app.etl.master_jobs import rebuild_master_jobs
from app.etl.jobs_scraper_6h import (
    FREE_OPEN_BOARD_SOURCES,
    _base_args,
    _configured_public_sources,
    _encoded_terms,
    _merge_sources,
    _target_locations,
)
from app.job_taxonomy import (
    all_balanced_taxonomy_scrape_search_terms,
    all_linkedin_style_role_names,
    all_role_backfill_search_terms,
    all_role_names,
)
from app.services.global_visa_rules import TARGET_COUNTRIES

logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="One-shot catch-up backfill (no purge).")
    parser.add_argument("--hours-old", type=int, default=720,
                        help="JobSpy max posting age in hours (default 720 = 30 days).")
    parser.add_argument("--max-per-source", type=int, default=140)
    parser.add_argument("--max-per-sponsor", type=int, default=600)
    return parser.parse_args()


async def _run(args: argparse.Namespace) -> int:
    started = time.monotonic()
    countries = list(sorted(TARGET_COUNTRIES))
    country_locations = _target_locations()
    roles = all_role_names()
    linkedin_style_roles = all_linkedin_style_role_names()
    terms = all_balanced_taxonomy_scrape_search_terms()
    backfill_terms = all_role_backfill_search_terms()
    failures = 0

    logger.info(
        "Catch-up backfill: %s roles x %s countries; hours_old=%s; NO purge",
        len(roles), len(countries), args.hours_old,
    )

    # 1) Official API / ATS connectors across all countries.
    try:
        loaded = await run_api_connectors_to_postgres(
            queries=terms,
            countries=countries,
            sources="adzuna~greenhouse~remoteok~remotive~jobicy",
        )
        logger.info("Catch-up API/ATS connectors loaded %s jobs", loaded)
    except Exception as exc:
        failures += 1
        logger.warning("Catch-up API/ATS connector pass failed: %s", exc)

    # 2) Direct H1B / ATS / public board pass across all countries.
    board_code = await run(_base_args(
        queries=_encoded_terms(linkedin_style_roles),
        locations=country_locations,
        max_per_source=200,
        max_per_sponsor=args.max_per_sponsor,
        sources=FREE_OPEN_BOARD_SOURCES,
        jobspy_hours_old=args.hours_old,
        jobspy_max_pages=50,
        schedule_type="catchup-boards",
        skip_master_sync=True,
    ))
    if board_code:
        failures += 1

    # 3) Wide public + coverage-floor pass to refill thin role/country cells.
    public_sources = _configured_public_sources()
    coverage_sources = _merge_sources(
        public_sources,
        "monster~jooble",
        "remoteok~remotive~arbeitnow~jobicy~weworkremotely",
        "jobtech~eures~uk_findajob~nhs_jobs~jobbank_ca~ba_jobsuche~france_travail~mycareersfuture~tyomarkkinatori~nav_arbeidsplassen",
        "h1b_sponsor~tier1_ats~scrapling_discovery",
    )
    floor_code = await run(_base_args(
        queries=_encoded_terms(backfill_terms),
        locations=country_locations,
        sources=coverage_sources,
        max_per_source=args.max_per_source,
        max_per_sponsor=args.max_per_sponsor,
        jobspy_hours_old=args.hours_old,
        jobspy_page_size=50,
        jobspy_max_pages=50,
        schedule_type="catchup-coverage-floor",
        skip_master_sync=True,
    ))
    if floor_code:
        failures += 1

    # 4) Rebuild master_jobs once at the end (no purge anywhere).
    try:
        client = PostgresClient()
        with client.session() as db:
            rebuilt = rebuild_master_jobs(db=db)
            db.commit()
        logger.info("Catch-up master_jobs rebuild complete: %s", rebuilt)
    except Exception as exc:
        failures += 1
        logger.warning("Catch-up master_jobs rebuild failed: %s", exc)

    logger.info("Catch-up backfill finished in %.0fs with %s failures", time.monotonic() - started, failures)
    return 1 if failures >= 3 else 0


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    return asyncio.run(_run(parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())

"""Focused Cloud Run Job that backfills every Jobs-page taxonomy role."""

from __future__ import annotations

import argparse
import asyncio
import logging

from app.etl.jobs_scraper import run
from app.job_taxonomy import all_role_backfill_search_terms

logger = logging.getLogger("placeup.etl.taxonomy_role_backfill")


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    terms = all_role_backfill_search_terms()
    logger.info("Starting taxonomy role backfill with %s role-focused search terms", len(terms))
    args = argparse.Namespace(
        queries="~".join(term.replace(" ", "_") for term in terms),
        locations="United_States~Canada",
        sources="rapidapi~usajobs~dice",
        max_per_source=25,
        max_per_sponsor=25,
        h1b_sponsor_concurrency=4,
        jobspy_hours_old=720,
        jobspy_page_size=25,
        jobspy_max_pages=3,
        tiers="T1~T2",
        schedule_type="taxonomy-role-backfill",
        dry_run=False,
    )
    return asyncio.run(run(args))


if __name__ == "__main__":
    raise SystemExit(main())

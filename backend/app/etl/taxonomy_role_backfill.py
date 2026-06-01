"""Focused Cloud Run Job that backfills every Jobs-page taxonomy role."""

from __future__ import annotations

import argparse
import asyncio
import logging

from app.etl.jobs_scraper import run
from app.job_taxonomy import all_role_backfill_search_terms
from app.services.global_visa_rules import COUNTRY_RULES, TARGET_COUNTRIES

logger = logging.getLogger("placeup.etl.taxonomy_role_backfill")


def _target_locations() -> str:
    locations: list[str] = []
    for country_code in sorted(TARGET_COUNTRIES):
        rule = COUNTRY_RULES.get(country_code)
        locations.append((rule.name if rule else country_code).replace(" ", "_"))
    return "~".join(locations)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    terms = all_role_backfill_search_terms()
    logger.info("Starting taxonomy role backfill with %s role-focused search terms", len(terms))
    args = argparse.Namespace(
        queries="~".join(term.replace(" ", "_") for term in terms),
        locations=_target_locations(),
        sources="rapidapi~usajobs~dice",
        max_per_source=60,
        max_per_sponsor=25,
        h1b_sponsor_concurrency=4,
        jobspy_hours_old=8,
        jobspy_page_size=50,
        jobspy_max_pages=25,
        tiers="T1~T2",
        schedule_type="taxonomy-role-backfill",
        dry_run=False,
    )
    return asyncio.run(run(args))


if __name__ == "__main__":
    raise SystemExit(main())

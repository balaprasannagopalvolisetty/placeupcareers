"""Cloud Run Job entrypoint for 12-hour external API ingests."""

from __future__ import annotations

import argparse
import asyncio
import logging

from app.etl.jobs_scraper import run as run_job_scraper
from app.job_taxonomy import all_taxonomy_scrape_search_terms
from app.services.global_visa_rules import COUNTRY_RULES, TARGET_COUNTRIES

logger = logging.getLogger("placeup.etl.external_api_ingest")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run 12-hour external API ingestion.")
    parser.add_argument("--provider", default="all", help="Provider key to ingest, or all.")
    parser.add_argument("--schedule-type", default="12h")
    return parser.parse_args()


def _provider_sources(provider: str) -> str:
    provider = (provider or "all").lower()
    if provider in {"all", "external"}:
        return "rapidapi~usajobs~dice"
    if provider in {"jsearch", "rapidapi", "linkedin"}:
        return "rapidapi"
    if provider in {"usajobs", "usa"}:
        return "usajobs"
    if provider == "dice":
        return "dice"
    return "rapidapi~usajobs~dice"


def _target_locations() -> str:
    names: list[str] = []
    for country_code in sorted(TARGET_COUNTRIES):
        rule = COUNTRY_RULES.get(country_code)
        names.append((rule.name if rule else country_code).replace(" ", "_"))
    return "~".join(names)


async def run(args: argparse.Namespace) -> int:
    scraper_args = argparse.Namespace(
        queries="~".join(term.replace(" ", "_") for term in all_taxonomy_scrape_search_terms()),
        locations=_target_locations(),
        sources=_provider_sources(args.provider),
        max_per_source=60,
        max_per_sponsor=10,
        h1b_sponsor_concurrency=1,
        jobspy_hours_old=8,
        jobspy_page_size=50,
        jobspy_max_pages=25,
        tiers="",
        schedule_type=args.schedule_type,
        dry_run=False,
    )
    return await run_job_scraper(scraper_args)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    args = parse_args()
    return asyncio.run(run(args))


if __name__ == "__main__":
    raise SystemExit(main())

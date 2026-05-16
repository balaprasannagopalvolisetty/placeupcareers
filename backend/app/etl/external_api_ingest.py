"""Cloud Run Job entrypoint for 12-hour external API ingests."""

from __future__ import annotations

import argparse
import asyncio
import logging

from app.etl.jobs_scraper import run as run_job_scraper
from app.job_taxonomy import all_early_career_search_terms

logger = logging.getLogger("placeup.etl.external_api_ingest")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run 12-hour external API ingestion.")
    parser.add_argument("--provider", default="all", help="Provider key to ingest, or all.")
    parser.add_argument("--schedule-type", default="12h")
    return parser.parse_args()


def _provider_sources(provider: str) -> str:
    provider = (provider or "all").lower()
    if provider in {"all", "external"}:
        return "rapidapi"
    if provider in {"jsearch", "rapidapi", "linkedin"}:
        return "rapidapi"
    if provider in {"usajobs", "usa"}:
        return "usajobs"
    if provider == "dice":
        return "dice"
    return "rapidapi~usajobs~dice"


async def run(args: argparse.Namespace) -> int:
    scraper_args = argparse.Namespace(
        queries="~".join(term.replace(" ", "_") for term in all_early_career_search_terms()),
        locations="North_America",
        sources=_provider_sources(args.provider),
        max_per_source=25,
        max_per_sponsor=10,
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

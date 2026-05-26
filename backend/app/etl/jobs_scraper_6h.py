"""Production-sized 6-hour job scraper entrypoint for Cloud Run Jobs."""

from __future__ import annotations

import argparse
import asyncio
import logging

from app.etl.jobs_scraper import run
from app.job_taxonomy import all_role_backfill_search_terms

logger = logging.getLogger(__name__)

PUBLIC_SOURCES = (
    "linkedin~indeed~ziprecruiter~glassdoor~google~"
    "usajobs~dice~monster~jooble~scrapling_discovery"
)
BOARD_SOURCES = "h1b_sponsor~tier1_ats~scrapegraph_discovery"
BATCH_SIZE = 12


def _encoded_terms(terms: list[str]) -> str:
    return "~".join(term.replace(" ", "_") for term in terms)


def _base_args(**overrides) -> argparse.Namespace:
    values = {
        "locations": "United_States~Canada",
        "max_per_source": 60,
        "max_per_sponsor": 400,
        "h1b_sponsor_concurrency": 10,
        "jobspy_hours_old": 720,
        "jobspy_page_size": 50,
        "jobspy_max_pages": 25,
        "tiers": "T1~T2",
        "schedule_type": "6h",
        "dry_run": False,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


async def _run_batched() -> int:
    terms = all_role_backfill_search_terms()
    failures = 0
    batches = [terms[i:i + BATCH_SIZE] for i in range(0, len(terms), BATCH_SIZE)]

    for index, batch in enumerate(batches, start=1):
        logger.info("6h scraper batch %s/%s publishing %s role terms", index, len(batches), len(batch))
        code = await run(_base_args(
            queries=_encoded_terms(batch),
            sources=PUBLIC_SOURCES,
            schedule_type=f"6h-public-{index:02d}",
        ))
        if code:
            failures += 1
            logger.warning("6h scraper public batch %s/%s failed with code %s", index, len(batches), code)

    logger.info("6h scraper running direct H1B/ATS/discovery board pass")
    board_code = await run(_base_args(
        queries=_encoded_terms(terms[:BATCH_SIZE]),
        sources=BOARD_SOURCES,
        schedule_type="6h-boards",
    ))
    if board_code:
        failures += 1
        logger.warning("6h scraper board pass failed with code %s", board_code)

    return 1 if failures == len(batches) + 1 else 0


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    return asyncio.run(_run_batched())


if __name__ == "__main__":
    raise SystemExit(main())

"""
Unified entry point for every clean-200 global source.

Merges the remote/English boards (free_boards) with the official
government-portal connectors (official_portals) into one registry, and
runs them all behind the same circuit breaker + 8h-recency + dedup
pipeline. This is the single function the scrape scheduler should call.

CLI:
    python -m app.etl.sources.global_sources --hours 8 --english-only
"""
from __future__ import annotations

import argparse
import asyncio
import logging
from typing import Optional

from app.models.job import JobPost
from app.etl.sources.free_boards import (  # remote / English-language boards
    scrape_remoteok, scrape_remotive, scrape_arbeitnow, scrape_jobicy, scrape_weworkremotely,
)
from app.etl.sources.official_portals import OFFICIAL_PORTAL_SOURCES
from app.etl.sources.free_boards_pipeline import run_free_boards

logger = logging.getLogger(__name__)

# Every clean-200 source PlaceUp can ingest, in one place.
FREE_BOARD_SOURCES = {
    "remoteok": scrape_remoteok,
    "remotive": scrape_remotive,
    "arbeitnow": scrape_arbeitnow,
    "jobicy": scrape_jobicy,
    "weworkremotely": scrape_weworkremotely,
}

ALL_CLEAN_SOURCES = {**FREE_BOARD_SOURCES, **OFFICIAL_PORTAL_SOURCES}


async def run_all_clean_sources(
    *,
    hours: Optional[int] = 8,
    max_jobs_per_source: int = 500,
    only: Optional[set[str]] = None,
    english_only: bool = True,
    queries: Optional[list[str]] = None,
) -> tuple[list[JobPost], dict[str, str]]:
    """Run every registered clean-200 source (boards + official portals).

    `english_only` defaults True to honour requirement B4 (only
    English-friendly roles from non-English-speaking countries).
    """
    return await run_free_boards(
        hours=hours,
        max_jobs_per_source=max_jobs_per_source,
        only=only,
        registry=ALL_CLEAN_SOURCES,
        english_only=english_only,
        queries=queries,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Run all clean-200 global job sources")
    parser.add_argument("--hours", type=int, default=8, help="Keep jobs posted in last N hours (0 = no limit)")
    parser.add_argument("--max", type=int, default=500, help="Max jobs per source")
    parser.add_argument("--only", type=str, default="", help="Comma-separated subset of source names")
    parser.add_argument("--queries", type=str, default="", help="Comma-separated query terms for queryable sources")
    parser.add_argument("--english-only", action="store_true", help="Drop non-English postings (B4)")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    only = {s.strip() for s in args.only.split(",") if s.strip()} or None
    queries = [s.strip() for s in args.queries.split(",") if s.strip()] or None
    jobs, status = asyncio.run(
        run_all_clean_sources(
            hours=args.hours, max_jobs_per_source=args.max,
            only=only, english_only=args.english_only, queries=queries,
        )
    )
    print(f"\n{len(jobs)} unique jobs (last {args.hours}h, english_only={args.english_only})")
    for src, st in sorted(status.items()):
        print(f"  {src:16s} {st}")
    by_country: dict[str, int] = {}
    for j in jobs:
        cc = j.extra_metadata.get("visa_country") or "remote/unspecified"
        by_country[cc] = by_country.get(cc, 0) + 1
    print("by country:", dict(sorted(by_country.items(), key=lambda kv: -kv[1])))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""
PlaceUp — Full Scrape CLI

Runs the complete scrape pipeline once and writes results to data/exports/
as both CSV and XLSX. Designed to be invoked manually or from a cron job.

Usage:
    python scripts/full_scrape.py
    python scripts/full_scrape.py --tiers T1            # only top-100 sponsors
    python scripts/full_scrape.py --no-jobspy           # skip JobSpy portals
    python scripts/full_scrape.py --queries "data scientist,ml engineer"
    python scripts/full_scrape.py --max-per-source 50   # smaller test run

The script honors the same .env file the FastAPI app reads.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import time
from pathlib import Path

# Make the project root importable when running this script directly.
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.models.job import JobSource, ScrapeRequest  # noqa: E402
from app.services.job_exporter import export_jobs  # noqa: E402
from app.services.job_scraper import run_scrape_cycle  # noqa: E402
from app.scrape_constants import DEFAULT_SCRAPE_SEARCH_TERMS  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("placeup.full_scrape")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="PlaceUp full scrape CLI")
    parser.add_argument(
        "--queries",
        default=None,
        help="Comma-separated search terms (default = backend defaults)",
    )
    parser.add_argument(
        "--locations",
        default="United States",
        help="Comma-separated locations (default = United States)",
    )
    parser.add_argument(
        "--tiers",
        default="T1,T2",
        help="H1B sponsor tiers: T1, T2, T3 (comma-separated)",
    )
    parser.add_argument(
        "--max-per-source",
        type=int,
        default=120,
        help="Max jobs per portal × query × location",
    )
    parser.add_argument(
        "--max-per-sponsor",
        type=int,
        default=500,
        help="Max jobs per H1B sponsor ATS board",
    )
    parser.add_argument(
        "--no-jobspy",
        action="store_true",
        help="Skip JobSpy portals (LinkedIn / Indeed / Glassdoor / ZipRecruiter / Google)",
    )
    parser.add_argument(
        "--no-dice",
        action="store_true",
        help="Skip Dice",
    )
    parser.add_argument(
        "--no-h1b",
        action="store_true",
        help="Skip H1B sponsor pipeline",
    )
    parser.add_argument(
        "--export-dir",
        default="data/exports",
        help="Where to write CSV/XLSX exports",
    )
    return parser.parse_args()


def build_request(args: argparse.Namespace) -> ScrapeRequest:
    sources: list[JobSource] = []
    if not args.no_jobspy:
        sources.extend([
            JobSource.LINKEDIN,
            JobSource.INDEED,
            JobSource.GLASSDOOR,
            JobSource.ZIPRECRUITER,
            JobSource.GOOGLE,
        ])
    sources.append(JobSource.USAJOBS)
    if not args.no_dice:
        sources.append(JobSource.DICE)
    if not args.no_h1b:
        sources.append(JobSource.H1B_SPONSOR)

    queries = (
        [q.strip() for q in args.queries.split(",") if q.strip()]
        if args.queries
        else list(DEFAULT_SCRAPE_SEARCH_TERMS)
    )
    locations = [l.strip() for l in args.locations.split(",") if l.strip()]
    tiers = [t.strip() for t in args.tiers.split(",") if t.strip()]

    return ScrapeRequest(
        search_terms=queries,
        locations=locations or ["United States"],
        sources=sources,
        results_per_source=args.max_per_source,
        h1b_sponsor_tiers=tiers,
        h1b_sponsor_max_jobs=args.max_per_sponsor,
    )


async def main() -> int:
    args = parse_args()
    request = build_request(args)

    logger.info("─" * 60)
    logger.info("PlaceUp full scrape starting")
    logger.info("  queries:    %s", len(request.search_terms))
    logger.info("  locations:  %s", request.locations)
    logger.info("  sources:    %s", [s.value for s in request.sources])
    logger.info("  H1B tiers:  %s", request.h1b_sponsor_tiers)
    logger.info("─" * 60)

    started = time.time()
    result, jobs = await run_scrape_cycle(request=request)
    duration = time.time() - started

    logger.info("─" * 60)
    logger.info(
        "Scrape complete in %.1fs — %s scraped, %s unique, %s dupes skipped",
        duration, result.total_scraped, result.new_jobs, result.duplicates_skipped,
    )

    if not jobs:
        logger.warning("No jobs collected — nothing to export.")
        return 1

    job_dicts = [job.model_dump(mode="json") for job in jobs]
    artifacts = export_jobs(job_dicts, export_dir=args.export_dir)
    logger.info("Exported artifacts:")
    for kind, path in artifacts.items():
        logger.info("  %-5s → %s", kind, path)

    # Light per-source breakdown
    logger.info("Per-source breakdown:")
    for source, stats in sorted(result.source_breakdown.items()):
        logger.info(
            "  %-20s attempts=%-4s scraped=%-5s unique=%-5s errors=%s",
            source, stats["attempts"], stats["scraped"], stats["unique"], stats["errors"],
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

"""
H1B Sponsor → Careers Pipeline

End-to-end pipeline that:
  1. Loads the curated H1B sponsor board catalog (h1b_sponsor_boards.py),
     optionally enriched with USCIS CSV data and the leaderboard scrapers.
  2. For each sponsor, dispatches to the right ATS scraper to pull ALL
     currently-open positions.
  3. Stamps each JobPost with H1B verification metadata (h1b_verified=True,
     visa_h1b=True, score boosted) since the source company is a known sponsor.
  4. Returns a deduplicated, normalized list of JobPost objects ready for
     the existing exporter / DB writer.

This is the bridge between the H1B data services and the job scraping
orchestrator. Run from a CLI script or wired into /api/jobs/scrape via the
H1B_SPONSOR option.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from app.models.job import JobPost, VisaBadges
from app.services.careers_ats import scrape_ats
from app.services.h1b_sponsor_boards import H1B_SPONSOR_BOARDS, filter_by_tier
from app.utils.deduplication import generate_content_hash

logger = logging.getLogger(__name__)


async def scrape_h1b_sponsor_boards(
    *,
    tiers: tuple[str, ...] = ("T1", "T2"),
    max_jobs_per_sponsor: int = 500,
    concurrency: int = 8,
    only_companies: Optional[set[str]] = None,
) -> list[JobPost]:
    """Scrape every configured H1B sponsor's ATS board in parallel.

    Args:
        tiers: H1B tiers to include ("T1" = top 100, "T2" = top 500).
        max_jobs_per_sponsor: Per-board cap to keep things reasonable.
        concurrency: Max parallel scrapes (be polite — these are public APIs).
        only_companies: If set, restrict to this allow-list of company names
            (case-insensitive match against the catalog "company" field).

    Returns:
        Deduplicated list of JobPost objects across all sponsors. Each post
        is stamped with visa.h1b_verified=True since the source is a
        known H1B sponsor.
    """
    sponsors = filter_by_tier(tiers)
    if only_companies:
        names = {c.lower() for c in only_companies}
        sponsors = [s for s in sponsors if s["company"].lower() in names]

    if not sponsors:
        logger.warning("H1B pipeline: no sponsors selected")
        return []

    logger.info("H1B pipeline: %s sponsors → %s ATS scrapes", len(sponsors), len(sponsors))

    semaphore = asyncio.Semaphore(concurrency)

    async def _scrape_one(entry: dict) -> tuple[dict, list[JobPost]]:
        async with semaphore:
            try:
                jobs = await scrape_ats(
                    ats_name=entry["ats"],
                    board_token=entry["token"],
                    max_jobs=max_jobs_per_sponsor,
                )
                return entry, jobs
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "H1B sponsor %s (%s/%s) failed: %s",
                    entry["company"], entry["ats"], entry["token"], exc,
                )
                return entry, []

    results = await asyncio.gather(*[_scrape_one(s) for s in sponsors])

    # Dedupe within this batch by content_hash
    seen_hashes: set[str] = set()
    unique: list[JobPost] = []

    for entry, jobs in results:
        for job in jobs:
            # Override company name with the canonical catalog name to
            # improve cross-source dedup (otherwise "Stripe Inc." vs "Stripe"
            # would create two records).
            if entry.get("company"):
                job.company = entry["company"]
                job.content_hash = generate_content_hash(job.title, job.company, job.location or "")

            # Stamp H1B verification — the source company is a known H1B sponsor
            existing_visa = job.visa or VisaBadges()
            job.visa = VisaBadges(
                visa_opt=existing_visa.visa_opt,
                visa_stem_opt=existing_visa.visa_stem_opt,
                visa_h1b=True,
                h1b_verified=True,
                visa_score=max(existing_visa.visa_score, 75),
            )

            if job.content_hash in seen_hashes:
                continue
            seen_hashes.add(job.content_hash)
            unique.append(job)

    logger.info(
        "H1B pipeline: %s unique jobs from %s sponsors (raw total %s)",
        len(unique), len(sponsors), sum(len(jobs) for _, jobs in results),
    )
    return unique


async def merge_with_external_jobs(
    h1b_jobs: list[JobPost],
    external_jobs: list[JobPost],
) -> list[JobPost]:
    """Merge H1B sponsor jobs with externally-scraped jobs, preferring the
    H1B-stamped record on dupes (so visa metadata is preserved).
    """
    by_hash: dict[str, JobPost] = {j.content_hash: j for j in h1b_jobs}
    for job in external_jobs:
        if job.content_hash in by_hash:
            # External duplicate of an H1B-known role — keep the H1B record.
            continue
        by_hash[job.content_hash] = job
    return list(by_hash.values())

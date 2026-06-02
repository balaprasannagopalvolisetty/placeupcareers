"""
Orchestrator for the clean-200 global job boards (free_boards.py).

Runs every registered connector behind a circuit breaker, applies the
"recent only" window (default 8h, per requirement B1), de-duplicates by
content hash (B7), and returns one clean list[JobPost]. A single bad
source is skipped, never fatal (B6).

CLI:  python -m app.etl.sources.free_boards_pipeline --hours 8
"""
from __future__ import annotations

import argparse
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx

from app.models.job import JobPost
from app.etl.sources.source_base import SourceHealth, guarded_source
from app.etl.sources import free_boards as fb

logger = logging.getLogger(__name__)

# name -> connector coroutine factory
FREE_BOARD_SOURCES = {
    "remoteok": fb.scrape_remoteok,
    "remotive": fb.scrape_remotive,
    "arbeitnow": fb.scrape_arbeitnow,
    "jobicy": fb.scrape_jobicy,
    "weworkremotely": fb.scrape_weworkremotely,
}


def _is_recent(job: JobPost, *, cutoff: Optional[datetime]) -> bool:
    """Keep jobs posted at/after cutoff. Jobs with no posted_at are kept
    (we can't prove they're stale; the dedup + later passes handle them)."""
    if cutoff is None or job.posted_at is None:
        return True
    posted = job.posted_at
    if posted.tzinfo is None:
        posted = posted.replace(tzinfo=timezone.utc)
    return posted >= cutoff


def dedupe(jobs: list[JobPost]) -> list[JobPost]:
    """Drop duplicates by content_hash (falls back to id)."""
    seen: set[str] = set()
    out: list[JobPost] = []
    for j in jobs:
        key = j.content_hash or j.id
        if key in seen:
            continue
        seen.add(key)
        out.append(j)
    return out


async def run_free_boards(
    *,
    hours: Optional[int] = 8,
    max_jobs_per_source: int = 500,
    only: Optional[set[str]] = None,
    health: Optional[SourceHealth] = None,
    registry: Optional[dict] = None,
    english_only: bool = False,
) -> tuple[list[JobPost], dict[str, str]]:
    """Run all (or a subset of) clean-200 sources.

    Args:
        registry:      source-name -> connector coroutine factory.
                       Defaults to FREE_BOARD_SOURCES; pass the merged
                       registry from global_sources to include portals.
        english_only:  drop postings not flagged english_friendly (B4).

    Returns (deduped recent jobs, per-source health summary).
    """
    health = health or SourceHealth()
    cutoff = (
        datetime.now(timezone.utc) - timedelta(hours=hours) if hours and hours > 0 else None
    )
    base = registry if registry is not None else FREE_BOARD_SOURCES
    sources = {k: v for k, v in base.items() if not only or k in only}

    collected: list[JobPost] = []
    async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
        async def _one(name: str, fn) -> list[JobPost]:
            return await guarded_source(
                name,
                lambda: fn(client=client, max_jobs=max_jobs_per_source),
                health=health,
            )

        results = await asyncio.gather(*[_one(n, fn) for n, fn in sources.items()])

    for batch in results:
        collected.extend(batch)

    recent = [j for j in collected if _is_recent(j, cutoff=cutoff)]
    if english_only:
        recent = [j for j in recent if j.extra_metadata.get("english_friendly", True)]
    unique = dedupe(recent)
    logger.info(
        "clean sources: %s raw → %s recent(<=%sh)%s → %s unique",
        len(collected), len(recent), hours,
        " english-only" if english_only else "", len(unique),
    )
    return unique, health.summary()


def main() -> int:
    parser = argparse.ArgumentParser(description="Scrape free clean-200 global job boards")
    parser.add_argument("--hours", type=int, default=8, help="Only keep jobs posted in the last N hours (0 = no limit)")
    parser.add_argument("--max", type=int, default=500, help="Max jobs per source")
    parser.add_argument("--only", type=str, default="", help="Comma-separated subset of sources")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    only = {s.strip() for s in args.only.split(",") if s.strip()} or None
    jobs, status = asyncio.run(
        run_free_boards(hours=args.hours, max_jobs_per_source=args.max, only=only)
    )
    print(f"\n{len(jobs)} unique jobs in last {args.hours}h")
    for src, st in status.items():
        print(f"  {src:16s} {st}")
    for j in jobs[:10]:
        loc = j.location or "—"
        print(f"  • [{j.source.value}] {j.title} @ {j.company} ({loc})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

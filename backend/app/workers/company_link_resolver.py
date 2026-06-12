"""Resolve official company career links for third-party scraped jobs.

For every active master_jobs row that came from a third-party portal
(LinkedIn, Dice, Glassdoor, Indeed, ...) and has not been checked yet, try to
locate the same opening on the employer's own ATS board / careers site via
app.services.company_career_resolver. On success the row's extra_metadata
gains a "company_link" object (consumed by the API + "Apply on Company
Website" button) and the description is upgraded to the first-party JD when
the ATS posting carries a richer one.

Usage:
    python -m app.workers.company_link_resolver --limit 200 --concurrency 5
    python -m app.workers.company_link_resolver --dry-run
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text

from app.db.postgres import PostgresClient
from app.services.company_career_resolver import get_board_postings, resolve_company_job
from app.services.job_description_details import clean_description_text

logger = logging.getLogger("placeup.workers.company_link_resolver")

# Sources that ALREADY come straight from the employer's ATS — nothing to
# resolve for these. Everything else (big portals, country job boards like
# EURES / MyCareersFuture / France Travail, aggregators, AI discovery) is a
# third-party intermediary and gets company-page resolution. This inverted
# list is what makes the flywheel cover countries where we have NO sponsor
# registry: their scraped jobs flow through here and lead us to the boards.
FIRST_PARTY_SOURCES = (
    "greenhouse", "lever", "ashby", "smartrecruiters", "workday", "recruitee",
    "personio", "teamtailor", "jazzhr", "rippling", "bamboohr", "workable",
    "h1b_sponsor", "tier1_ats",
)

CANDIDATE_SQL = """
SELECT id, source_name, source_job_id, source_url, title, company, location, description
FROM master_jobs
WHERE status = 'active'
  AND coalesce(source_name, '') <> ''
  AND lower(source_name) <> ALL(:first_party)
  AND coalesce(extra_metadata->>'company_link_checked', '') = ''
ORDER BY last_seen_at DESC
LIMIT :limit
"""

UPDATE_MASTER_SQL = """
UPDATE master_jobs
SET
    description = coalesce(nullif(:description, ''), description),
    extra_metadata = coalesce(extra_metadata, '{}'::jsonb) || cast(:metadata AS jsonb)
WHERE id = :id
"""

UPDATE_JOBS_SQL = """
UPDATE jobs
SET
    description = coalesce(nullif(:description, ''), description),
    extra_metadata = coalesce(extra_metadata, '{}'::jsonb) || cast(:metadata AS jsonb)
WHERE id = :id
   OR (
        source_name = :source_name
        AND source_job_id IS NOT NULL
        AND source_job_id = :source_job_id
   )
"""


def _candidate_rows(limit: int) -> list[dict[str, Any]]:
    client = PostgresClient()
    with client.session() as db:
        rows = db.execute(
            text(CANDIDATE_SQL),
            {"limit": limit, "first_party": list(FIRST_PARTY_SOURCES)},
        ).mappings().all()
    return [dict(row) for row in rows]


async def _resolve_one(row: dict[str, Any]) -> dict[str, Any]:
    link = await resolve_company_job(
        row.get("company") or "",
        row.get("title") or "",
        row.get("location") or "",
    )
    checked_at = datetime.now(timezone.utc).isoformat()
    if link is None:
        return {
            "id": row.get("id"),
            "status": "miss",
            "metadata": {"company_link_checked": checked_at},
            "description": "",
            "source_name": row.get("source_name") or "",
            "source_job_id": row.get("source_job_id") or "",
        }

    # Prefer the first-party JD when it is materially richer.
    new_description = ""
    if link.description:
        current = clean_description_text(row.get("description") or "")
        candidate = clean_description_text(link.description)[:60000]
        if len(candidate) > max(len(current) + 300, 600):
            new_description = candidate

    return {
        "id": row.get("id"),
        "status": "resolved",
        "metadata": {
            "company_link_checked": checked_at,
            "company_link": link.to_metadata(),
        },
        "description": new_description,
        "source_name": row.get("source_name") or "",
        "source_job_id": row.get("source_job_id") or "",
    }


def _write_results(results: list[dict[str, Any]]) -> dict[str, int]:
    client = PostgresClient()
    master_updated = 0
    jobs_updated = 0
    with client.session() as db:
        for result in results:
            params = {
                "id": result["id"],
                "description": result.get("description") or "",
                "metadata": json.dumps(result["metadata"]),
                "source_name": result.get("source_name") or "",
                "source_job_id": result.get("source_job_id") or "",
            }
            master_updated += int(db.execute(text(UPDATE_MASTER_SQL), params).rowcount or 0)
            jobs_updated += int(db.execute(text(UPDATE_JOBS_SQL), params).rowcount or 0)
    return {"master_updated": master_updated, "jobs_updated": jobs_updated}


async def _harvest_company_boards(companies: list[str]) -> dict[str, int]:
    """Ingest EVERY open posting from each discovered company ATS board.

    The resolver already downloaded these boards while matching individual
    scraped jobs (cached 6h), so harvesting them costs no extra scraping —
    it turns one LinkedIn-discovered company into full first-party coverage
    of that employer's openings, each with a direct apply link.
    """
    client = PostgresClient()
    payloads: list[dict] = []
    seen_ids: set[str] = set()
    boards_with_postings = 0
    for company in companies:
        postings = list(await get_board_postings(company))
        # Merge in the company's own careers portal found via web search —
        # ATS boards can be partial; the first-party portal (Workday /
        # Eightfold / embedded ATS) often lists more openings. Dedup by job
        # id below and by canonical key in the loader.
        try:
            from app.services.careers_page_ingest import collect_postings_for_company
            _, extra = await collect_postings_for_company(company)
            if extra:
                postings.extend(extra)
        except Exception as exc:  # noqa: BLE001
            logger.debug("Search-based portal harvest failed for %r: %s", company, exc)
        if not postings:
            continue
        boards_with_postings += 1
        for posting in postings:
            pid = str(getattr(posting, "id", "") or "")
            if not pid or pid in seen_ids:
                continue
            seen_ids.add(pid)
            try:
                payloads.append(posting.model_dump(mode="python"))
            except Exception:  # noqa: BLE001
                continue
    loaded = await client.upsert_jobs_batch(payloads) if payloads else 0
    rebuilt = 0
    if loaded:
        try:
            from app.etl.master_jobs import rebuild_master_jobs
            rebuilt = rebuild_master_jobs(client)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Master rebuild after board harvest failed: %s", exc)
    return {
        "boards_harvested": boards_with_postings,
        "board_postings_loaded": loaded,
        "master_rows_synced": rebuilt,
    }


async def run(limit: int, concurrency: int, dry_run: bool = False, harvest_boards: bool = True) -> dict[str, Any]:
    started = time.monotonic()
    rows = _candidate_rows(limit)
    semaphore = asyncio.Semaphore(concurrency)

    async def guarded(row: dict[str, Any]) -> dict[str, Any]:
        async with semaphore:
            try:
                return await _resolve_one(row)
            except Exception as exc:  # noqa: BLE001 — one bad row must not kill the batch
                logger.warning("Company link resolution failed for %s: %s", row.get("id"), exc)
                return {"id": row.get("id"), "status": "error", "metadata": {}, "description": ""}

    results = await asyncio.gather(*(guarded(row) for row in rows))
    resolved = [r for r in results if r.get("status") == "resolved"]
    misses = [r for r in results if r.get("status") == "miss"]
    writable = [r for r in results if r.get("metadata")]

    writes = {"master_updated": 0, "jobs_updated": 0}
    if writable and not dry_run:
        writes = _write_results(writable)

    # Harvest entire boards for every company the resolver touched this run:
    # one scraped third-party job -> all of that employer's open positions.
    harvest_stats = {"boards_harvested": 0, "board_postings_loaded": 0, "master_rows_synced": 0}
    if harvest_boards and not dry_run and rows:
        companies = sorted({str(r.get("company") or "").strip() for r in rows if str(r.get("company") or "").strip()})
        try:
            harvest_stats = await _harvest_company_boards(companies)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Board harvest step failed: %s", exc)

    summary = {
        "candidates": len(rows),
        "resolved": len(resolved),
        "misses": len(misses),
        "errors": len(results) - len(resolved) - len(misses),
        "elapsed_s": round(time.monotonic() - started, 1),
        **writes,
        **harvest_stats,
    }
    logger.info("Company link resolver finished: %s", summary)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=200)
    parser.add_argument("--concurrency", type=int, default=5)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--skip-board-harvest", action="store_true",
                        help="Only resolve links; don't ingest full company boards.")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    summary = asyncio.run(run(args.limit, args.concurrency, dry_run=args.dry_run, harvest_boards=not args.skip_board_harvest))
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

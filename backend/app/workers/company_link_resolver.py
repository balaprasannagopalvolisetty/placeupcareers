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
from app.services.company_career_resolver import resolve_company_job
from app.services.job_description_details import clean_description_text

logger = logging.getLogger("placeup.workers.company_link_resolver")

THIRD_PARTY_SOURCES = ("linkedin", "dice", "glassdoor", "indeed", "ziprecruiter", "simplyhired", "monster")

CANDIDATE_SQL = """
SELECT id, source_name, source_job_id, source_url, title, company, location, description
FROM master_jobs
WHERE status = 'active'
  AND lower(coalesce(source_name, '')) = ANY(:sources)
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
            {"limit": limit, "sources": list(THIRD_PARTY_SOURCES)},
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


async def run(limit: int, concurrency: int, dry_run: bool = False) -> dict[str, Any]:
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

    summary = {
        "candidates": len(rows),
        "resolved": len(resolved),
        "misses": len(misses),
        "errors": len(results) - len(resolved) - len(misses),
        "elapsed_s": round(time.monotonic() - started, 1),
        **writes,
    }
    logger.info("Company link resolver finished: %s", summary)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=200)
    parser.add_argument("--concurrency", type=int, default=5)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    summary = asyncio.run(run(args.limit, args.concurrency, dry_run=args.dry_run))
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

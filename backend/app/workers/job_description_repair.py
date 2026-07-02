"""Backfill thin job descriptions from public detail URLs."""

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
from app.services.job_description_details import (
    clean_description_text,
    fetch_full_job_description,
    is_html_fetch_allowed,
    is_thin_description,
)

logger = logging.getLogger("placeup.workers.job_description_repair")
ADVISORY_LOCK_KEY = 6412226682827


CANDIDATE_SQL = """
SELECT
    id,
    source_name,
    source_job_id,
    source_url,
    title,
    company,
    description,
    extra_metadata,
    coalesce(extra_metadata->>'source_table', 'master_jobs') AS source_table
FROM master_jobs
WHERE status = 'active'
  AND source_url IS NOT NULL
  AND source_url <> ''
  AND (
    description IS NULL
    OR length(description) < :thin_chars
    OR array_length(regexp_split_to_array(trim(coalesce(description, '')), '\\s+'), 1) < :thin_words
  )
ORDER BY last_seen_at DESC
LIMIT :limit
"""

UPDATE_MASTER_SQL = """
UPDATE master_jobs
SET
    description = :description,
    source_url = coalesce(nullif(:source_url, ''), source_url),
    extra_metadata = coalesce(extra_metadata, '{}'::jsonb) || cast(:metadata AS jsonb)
WHERE id = :id
"""

UPDATE_JOBS_SQL = """
UPDATE jobs
SET
    description = :description,
    source_url = coalesce(nullif(:source_url, ''), source_url),
    extra_metadata = coalesce(extra_metadata, '{}'::jsonb) || cast(:metadata AS jsonb)
WHERE id = :id
   OR source_url = :original_url
   OR (
        source_name = :source_name
        AND source_job_id IS NOT NULL
        AND source_job_id = :source_job_id
   )
"""

UPDATE_SILVER_SQL = """
UPDATE silver_posts
SET
    description_text = :description,
    job_url = coalesce(nullif(:source_url, ''), job_url),
    silver_updated_at = now()
WHERE job_url = :original_url
   OR (job_id IS NOT NULL AND job_id::text = :source_job_id)
"""


def _table_exists(db, table_name: str) -> bool:
    return bool(db.execute(text("SELECT to_regclass(:table_name)"), {"table_name": f"public.{table_name}"}).scalar())


def _candidate_rows(limit: int, thin_chars: int, thin_words: int) -> list[dict[str, Any]]:
    client = PostgresClient()
    with client.session() as db:
        rows = db.execute(
            text(CANDIDATE_SQL),
            {"limit": limit, "thin_chars": thin_chars, "thin_words": thin_words},
        ).mappings().all()
    return [dict(row) for row in rows if is_html_fetch_allowed(row.get("source_url") or "")]


def _is_better_description(current: str, candidate: str, *, thin_chars: int, thin_words: int) -> bool:
    current_clean = clean_description_text(current)
    candidate_clean = clean_description_text(candidate)
    if not candidate_clean:
        return False
    if not is_thin_description(current_clean, min_chars=thin_chars, min_words=thin_words):
        return False
    if len(candidate_clean.split()) < thin_words or len(candidate_clean) < thin_chars:
        return False
    return len(candidate_clean) >= len(current_clean) + 300


async def _repair_one(row: dict[str, Any], *, thin_chars: int, thin_words: int) -> dict[str, Any]:
    url = row.get("source_url") or ""
    details = await fetch_full_job_description(url)
    if not details:
        return {"id": row.get("id"), "status": "miss"}

    description = clean_description_text(details.description)[:60000]
    if not _is_better_description(row.get("description") or "", description, thin_chars=thin_chars, thin_words=thin_words):
        return {"id": row.get("id"), "status": "not_better"}

    return {
        "id": row.get("id"),
        "status": "repaired",
        "description": description,
        "source_url": details.source_url,
        "original_url": url,
        "extractor": details.extractor,
        "previous_length": len(clean_description_text(row.get("description") or "")),
        "new_length": len(description),
        "source_name": row.get("source_name") or "",
        "source_job_id": row.get("source_job_id") or "",
        "source_table": row.get("source_table") or "",
    }


def _write_repairs(repairs: list[dict[str, Any]]) -> dict[str, int]:
    if not repairs:
        return {"master_updated": 0, "jobs_updated": 0, "silver_updated": 0, "master_rebuilt": 0}

    client = PostgresClient()
    master_updated = 0
    jobs_updated = 0
    silver_updated = 0
    master_rebuilt = 0
    now = datetime.now(timezone.utc).isoformat()
    with client.session() as db:
        silver_exists = _table_exists(db, "silver_posts")
        for repair in repairs:
            metadata = json.dumps({
                "jd_repaired_at": now,
                "jd_repair_extractor": repair["extractor"],
                "jd_previous_length": repair["previous_length"],
                "jd_new_length": repair["new_length"],
            })
            params = {
                "id": repair["id"],
                "description": repair["description"],
                "source_url": repair["source_url"],
                "original_url": repair["original_url"],
                "source_name": repair["source_name"],
                "source_job_id": repair["source_job_id"],
                "metadata": metadata,
            }
            jobs_result = db.execute(text(UPDATE_JOBS_SQL), params)
            jobs_updated += int(jobs_result.rowcount or 0)
            if silver_exists:
                silver_result = db.execute(text(UPDATE_SILVER_SQL), params)
                silver_updated += int(silver_result.rowcount or 0)
            master_result = db.execute(text(UPDATE_MASTER_SQL), params)
            master_updated += int(master_result.rowcount or 0)

        try:
            from app.etl.master_jobs import rebuild_master_jobs

            master_rebuilt = rebuild_master_jobs(db=db)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Master jobs rebuild skipped after JD repair: %s", exc)

    return {
        "master_updated": master_updated,
        "jobs_updated": jobs_updated,
        "silver_updated": silver_updated,
        "master_rebuilt": master_rebuilt,
    }


async def run(limit: int, concurrency: int, thin_chars: int, thin_words: int, dry_run: bool = False) -> dict[str, Any]:
    started = time.monotonic()
    lock_client = PostgresClient()
    with lock_client.session() as lock_db:
        locked = bool(lock_db.execute(
            text("SELECT pg_try_advisory_lock(:lock_key)"),
            {"lock_key": ADVISORY_LOCK_KEY},
        ).scalar())
        if not locked:
            summary = {
                "skipped": True,
                "reason": "another_job_description_repair_execution_is_running",
                "candidates": 0,
                "repaired": 0,
                "missed": 0,
                "not_better": 0,
                "dry_run": dry_run,
                "duration_seconds": round(time.monotonic() - started, 2),
                "master_updated": 0,
                "jobs_updated": 0,
                "silver_updated": 0,
                "master_rebuilt": 0,
            }
            logger.warning("Job description repair skipped: %s", summary)
            return summary

        try:
            rows = _candidate_rows(limit, thin_chars, thin_words)
            semaphore = asyncio.Semaphore(concurrency)

            async def guarded(row: dict[str, Any]) -> dict[str, Any]:
                async with semaphore:
                    return await _repair_one(row, thin_chars=thin_chars, thin_words=thin_words)

            results = await asyncio.gather(*(guarded(row) for row in rows))
            repairs = [result for result in results if result.get("status") == "repaired"]
            writes = {"master_updated": 0, "jobs_updated": 0, "silver_updated": 0, "master_rebuilt": 0}
            if repairs and not dry_run:
                writes = _write_repairs(repairs)

            summary = {
                "skipped": False,
                "candidates": len(rows),
                "repaired": len(repairs),
                "missed": sum(1 for result in results if result.get("status") == "miss"),
                "not_better": sum(1 for result in results if result.get("status") == "not_better"),
                "dry_run": dry_run,
                "duration_seconds": round(time.monotonic() - started, 2),
                **writes,
            }
            logger.info("Job description repair complete: %s", summary)
            return summary
        finally:
            try:
                lock_db.execute(
                    text("SELECT pg_advisory_unlock(:lock_key)"),
                    {"lock_key": ADVISORY_LOCK_KEY},
                )
            except Exception as unlock_exc:  # noqa: BLE001
                logger.warning("Job description repair advisory unlock failed: %s", unlock_exc)


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill thin job descriptions from public detail URLs.")
    parser.add_argument("--limit", type=int, default=5000)
    parser.add_argument("--concurrency", type=int, default=6)
    parser.add_argument("--thin-chars", type=int, default=1200)
    parser.add_argument("--thin-words", type=int, default=120)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args()

    logging.basicConfig(
        level=args.log_level.upper(),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    print(json.dumps(asyncio.run(run(
        limit=args.limit,
        concurrency=args.concurrency,
        thin_chars=args.thin_chars,
        thin_words=args.thin_words,
        dry_run=args.dry_run,
    ))))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

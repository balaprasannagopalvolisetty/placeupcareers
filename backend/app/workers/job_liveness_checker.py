"""Verify active job URLs and remove postings that are definitively closed.

The regular scraper refreshes ``last_seen_at`` when it finds a role again, but
some providers keep stale records in feeds after their apply page has closed.
This bounded worker revisits the oldest unchecked active URLs. It deletes only
high-confidence closures (HTTP 404/410 or explicit closed/expired page text);
blocks, rate limits, timeouts, and server errors never remove a job.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import re
import time
from datetime import datetime, timezone

import httpx
from sqlalchemy import text

from app.db.postgres import PostgresClient

logger = logging.getLogger("placeup.workers.job_liveness_checker")

_CLOSED_PATTERNS = (
    re.compile(r"\bthis (?:job|position|role) (?:is )?no longer available\b", re.I),
    re.compile(r"\b(?:job|position|posting|role) (?:has been|is) (?:filled|closed|expired)\b", re.I),
    re.compile(r"\bno longer accepting applications\b", re.I),
    re.compile(r"\bthe (?:job|position) you (?:are looking for|requested) (?:is )?no longer available\b", re.I),
    re.compile(r"\bthis requisition (?:has been|is) closed\b", re.I),
)


def classify_job_page(status_code: int, body: str = "") -> str:
    """Return ``closed``, ``active``, or ``unknown`` conservatively."""
    if status_code in {404, 410}:
        return "closed"
    if status_code in {401, 403, 408, 425, 429} or status_code >= 500:
        return "unknown"
    if not 200 <= status_code < 400:
        return "unknown"
    clean = re.sub(r"<[^>]+>", " ", body or "")
    clean = re.sub(r"\s+", " ", clean)[:180_000]
    if any(pattern.search(clean) for pattern in _CLOSED_PATTERNS):
        return "closed"
    return "active"


async def _check_one(client: httpx.AsyncClient, row: dict, semaphore: asyncio.Semaphore) -> dict:
    async with semaphore:
        try:
            async with client.stream("GET", str(row["source_url"])) as response:
                chunks: list[bytes] = []
                size = 0
                async for chunk in response.aiter_bytes():
                    remaining = 180_000 - size
                    if remaining <= 0:
                        break
                    chunks.append(chunk[:remaining])
                    size += min(len(chunk), remaining)
                body = b"".join(chunks).decode(response.encoding or "utf-8", errors="ignore")
                result = classify_job_page(response.status_code, body)
                return {**row, "result": result, "status_code": response.status_code}
        except (httpx.TimeoutException, httpx.NetworkError, httpx.InvalidURL):
            return {**row, "result": "unknown", "status_code": None}
        except Exception as exc:  # pragma: no cover - provider-specific failures
            logger.debug("Liveness check failed for %s: %s", row.get("source_url"), exc)
            return {**row, "result": "unknown", "status_code": None}


async def run(limit: int = 1500, concurrency: int = 24, dry_run: bool = False) -> dict:
    started = time.monotonic()
    database = PostgresClient()
    with database.session() as session:
        rows = [dict(row) for row in session.execute(text("""
            SELECT id::text AS id, source_url
              FROM master_jobs
             WHERE status = 'active'
               AND source_url LIKE 'http%'
             ORDER BY extra_metadata->>'liveness_checked_at' NULLS FIRST,
                      last_seen_at ASC NULLS FIRST
             LIMIT :limit
        """), {"limit": max(1, min(int(limit), 10000))}).mappings().all()]

    timeout = httpx.Timeout(12.0, connect=6.0)
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; PlaceUpJobVerifier/1.0; +https://placeupcareer.com)",
        "Accept": "text/html,application/xhtml+xml",
    }
    semaphore = asyncio.Semaphore(max(1, min(int(concurrency), 64)))
    async with httpx.AsyncClient(timeout=timeout, headers=headers, follow_redirects=True) as client:
        checked = await asyncio.gather(*[_check_one(client, row, semaphore) for row in rows])

    closed = [row for row in checked if row["result"] == "closed"]
    now_iso = datetime.now(timezone.utc).isoformat()
    deleted_master = 0
    deleted_source = 0
    if not dry_run:
        with database.session() as session:
            for row in checked:
                if row["result"] != "closed":
                    session.execute(text("""
                        UPDATE master_jobs
                           SET extra_metadata = COALESCE(extra_metadata, '{}'::jsonb)
                               || jsonb_build_object(
                                   'liveness_checked_at', :checked_at,
                                   'liveness_http_status', :status_code
                               )
                         WHERE id = :id
                    """), {"id": row["id"], "checked_at": now_iso, "status_code": row["status_code"]})
            for row in closed:
                session.execute(text("""
                    UPDATE contacts
                       SET related_job_id = NULL
                     WHERE related_job_id IN (
                         SELECT id FROM jobs WHERE source_url = :source_url
                     )
                """), {"source_url": row["source_url"]})
                deleted_source += int(session.execute(
                    text("DELETE FROM jobs WHERE source_url = :source_url"),
                    {"source_url": row["source_url"]},
                ).rowcount or 0)
                deleted_master += int(session.execute(
                    text("DELETE FROM master_jobs WHERE id = :id"),
                    {"id": row["id"]},
                ).rowcount or 0)
            session.commit()

    summary = {
        "checked": len(checked),
        "active": sum(1 for row in checked if row["result"] == "active"),
        "unknown": sum(1 for row in checked if row["result"] == "unknown"),
        "confirmed_closed": len(closed),
        "master_jobs_deleted": deleted_master,
        "source_jobs_deleted": deleted_source,
        "dry_run": dry_run,
        "duration_seconds": round(time.monotonic() - started, 2),
    }
    logger.info("Job liveness check complete: %s", summary)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify active job URLs and remove confirmed closures.")
    parser.add_argument("--limit", type=int, default=1500)
    parser.add_argument("--concurrency", type=int, default=24)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    print(json.dumps(asyncio.run(run(args.limit, args.concurrency, args.dry_run))))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

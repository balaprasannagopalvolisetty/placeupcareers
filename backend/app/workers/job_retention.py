"""Job retention + taxonomy cleanup worker.

Two responsibilities, both idempotent and safe to run daily as a Cloud Run
Job (schedule via Cloud Scheduler):

1. ``purge_expired``   — hard-delete every posting older than the 60-day
   (2-month) retention window. Mirrors the frontend visibility boundary in
   ``app.api.jobs.VISIBLE_RETENTION_DAYS`` so the visible inventory and the
   stored inventory stay identical.

2. ``purge_non_taxonomy`` — OPT-IN ONLY (``--include-non-taxonomy``). Unknown
   titles are now KEPT: they feed the taxonomy-evolution worker, which
   surfaces high-volume unknown roles as candidates to add to the taxonomy
   and flags taxonomy roles with zero live inventory for removal
   (see workers/taxonomy_evolution.py).

Run locally / in the job container:

    python -m app.workers.job_retention            # both passes
    python -m app.workers.job_retention --dry-run  # report only
"""
from __future__ import annotations

import argparse
import logging

from sqlalchemy import text

from app.config import settings
from app.db.postgres import PostgresClient
from app.etl.purge_jobs_except_today import purge_outside_window
from app.job_taxonomy import categorize

logger = logging.getLogger("placeup.job_retention")

_BATCH = 5000


def purge_expired(*, retention_days: int | None = None, dry_run: bool = False) -> dict:
    """Rolling-window purge: delete postings older than the retention window."""
    days = int(retention_days or settings.job_retention_days or 60)
    counts = purge_outside_window(retention_days=days, dry_run=dry_run)
    logger.info("Retention purge (%sd, dry_run=%s): %s", days, dry_run, counts)
    return counts


def purge_non_taxonomy(*, dry_run: bool = False) -> dict:
    """Delete jobs whose title matches none of the 117 taxonomy roles.

    Titles are classified in Python with the same ``categorize`` matcher the
    Jobs feed uses, so the purge can never disagree with what the frontend
    would have shown. Batched scan keeps memory bounded on large tables.
    """
    client = PostgresClient()
    to_delete: list[str] = []
    scanned = 0
    with client.session() as db:
        offset = 0
        while True:
            rows = db.execute(
                text("SELECT id, title FROM jobs ORDER BY id LIMIT :lim OFFSET :off"),
                {"lim": _BATCH, "off": offset},
            ).mappings().all()
            if not rows:
                break
            for row in rows:
                scanned += 1
                category, role = categorize(str(row["title"] or ""))
                if category == "Other" and role == "Other":
                    to_delete.append(str(row["id"]))
            offset += _BATCH

        counts = {"scanned": scanned, "non_taxonomy": len(to_delete), "deleted": 0}
        if dry_run or not to_delete:
            return counts

        deleted = 0
        for start in range(0, len(to_delete), _BATCH):
            chunk = to_delete[start:start + _BATCH]
            db.execute(
                text("UPDATE contacts SET related_job_id = NULL WHERE related_job_id = ANY(:ids)"),
                {"ids": chunk},
            )
            db.execute(text("DELETE FROM master_jobs WHERE id = ANY(:ids)"), {"ids": chunk})
            deleted += int(db.execute(text("DELETE FROM jobs WHERE id = ANY(:ids)"), {"ids": chunk}).rowcount or 0)
        counts["deleted"] = deleted
    logger.info("Non-taxonomy purge: %s", counts)
    return counts


def run(*, dry_run: bool = False, include_non_taxonomy: bool = False) -> dict:
    result = {"expired": purge_expired(dry_run=dry_run)}
    if include_non_taxonomy:
        result["non_taxonomy"] = purge_non_taxonomy(dry_run=dry_run)
    return result


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    parser = argparse.ArgumentParser(description="Purge expired job postings (60-day retention).")
    parser.add_argument("--dry-run", action="store_true", help="Report counts without deleting")
    parser.add_argument("--retention-days", type=int, default=None, help="Override the retention window")
    parser.add_argument(
        "--include-non-taxonomy", action="store_true",
        help="ALSO delete jobs whose title maps to none of the taxonomy roles. "
             "Off by default: unknown titles are kept and reported by the "
             "taxonomy-evolution worker as candidates for new roles.",
    )
    args = parser.parse_args()
    result = {"expired": purge_expired(retention_days=args.retention_days, dry_run=args.dry_run)}
    if args.include_non_taxonomy:
        result["non_taxonomy"] = purge_non_taxonomy(dry_run=args.dry_run)
    print(result)

"""
Stale-jobs sweeper — flips `status` to `inactive` for any job that
hasn't been re-seen by the scraper in the configured window (default
14 days, controlled by `job_inactive_after_days` in settings).

Why this exists
---------------
A job's `last_seen_at` is updated every time the 6h or 12h scraper
finds it again on the source ATS. If a posting disappears from the
source — closed, filled, expired — `last_seen_at` stops advancing.
Without this sweeper, those stale rows just sit in `master_jobs`
forever marked `active`, polluting Jobs-page results and inflating
the active count on the dashboard.

The sweep runs as a Cloud Run Job (see deploy_separate_cloud_run.ps1)
and is scheduled daily by schedule_jobs.ps1. Two updates per run:

1. `jobs` table  — flip per-source rows older than the window.
2. `master_jobs` — flip the deduped row when the max last_seen_at
                    across all merged sources is older than the window.

Idempotent: re-running the same day re-flips already-inactive rows
with no harm. Cheap: two UPDATEs with an index on `last_seen_at`.

CLI:
    python -m app.workers.stale_jobs_sweeper --days 14 --dry-run
"""

from __future__ import annotations

import argparse
import json
import logging
import time

from sqlalchemy import text

from app.config import settings
from app.db.postgres import PostgresClient

logger = logging.getLogger("placeup.workers.stale_jobs_sweeper")


SWEEP_JOBS_SQL = """
UPDATE jobs
   SET status = 'inactive'
 WHERE status = 'active'
   AND last_seen_at < NOW() - (:days || ' days')::interval
"""

SWEEP_MASTER_SQL = """
UPDATE master_jobs
   SET status = 'inactive'
 WHERE status = 'active'
   AND last_seen_at < NOW() - (:days || ' days')::interval
"""

COUNT_RETENTION_JOBS_SQL = """
SELECT count(*)
  FROM jobs
 WHERE COALESCE(first_seen_at, last_seen_at) < NOW() - (:retention_days || ' days')::interval
"""

COUNT_RETENTION_MASTER_SQL = """
SELECT count(*)
  FROM master_jobs
 WHERE COALESCE(first_seen_at, last_seen_at) < NOW() - (:retention_days || ' days')::interval
"""

DELETE_RETENTION_CONTACT_LINKS_SQL = """
UPDATE contacts
   SET related_job_id = NULL
 WHERE related_job_id IN (
       SELECT id
         FROM jobs
        WHERE COALESCE(first_seen_at, last_seen_at) < NOW() - (:retention_days || ' days')::interval
 )
"""

DELETE_RETENTION_JOBS_SQL = """
DELETE FROM jobs
 WHERE COALESCE(first_seen_at, last_seen_at) < NOW() - (:retention_days || ' days')::interval
"""

DELETE_RETENTION_MASTER_SQL = """
DELETE FROM master_jobs
 WHERE COALESCE(first_seen_at, last_seen_at) < NOW() - (:retention_days || ' days')::interval
"""

COUNT_RETENTION_SILVER_SQL = """
SELECT count(*)
  FROM silver_posts
 WHERE silver_updated_at < NOW() - (:retention_days || ' days')::interval
"""

DELETE_RETENTION_SILVER_SQL = """
DELETE FROM silver_posts
 WHERE silver_updated_at < NOW() - (:retention_days || ' days')::interval
"""


def _silver_posts_exists(db) -> bool:
    return bool(db.execute(text("SELECT to_regclass('public.silver_posts')")).scalar())


def run(days: int, retention_days: int, dry_run: bool = False) -> dict:
    started = time.monotonic()
    client = PostgresClient()

    with client.session() as db:
        if dry_run:
            # Preview only — count how many rows would flip.
            jobs_affected = db.execute(
                text("SELECT count(*) FROM jobs WHERE status = 'active' "
                     "AND last_seen_at < NOW() - (:days || ' days')::interval"),
                {"days": days},
            ).scalar_one()
            master_affected = db.execute(
                text("SELECT count(*) FROM master_jobs WHERE status = 'active' "
                     "AND last_seen_at < NOW() - (:days || ' days')::interval"),
                {"days": days},
            ).scalar_one()
            jobs_updated = int(jobs_affected or 0)
            master_updated = int(master_affected or 0)
            jobs_deleted = int(db.execute(text(COUNT_RETENTION_JOBS_SQL), {"retention_days": retention_days}).scalar() or 0)
            master_deleted = int(db.execute(text(COUNT_RETENTION_MASTER_SQL), {"retention_days": retention_days}).scalar() or 0)
            silver_deleted = int(db.execute(text(COUNT_RETENTION_SILVER_SQL), {"retention_days": retention_days}).scalar() or 0) if _silver_posts_exists(db) else 0
        else:
            jobs_result = db.execute(text(SWEEP_JOBS_SQL), {"days": days})
            master_result = db.execute(text(SWEEP_MASTER_SQL), {"days": days})
            db.execute(text(DELETE_RETENTION_CONTACT_LINKS_SQL), {"retention_days": retention_days})
            jobs_delete_result = db.execute(text(DELETE_RETENTION_JOBS_SQL), {"retention_days": retention_days})
            master_delete_result = db.execute(text(DELETE_RETENTION_MASTER_SQL), {"retention_days": retention_days})
            if _silver_posts_exists(db):
                silver_deleted = int(db.execute(text(COUNT_RETENTION_SILVER_SQL), {"retention_days": retention_days}).scalar() or 0)
                db.execute(text(DELETE_RETENTION_SILVER_SQL), {"retention_days": retention_days})
            else:
                silver_deleted = 0
            db.commit()
            jobs_updated = int(jobs_result.rowcount or 0)
            master_updated = int(master_result.rowcount or 0)
            jobs_deleted = int(jobs_delete_result.rowcount or 0)
            master_deleted = int(master_delete_result.rowcount or 0)

    summary = {
        "threshold_days": days,
        "retention_days": retention_days,
        "dry_run": dry_run,
        "jobs_marked_inactive": jobs_updated,
        "master_jobs_marked_inactive": master_updated,
        "jobs_deleted": jobs_deleted,
        "master_jobs_deleted": master_deleted,
        "silver_posts_deleted": silver_deleted,
        "duration_seconds": round(time.monotonic() - started, 2),
    }
    logger.info("Stale-jobs sweeper complete: %s", summary)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Mark stale jobs inactive in jobs + master_jobs.")
    parser.add_argument(
        "--days", type=int,
        default=getattr(settings, "job_inactive_after_days", 14),
        help="Mark jobs as inactive if last_seen_at is older than this many days.",
    )
    parser.add_argument(
        "--retention-days", type=int,
        default=getattr(settings, "job_retention_days", 60),
        help="Hard-delete job rows older than this many days.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Count without updating.")
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args()

    logging.basicConfig(
        level=args.log_level.upper(),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    summary = run(days=args.days, retention_days=args.retention_days, dry_run=args.dry_run)
    print(json.dumps(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

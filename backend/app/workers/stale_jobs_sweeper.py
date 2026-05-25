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
   SET status = 'inactive',
       updated_at = NOW()
 WHERE status = 'active'
   AND last_seen_at < NOW() - (:days || ' days')::interval
"""

SWEEP_MASTER_SQL = """
UPDATE master_jobs
   SET status = 'inactive',
       updated_at = NOW()
 WHERE status = 'active'
   AND last_seen_at < NOW() - (:days || ' days')::interval
"""


def run(days: int, dry_run: bool = False) -> dict:
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
        else:
            jobs_result = db.execute(text(SWEEP_JOBS_SQL), {"days": days})
            master_result = db.execute(text(SWEEP_MASTER_SQL), {"days": days})
            db.commit()
            jobs_updated = int(jobs_result.rowcount or 0)
            master_updated = int(master_result.rowcount or 0)

    summary = {
        "threshold_days": days,
        "dry_run": dry_run,
        "jobs_marked_inactive": jobs_updated,
        "master_jobs_marked_inactive": master_updated,
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
    parser.add_argument("--dry-run", action="store_true", help="Count without updating.")
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args()

    logging.basicConfig(
        level=args.log_level.upper(),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    summary = run(days=args.days, dry_run=args.dry_run)
    print(json.dumps(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

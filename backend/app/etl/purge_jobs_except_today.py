"""Delete job postings outside the current local day.

Use this after a forced refresh when the frontend must show only today's
postings. The effective date is `posted_at` when present, otherwise
`last_seen_at`, so rows with an old posted date do not survive simply because
they were re-scraped today.
"""

from __future__ import annotations

import argparse
from datetime import datetime, time, timezone
import logging
from zoneinfo import ZoneInfo

from sqlalchemy import text

from app.db.postgres import PostgresClient
from app.etl.master_jobs import rebuild_master_jobs

logger = logging.getLogger(__name__)


def _bounds(day: str | None, tz_name: str) -> tuple[datetime, datetime, str]:
    zone = ZoneInfo(tz_name)
    local_date = datetime.now(zone).date() if not day else datetime.strptime(day, "%Y-%m-%d").date()
    start_local = datetime.combine(local_date, time.min, tzinfo=zone)
    end_local = datetime.combine(local_date, time.max, tzinfo=zone)
    start_utc = start_local.astimezone(timezone.utc)
    end_utc = end_local.astimezone(timezone.utc)
    return start_utc, end_utc, local_date.isoformat()


def purge_except_day(*, day: str | None, tz_name: str, dry_run: bool) -> dict[str, int | str]:
    start_utc, end_utc, day_label = _bounds(day, tz_name)
    params = {"start_utc": start_utc, "end_utc": end_utc}
    outside_jobs = """
        COALESCE(posted_at, last_seen_at) IS NULL
        OR COALESCE(posted_at, last_seen_at) < :start_utc
        OR COALESCE(posted_at, last_seen_at) > :end_utc
    """
    outside_master = outside_jobs

    client = PostgresClient()
    with client.session() as db:
        counts: dict[str, int | str] = {
            "kept_date": day_label,
            "timezone": tz_name,
        }
        counts["jobs_to_delete"] = int(db.execute(text(f"SELECT COUNT(*) FROM jobs WHERE {outside_jobs}"), params).scalar() or 0)
        counts["master_jobs_to_delete"] = int(db.execute(text(f"SELECT COUNT(*) FROM master_jobs WHERE {outside_master}"), params).scalar() or 0)
        counts["staging_to_delete"] = int(db.execute(text(
            "SELECT COUNT(*) FROM staging_records WHERE last_seen_at < :start_utc OR last_seen_at > :end_utc"
        ), params).scalar() or 0)
        if dry_run:
            return counts

        db.execute(text(f"""
            UPDATE contacts
               SET related_job_id = NULL
             WHERE related_job_id IN (SELECT id FROM jobs WHERE {outside_jobs})
        """), params)
        counts["master_jobs_deleted"] = int(db.execute(text(f"DELETE FROM master_jobs WHERE {outside_master}"), params).rowcount or 0)
        counts["jobs_deleted"] = int(db.execute(text(f"DELETE FROM jobs WHERE {outside_jobs}"), params).rowcount or 0)
        counts["staging_deleted"] = int(db.execute(text(
            "DELETE FROM staging_records WHERE last_seen_at < :start_utc OR last_seen_at > :end_utc"
        ), params).rowcount or 0)
        counts["master_jobs_rebuilt"] = rebuild_master_jobs(db=db)
        return counts


def main() -> int:
    parser = argparse.ArgumentParser(description="Keep only one local day's job postings.")
    parser.add_argument("--date", help="Local date to keep, YYYY-MM-DD. Defaults to today in --timezone.")
    parser.add_argument("--timezone", default="America/Chicago")
    parser.add_argument("--yes", action="store_true", help="Required to delete rows.")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    if not args.yes and not args.dry_run:
        parser.error("Refusing to delete without --yes. Use --dry-run to inspect counts.")
    counts = purge_except_day(day=args.date, tz_name=args.timezone, dry_run=args.dry_run)
    for key, value in counts.items():
        logger.info("%s: %s", key, value)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

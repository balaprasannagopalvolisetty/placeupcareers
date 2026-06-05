"""Purge all scraped job postings from the production database.

This is intentionally a separate one-shot utility because clearing the job
board is destructive. It removes the active serving rows and scraper staging
history so the next 6-hour run refills the frontend from fresh source data.
"""

from __future__ import annotations

import argparse
import logging

from sqlalchemy import text

from app.db.postgres import PostgresClient

logger = logging.getLogger(__name__)


DELETE_STATEMENTS: tuple[tuple[str, str], ...] = (
    ("contacts.related_job_id", "UPDATE contacts SET related_job_id = NULL WHERE related_job_id IS NOT NULL"),
    ("master_jobs", "DELETE FROM master_jobs"),
    ("jobs", "DELETE FROM jobs"),
    ("staging_records", "DELETE FROM staging_records"),
    ("job ingest_runs", "DELETE FROM ingest_runs WHERE pipeline_name ILIKE '%job%' OR source_name ILIKE '%job%' OR source_name ILIKE '%scrap%'"),
)

COUNT_STATEMENTS: tuple[tuple[str, str], ...] = (
    ("contacts.related_job_id", "SELECT COUNT(*) FROM contacts WHERE related_job_id IS NOT NULL"),
    ("master_jobs", "SELECT COUNT(*) FROM master_jobs"),
    ("jobs", "SELECT COUNT(*) FROM jobs"),
    ("staging_records", "SELECT COUNT(*) FROM staging_records"),
    ("job ingest_runs", "SELECT COUNT(*) FROM ingest_runs WHERE pipeline_name ILIKE '%job%' OR source_name ILIKE '%job%' OR source_name ILIKE '%scrap%'"),
)


def purge_job_postings(*, dry_run: bool) -> dict[str, int]:
    client = PostgresClient()
    counts: dict[str, int] = {}
    with client.session() as db:
        if dry_run:
            for label, sql in COUNT_STATEMENTS:
                counts[label] = int(db.execute(text(sql)).scalar() or 0)
            return counts

        for label, sql in DELETE_STATEMENTS:
            result = db.execute(text(sql))
            counts[label] = int(result.rowcount or 0)
            logger.info("Purged %s rows from %s", counts[label], label)
    return counts


def main() -> int:
    parser = argparse.ArgumentParser(description="Delete all scraped job postings and staging rows.")
    parser.add_argument("--yes", action="store_true", help="Required to perform the destructive purge.")
    parser.add_argument("--dry-run", action="store_true", help="Only print row counts; do not delete.")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    if not args.yes and not args.dry_run:
        parser.error("Refusing to purge without --yes. Use --dry-run to inspect counts.")

    counts = purge_job_postings(dry_run=args.dry_run)
    for label, count in counts.items():
        logger.info("%s: %s", label, count)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

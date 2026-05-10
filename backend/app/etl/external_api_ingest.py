"""Cloud Run Job entrypoint for 12-hour external API ingests.

This is intentionally a framework shell: each paid/free API provider should
be added as a source module, then routed through the same staging_records
and ingest_runs tables used by the 6-hour job scraper.
"""

from __future__ import annotations

import argparse
import logging

from app.db.postgres import PostgresClient
from app.etl.run_manager import finish_ingest_run, start_ingest_run

logger = logging.getLogger("placeup.etl.external_api_ingest")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run 12-hour external API ingestion.")
    parser.add_argument("--provider", default="all", help="Provider key to ingest, or all.")
    parser.add_argument("--schedule-type", default="12h")
    return parser.parse_args()


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    args = parse_args()
    client = PostgresClient()
    with client.session() as db:
        run = start_ingest_run(
            db,
            source_name=args.provider,
            pipeline_name="external_api_ingest",
            schedule_type=args.schedule_type,
        )
        finish_ingest_run(
            db,
            run,
            status="success",
            records_seen=0,
            records_staged=0,
            records_inserted=0,
            records_updated=0,
        )
    logger.info("External API ETL framework is ready; add provider source modules under app.etl.sources.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Cloud Run Job entrypoint for the 6-hour job scraping pipeline.

The pipeline is staging-first:
1. Run configured job scrapers.
2. Persist every normalized scrape result to staging_records.
3. Upsert companies/jobs from staging-normalized payloads.
4. Record run metrics in ingest_runs.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.db.postgres import PostgresClient, stable_hash
from app.db.schema import IngestRun
from app.etl.loaders.jobs import load_normalized_jobs
from app.etl.normalizers.jobs import normalize_job_payload
from app.etl.run_manager import finish_ingest_run, start_ingest_run
from app.models.job import JobSource, ScrapeRequest
from app.scrape_constants import DEFAULT_SCRAPE_SEARCH_TERMS

logger = logging.getLogger("placeup.etl.jobs_scraper")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the PlaceUp staging-first job scraper ETL.")
    parser.add_argument("--queries", default=None, help="Comma-separated search terms.")
    parser.add_argument("--locations", default="United States", help="Comma-separated locations.")
    parser.add_argument("--sources", default=None, help="Comma-separated JobSource values. Defaults to core sources.")
    parser.add_argument("--max-per-source", type=int, default=120)
    parser.add_argument("--max-per-sponsor", type=int, default=500)
    parser.add_argument("--tiers", default="T1,T2")
    parser.add_argument("--schedule-type", default="6h")
    parser.add_argument("--dry-run", action="store_true", help="Fetch and normalize, but do not write to Postgres.")
    return parser.parse_args()


def build_request(args: argparse.Namespace) -> ScrapeRequest:
    queries = (
        [q.strip() for q in args.queries.split(",") if q.strip()]
        if args.queries
        else list(DEFAULT_SCRAPE_SEARCH_TERMS)
    )
    locations = [loc.strip() for loc in args.locations.split(",") if loc.strip()] or ["United States"]
    tiers = [tier.strip() for tier in args.tiers.split(",") if tier.strip()] or ["T1", "T2"]
    if args.sources:
        sources = [JobSource(src.strip()) for src in args.sources.split(",") if src.strip()]
    else:
        sources = [
            JobSource.LINKEDIN,
            JobSource.INDEED,
            JobSource.GLASSDOOR,
            JobSource.ZIPRECRUITER,
            JobSource.GOOGLE,
            JobSource.USAJOBS,
            JobSource.DICE,
            JobSource.H1B_SPONSOR,
        ]
    return ScrapeRequest(
        search_terms=queries,
        locations=locations,
        sources=sources,
        results_per_source=args.max_per_source,
        h1b_sponsor_tiers=tiers,
        h1b_sponsor_max_jobs=args.max_per_sponsor,
    )


async def run(args: argparse.Namespace) -> int:
    from app.services.job_scraper import run_scrape_cycle

    request = build_request(args)
    result, jobs = await run_scrape_cycle(request=request, existing_hashes=set())
    job_payloads = [job.model_dump(mode="json") for job in jobs]
    normalized = [normalize_job_payload(payload) for payload in job_payloads]
    staging_records = [
        {
            "source_record_id": payload.get("source_job_id") or payload.get("id"),
            "source_url": payload.get("job_url") or payload.get("job_url_direct"),
            "record_hash": stable_hash(payload),
            "payload": payload,
            "normalized_payload": normalized_payload,
            "validation_status": "valid" if normalized_payload.get("title") else "invalid",
            "validation_errors": [] if normalized_payload.get("title") else ["missing title"],
        }
        for payload, normalized_payload in zip(job_payloads, normalized)
    ]

    logger.info(
        "Fetched %s raw jobs, %s unique normalized jobs in %.2fs",
        result.total_scraped,
        len(normalized),
        result.duration_seconds,
    )

    if args.dry_run:
        logger.info("Dry run enabled; skipping database writes.")
        return 0

    client = PostgresClient()
    with client.session() as db:
        run_row = start_ingest_run(
            db,
            source_name="job_scraper",
            pipeline_name="jobs_scraper",
            schedule_type=args.schedule_type,
        )
        run_id = run_row.id

    try:
        with client.session() as db:
            run_row = db.get(IngestRun, run_id)
            if run_row is None:
                raise RuntimeError(f"Ingest run disappeared: {run_id}")
            staged = client.stage_records(db, run_id, "job_scraper", staging_records)
            loaded = load_normalized_jobs(db, normalized)
            try:
                from app.etl.master_jobs import rebuild_master_jobs
                rebuild_master_jobs(client)
            except Exception as sync_exc:
                logger.warning("Master jobs sync failed after scraper load: %s", sync_exc)
            finish_ingest_run(
                db,
                run_row,
                status="success",
                records_seen=result.total_scraped,
                records_staged=staged,
                records_inserted=loaded,
                records_updated=loaded,
                records_failed=len([r for r in staging_records if r["validation_status"] != "valid"]),
            )
            logger.info("ETL run %s complete: staged=%s loaded=%s", run_id, staged, loaded)
    except Exception as exc:
        with client.session() as db:
            run_row = db.get(IngestRun, run_id)
            if run_row is not None:
                finish_ingest_run(
                    db,
                    run_row,
                    status="failed",
                    records_seen=result.total_scraped,
                    records_failed=len(staging_records),
                    error_message=str(exc),
                )
        logger.exception("ETL run %s failed", run_id)
        return 1
    return 0


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    return asyncio.run(run(parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())

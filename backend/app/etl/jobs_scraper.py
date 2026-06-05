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
import re
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


def split_cli_list(value: str | None, *, decode_underscores: bool = False) -> list[str]:
    if not value:
        return []
    items = [item.strip() for item in re.split(r"[,|~]", value) if item.strip()]
    if decode_underscores:
        return [item.replace("_", " ") for item in items]
    return items


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the PlaceUp staging-first job scraper ETL.")
    parser.add_argument("--queries", default=None, help="Comma-separated search terms.")
    parser.add_argument("--locations", default="United States", help="Comma-separated locations.")
    parser.add_argument("--sources", default=None, help="Comma-separated JobSource values. Defaults to core sources.")
    parser.add_argument("--max-per-source", type=int, default=120)
    parser.add_argument("--max-per-sponsor", type=int, default=500)
    parser.add_argument("--h1b-sponsor-concurrency", type=int, default=8)
    parser.add_argument("--jobspy-hours-old", type=int, default=336)
    parser.add_argument("--jobspy-page-size", type=int, default=35)
    parser.add_argument("--jobspy-max-pages", type=int, default=15)
    parser.add_argument("--tiers", default="T1,T2")
    parser.add_argument("--schedule-type", default="6h")
    parser.add_argument("--dry-run", action="store_true", help="Fetch and normalize, but do not write to Postgres.")
    return parser.parse_args()


def build_request(args: argparse.Namespace) -> ScrapeRequest:
    queries = split_cli_list(args.queries, decode_underscores=True) or list(DEFAULT_SCRAPE_SEARCH_TERMS)
    locations = split_cli_list(args.locations, decode_underscores=True) or ["United States"]
    tiers = split_cli_list(args.tiers) or ["T1", "T2"]
    if args.sources:
        sources = [JobSource(src.strip()) for src in split_cli_list(args.sources)]
    else:
        sources = [
            JobSource.RAPIDAPI,
            JobSource.USAJOBS,
            JobSource.DICE,
            JobSource.REMOTEOK,
            JobSource.REMOTIVE,
            JobSource.ARBEITNOW,
            JobSource.JOBICY,
            JobSource.WEWORKREMOTELY,
            JobSource.JOBTECH,
            JobSource.EURES,
            JobSource.UK_FIND_A_JOB,
            JobSource.NHS_JOBS,
            JobSource.JOBBANK_CA,
            JobSource.BA_JOBSUCHE,
            JobSource.FRANCE_TRAVAIL,
            JobSource.MYCAREERSFUTURE,
            JobSource.TYOMARKKINATORI,
            JobSource.NAV_ARBEIDSPLASSEN,
            JobSource.H1B_SPONSOR,
            # Direct Tier-1 ATS pulls (Greenhouse/Lever/Ashby/SmartRecruiters/
            # Workable/Recruitee). Filtered to the expanded taxonomy roles before
            # they hit master_jobs. See app/etl/sources/tier1_ats.py.
            JobSource.TIER1_ATS,
            JobSource.SCRAPLING_DISCOVERY,
        ]
    return ScrapeRequest(
        search_terms=queries,
        locations=locations,
        sources=sources,
        results_per_source=args.max_per_source,
        h1b_sponsor_tiers=tiers,
        h1b_sponsor_max_jobs=args.max_per_sponsor,
        h1b_sponsor_concurrency=getattr(args, "h1b_sponsor_concurrency", 8),
        jobspy_hours_old=getattr(args, "jobspy_hours_old", 336),
        jobspy_page_size=getattr(args, "jobspy_page_size", 35),
        jobspy_max_pages=getattr(args, "jobspy_max_pages", 15),
    )


async def run(args: argparse.Namespace) -> int:
    from app.services.job_scraper import run_scrape_cycle

    request = build_request(args)
    # Strip custom aggregate sources off the request before run_scrape_cycle
    # sees them — the inner cycle doesn't know about them, we'll run them
    # ourselves and merge afterwards.
    tier1_enabled = JobSource.TIER1_ATS in (request.sources or [])
    if tier1_enabled:
        request.sources = [s for s in request.sources if s != JobSource.TIER1_ATS]
    scrapegraph_discovery_enabled = JobSource.SCRAPEGRAPH_DISCOVERY in (request.sources or [])
    if scrapegraph_discovery_enabled:
        request.sources = [s for s in request.sources if s != JobSource.SCRAPEGRAPH_DISCOVERY]

    result, jobs = await run_scrape_cycle(request=request, existing_hashes=set())

    if tier1_enabled:
        try:
            from app.etl.sources.tier1_ats import scrape_tier1_ats
            tier1_jobs = await scrape_tier1_ats(
                tiers=tuple(request.h1b_sponsor_tiers or ("T1", "T2")),
                max_jobs_per_sponsor=request.h1b_sponsor_max_jobs or 500,
                concurrency=request.h1b_sponsor_concurrency or 8,
                apply_taxonomy_filter=True,
            )
            logger.info("tier1_ats added %s jobs (post-taxonomy filter)", len(tier1_jobs))
            # Dedup by content_hash so a Stripe role that also came in
            # via JobSpy doesn't get duplicated by the Tier-1 pull.
            seen = {j.content_hash for j in jobs if getattr(j, "content_hash", None)}
            added = 0
            for tj in tier1_jobs:
                if not getattr(tj, "content_hash", None) or tj.content_hash in seen:
                    continue
                seen.add(tj.content_hash)
                jobs.append(tj)
                added += 1
            result.total_scraped += added
            result.new_jobs += added
            result.sources_used = sorted(set([*result.sources_used, "tier1_ats"]))
            result.source_breakdown["tier1_ats"] = {
                "attempts": 1,
                "scraped": len(tier1_jobs),
                "unique": added,
                "errors": 0,
            }
        except Exception as exc:
            logger.warning("tier1_ats source failed (non-fatal): %s", exc)
            result.errors.append(f"tier1_ats: {exc}")
            result.source_breakdown["tier1_ats"] = {
                "attempts": 1,
                "scraped": 0,
                "unique": 0,
                "errors": 1,
            }

    if scrapegraph_discovery_enabled:
        try:
            from app.services.scrapegraph_discovery import scrape_scrapegraph_discovery
            scrapegraph_jobs = await scrape_scrapegraph_discovery()
            logger.info("scrapegraph_discovery added %s jobs", len(scrapegraph_jobs))
            seen = {j.content_hash for j in jobs if getattr(j, "content_hash", None)}
            added = 0
            for sj in scrapegraph_jobs:
                if not getattr(sj, "content_hash", None) or sj.content_hash in seen:
                    continue
                seen.add(sj.content_hash)
                jobs.append(sj)
                added += 1
            result.total_scraped += added
            result.new_jobs += added
            result.sources_used = sorted(set([*result.sources_used, "scrapegraph_discovery"]))
            result.source_breakdown["scrapegraph_discovery"] = {
                "attempts": 1,
                "scraped": len(scrapegraph_jobs),
                "unique": added,
                "errors": 0,
            }
        except Exception as exc:
            logger.warning("scrapegraph_discovery source failed (non-fatal): %s", exc)
            result.errors.append(f"scrapegraph_discovery: {exc}")
            result.source_breakdown["scrapegraph_discovery"] = {
                "attempts": 1,
                "scraped": 0,
                "unique": 0,
                "errors": 1,
            }

    job_payloads = [job.model_dump(mode="json") for job in jobs]
    normalized = [normalize_job_payload(payload) for payload in job_payloads]
    staging_records = [
        {
            "source_record_id": payload.get("source_job_id") or payload.get("id"),
            "source_url": payload.get("job_url") or payload.get("job_url_direct"),
            "record_hash": stable_hash(payload),
            "payload": payload,
            "normalized_payload": normalized_payload,
            "validation_status": "valid" if normalized_payload.get("title") and not _normalization_errors(normalized_payload) else "invalid",
            "validation_errors": _normalization_errors(normalized_payload) or ([] if normalized_payload.get("title") else ["missing title"]),
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
            db.commit()
            try:
                from app.etl.master_jobs import rebuild_master_jobs
                rebuild_master_jobs(db=db)
            except Exception as sync_exc:
                db.rollback()
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


def _normalization_errors(normalized_payload: dict) -> list[str]:
    metadata = normalized_payload.get("extra_metadata") or {}
    if not isinstance(metadata, dict):
        return []
    errors = metadata.get("validation_errors") or []
    return [str(error) for error in errors if str(error).strip()] if isinstance(errors, list) else []


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    return asyncio.run(run(parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())

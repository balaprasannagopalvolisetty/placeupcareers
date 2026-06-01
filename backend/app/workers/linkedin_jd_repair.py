"""Repair existing LinkedIn rows with board-company names or thin JDs."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import time

from sqlalchemy import func, select

from app.db.postgres import PostgresClient
from app.db.schema import Company, Job
from app.etl.loaders.jobs import load_normalized_jobs
from app.etl.normalizers.jobs import normalize_job_payload
from app.models.job import JobPost
from app.services.linkedin_job_details import BOARD_COMPANIES, enrich_linkedin_jobs

logger = logging.getLogger("placeup.workers.linkedin_jd_repair")


def _job_to_payload(job: Job, company: Company | None) -> dict:
    return {
        "id": job.id,
        "title": job.title,
        "company": company.name if company else "",
        "location": job.location or "",
        "description": job.description or "",
        "job_url": job.source_url or "",
        "category": job.category or "Other",
        "job_type": job.employment_type or "",
        "source": job.source_name or "linkedin",
        "source_job_id": job.source_job_id or "",
        "posted_at": job.posted_at,
        "scraped_at": job.last_seen_at,
        "status": job.status or "active",
        "content_hash": job.content_hash or job.id,
        "visa": {
            "visa_opt": job.visa_opt,
            "visa_stem_opt": job.visa_stem_opt,
            "visa_h1b": job.visa_h1b,
            "h1b_verified": job.h1b_verified,
            "visa_score": job.visa_score,
        },
        "extra_metadata": job.extra_metadata or {},
    }


def _candidate_payloads(limit: int) -> list[dict]:
    client = PostgresClient()
    board_names = tuple(sorted(BOARD_COMPANIES))
    with client.session() as db:
        rows = db.execute(
            select(Job, Company)
            .join(Company, Job.company_id == Company.id, isouter=True)
            .where(Job.source_url.ilike("%linkedin.com/jobs/%"))
            .where(
                (Company.normalized_name.in_(board_names))
                | (Job.description.is_(None))
                | (Job.description == "")
                | (func.length(Job.description) < 450)
            )
            .order_by(Job.last_seen_at.desc())
            .limit(limit)
        ).all()
    return [_job_to_payload(job, company) for job, company in rows]


async def run(limit: int, dry_run: bool = False) -> dict:
    started = time.monotonic()
    payloads = _candidate_payloads(limit)
    jobs: list[JobPost] = []
    for payload in payloads:
        try:
            jobs.append(JobPost(**payload))
        except Exception as exc:
            logger.debug("Skipping invalid LinkedIn repair candidate %s: %s", payload.get("id"), exc)

    repaired = await enrich_linkedin_jobs(jobs, max_jobs=limit, concurrency=4)
    write_count = 0
    if repaired and not dry_run:
        normalized = [normalize_job_payload(job.model_dump(mode="json")) for job in jobs]
        client = PostgresClient()
        with client.session() as db:
            write_count = load_normalized_jobs(db, normalized)
            try:
                from app.etl.master_jobs import rebuild_master_jobs

                rebuild_master_jobs(db=db)
            except Exception as exc:
                logger.warning("Master jobs rebuild skipped after LinkedIn repair: %s", exc)

    summary = {
        "candidates": len(payloads),
        "valid_candidates": len(jobs),
        "repaired": repaired,
        "written": write_count,
        "dry_run": dry_run,
        "duration_seconds": round(time.monotonic() - started, 2),
    }
    logger.info("LinkedIn JD repair complete: %s", summary)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Repair existing LinkedIn rows with missing company/JD details.")
    parser.add_argument("--limit", type=int, default=500)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args()

    logging.basicConfig(
        level=args.log_level.upper(),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    print(json.dumps(asyncio.run(run(limit=args.limit, dry_run=args.dry_run))))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

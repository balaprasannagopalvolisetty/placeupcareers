"""Load normalized staged job records into core Postgres tables."""

from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.db.postgres import upsert_company
from app.db.schema import Job


def load_normalized_jobs(db: Session, jobs: list[dict]) -> int:
    count = 0
    for job in jobs:
        normalized = job if "company_name" in job else _compat_normalize(job)
        if not normalized.get("id") or not normalized.get("title") or not normalized.get("company_name"):
            continue

        company = upsert_company(db, normalized["company_name"])
        values = {
            "id": normalized["id"],
            "company_id": company.id if company else None,
            "title": normalized["title"],
            "normalized_title": normalized.get("normalized_title"),
            "location": normalized.get("location"),
            "country": normalized.get("country"),
            "category": normalized.get("category"),
            "source_name": normalized.get("source_name") or "unknown",
            "source_job_id": normalized.get("source_job_id"),
            "source_url": normalized.get("source_url"),
            "description": normalized.get("description"),
            "employment_type": normalized.get("employment_type"),
            "remote_type": normalized.get("remote_type"),
            "salary_min": normalized.get("salary_min"),
            "salary_max": normalized.get("salary_max"),
            "currency": normalized.get("currency"),
            "visa_opt": normalized.get("visa_opt", False),
            "visa_stem_opt": normalized.get("visa_stem_opt", False),
            "visa_h1b": normalized.get("visa_h1b", False),
            "h1b_verified": normalized.get("h1b_verified", False),
            "visa_score": normalized.get("visa_score", 0),
            "content_hash": normalized.get("content_hash") or normalized["id"],
            "status": normalized.get("status") or "active",
            "posted_at": normalized.get("posted_at"),
            "extra_metadata": normalized.get("extra_metadata") or {},
        }
        stmt = insert(Job).values(**values)
        stmt = stmt.on_conflict_do_update(
            index_elements=[Job.content_hash],
            set_={k: v for k, v in values.items() if k not in {"id", "content_hash"}},
        )
        db.execute(stmt)
        count += 1
    return count


def _compat_normalize(job: dict) -> dict:
    from app.etl.normalizers.jobs import normalize_job_payload

    return normalize_job_payload(job)

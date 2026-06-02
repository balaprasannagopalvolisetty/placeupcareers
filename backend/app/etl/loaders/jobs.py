"""Load normalized staged job records into core Postgres tables."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.postgres import upsert_company
from app.db.schema import Job


def load_normalized_jobs(db: Session, jobs: list[dict]) -> int:
    count = 0
    seen_ids: set[str] = set()
    seen_hashes: set[str] = set()
    seen_source_keys: set[tuple[str, str]] = set()

    for job in jobs:
        normalized = job if "company_name" in job else _compat_normalize(job)
        if not normalized.get("id") or not normalized.get("title") or not normalized.get("company_name"):
            continue

        company = upsert_company(db, normalized["company_name"])
        values = {
            "id": _clip(normalized["id"], 80),
            "company_id": company.id if company else None,
            "title": _clip(normalized["title"], 500),
            "normalized_title": _clip(normalized.get("normalized_title"), 500),
            "location": _clip(normalized.get("location"), 300),
            "country": _clip(normalized.get("country"), 80),
            "category": _clip(normalized.get("category"), 120),
            "source_name": _clip(normalized.get("source_name") or "unknown", 120),
            "source_job_id": _clip(normalized.get("source_job_id"), 240),
            "source_url": _text_or_none(normalized.get("source_url")),
            "description": normalized.get("description"),
            "employment_type": _clip(normalized.get("employment_type"), 120),
            "remote_type": _clip(normalized.get("remote_type"), 120),
            "salary_min": normalized.get("salary_min"),
            "salary_max": normalized.get("salary_max"),
            "currency": _clip(normalized.get("currency"), 12),
            "visa_opt": normalized.get("visa_opt", False),
            "visa_stem_opt": normalized.get("visa_stem_opt", False),
            "visa_h1b": normalized.get("visa_h1b", False),
            "h1b_verified": normalized.get("h1b_verified", False),
            "visa_score": normalized.get("visa_score", 0),
            "content_hash": _clip(normalized.get("content_hash") or normalized["id"], 128),
            "status": _clip(normalized.get("status") or "active", 30),
            "posted_at": normalized.get("posted_at"),
            "extra_metadata": normalized.get("extra_metadata") or {},
        }

        source_key = _source_key(values)
        if values["id"] in seen_ids or values["content_hash"] in seen_hashes or source_key in seen_source_keys:
            continue
        seen_ids.add(values["id"])
        seen_hashes.add(values["content_hash"])
        if source_key:
            seen_source_keys.add(source_key)

        existing = _find_existing_job(db, values)
        if existing:
            _update_existing_job(db, existing, values)
        else:
            db.add(Job(**values))
        count += 1
    return count


def _clip(value: object, max_len: int) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return text[:max_len]


def _text_or_none(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _source_key(values: dict) -> tuple[str, str] | None:
    source_name = values.get("source_name")
    source_job_id = values.get("source_job_id")
    if not source_name or not source_job_id:
        return None
    return (source_name, source_job_id)


def _find_existing_job(db: Session, values: dict) -> Job | None:
    existing = db.get(Job, values["id"])
    if existing:
        return existing

    existing = db.execute(select(Job).where(Job.content_hash == values["content_hash"])).scalar_one_or_none()
    if existing:
        return existing

    source_key = _source_key(values)
    if source_key:
        source_name, source_job_id = source_key
        existing = db.execute(
            select(Job).where(Job.source_name == source_name, Job.source_job_id == source_job_id)
        ).scalar_one_or_none()
        if existing:
            return existing

    source_url = values.get("source_url")
    if source_url:
        existing = db.execute(select(Job).where(Job.source_url == source_url).limit(1)).scalar_one_or_none()
        if existing:
            return existing

    return None


def _update_existing_job(db: Session, existing: Job, values: dict) -> None:
    protected_fields = {"id"}

    if _content_hash_owned_by_other(db, existing.id, values["content_hash"]):
        protected_fields.add("content_hash")

    source_key = _source_key(values)
    if source_key and _source_key_owned_by_other(db, existing.id, source_key):
        protected_fields.update({"source_name", "source_job_id"})

    for key, value in values.items():
        if key in protected_fields:
            continue
        setattr(existing, key, value)

    existing.last_seen_at = func.now()


def _content_hash_owned_by_other(db: Session, job_id: str, content_hash: str) -> bool:
    owner_id = db.execute(
        select(Job.id).where(Job.content_hash == content_hash, Job.id != job_id)
    ).scalar_one_or_none()
    return bool(owner_id)


def _source_key_owned_by_other(db: Session, job_id: str, source_key: tuple[str, str]) -> bool:
    source_name, source_job_id = source_key
    owner_id = db.execute(
        select(Job.id).where(
            Job.source_name == source_name,
            Job.source_job_id == source_job_id,
            Job.id != job_id,
        )
    ).scalar_one_or_none()
    return bool(owner_id)


def _compat_normalize(job: dict) -> dict:
    from app.etl.normalizers.jobs import normalize_job_payload

    return normalize_job_payload(job)

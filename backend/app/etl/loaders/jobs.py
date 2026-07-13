"""Load normalized staged job records into core Postgres tables."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.postgres import upsert_company
from app.db.schema import Job
from app.utils.deduplication import generate_content_hash
from app.utils.text_processing import extract_relevant_keywords, extract_skills_from_text
from app.utils.job_quality import (
    COMPLETE_JD_POLICY_VERSION,
    complete_job_description_reason,
    has_complete_job_description,
)


def load_normalized_jobs(db: Session, jobs: list[dict]) -> int:
    count = 0
    seen_ids: set[str] = set()
    seen_hashes: set[str] = set()
    seen_source_keys: set[tuple[str, str]] = set()

    for job in jobs:
        normalized = job if "company_name" in job else _compat_normalize(job)
        if not normalized.get("id") or not normalized.get("title") or not normalized.get("company_name"):
            continue

        # Locked publication boundary. Some official/API ingestion paths pass
        # pre-normalized dictionaries directly to this loader, so enforcing the
        # full-JD contract only in normalize_job_payload was bypassable.
        normalized = _enforce_complete_jd_policy(normalized)

        company = upsert_company(db, normalized["company_name"])
        extra_metadata = dict(normalized.get("extra_metadata") or {})
        extra_metadata["jd_analysis"] = _jd_analysis(
            title=normalized.get("title") or "",
            description=normalized.get("description") or "",
        )
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
            "extra_metadata": extra_metadata,
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


def _jd_analysis(*, title: str, description: str) -> dict:
    jd_text = f"{title}\n{description or ''}".strip()
    skills = list(dict.fromkeys(extract_skills_from_text(jd_text)))
    keywords = [
        kw for kw in extract_relevant_keywords(jd_text, top_n=50)
        if kw not in skills
    ]
    return {
        "schema": "placeup_jd_analysis_v1",
        "description_hash": generate_content_hash(title or "", "", description or ""),
        "skills": skills[:80],
        "keywords": keywords[:80],
        "word_count": len((description or "").split()),
    }


def _source_key(values: dict) -> tuple[str, str] | None:
    source_name = values.get("source_name")
    source_job_id = values.get("source_job_id")
    if not source_name or not source_job_id:
        return None
    return (source_name, source_job_id)


def _validation_errors(normalized: dict) -> list[str]:
    metadata = normalized.get("extra_metadata") or {}
    if not isinstance(metadata, dict):
        return []
    errors = metadata.get("validation_errors") or []
    return [str(error) for error in errors if str(error).strip()] if isinstance(errors, list) else []


def _enforce_complete_jd_policy(normalized: dict) -> dict:
    row = dict(normalized)
    metadata = dict(row.get("extra_metadata") or {})
    errors = [
        error for error in _validation_errors(row)
        if not error.lower().startswith(("thin or missing job description", "incomplete job description:"))
    ]
    reason = complete_job_description_reason(row.get("description") or "")
    metadata["jd_completeness_policy"] = COMPLETE_JD_POLICY_VERSION
    metadata["jd_complete"] = reason is None
    if reason:
        errors.append(f"incomplete job description: {reason}")
        row["status"] = "quarantined"
    elif not errors and str(row.get("status") or "active").lower() == "quarantined":
        row["status"] = "active"
    if errors:
        metadata["validation_errors"] = list(dict.fromkeys(errors))
    else:
        metadata.pop("validation_errors", None)
    row["extra_metadata"] = metadata
    return row


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

    # Never let a re-scrape clobber a richer stored description with a thin
    # snippet. Boards frequently return truncated summaries on refresh while
    # the stored row already holds the FULL JD hydrated from the company
    # page — blind overwrite here was why complete position info kept
    # disappearing after every scrape/update cycle.
    incoming_desc = str(values.get("description") or "").strip()
    existing_desc = str(existing.description or "").strip()
    existing_meta = existing.extra_metadata if isinstance(existing.extra_metadata, dict) else {}
    existing_has_complete_jd = has_complete_job_description(existing_desc)
    incoming_has_complete_jd = has_complete_job_description(incoming_desc)
    keep_existing_description = bool(existing_desc) and (
        len(incoming_desc) < 200
        or (existing_meta.get("description_hydrated") and len(incoming_desc) <= len(existing_desc))
        or len(incoming_desc) < int(len(existing_desc) * 0.6)
    )
    if keep_existing_description:
        protected_fields.add("description")
        merged_meta = dict(values.get("extra_metadata") or {})
        for k in (
            "description_hydrated",
            "description_hydrated_from",
            "description_extractor",
            "description_html",
            "jd_analysis",
        ):
            if k in existing_meta:
                merged_meta[k] = existing_meta[k]
        values = dict(values)
        values["extra_metadata"] = merged_meta
    # A partial refresh must never quarantine or downgrade a previously
    # complete active posting. Preserve the full JD and its publication state.
    if existing_has_complete_jd and not incoming_has_complete_jd:
        protected_fields.add("status")
        protected_fields.add("description")
        merged_meta = dict(values.get("extra_metadata") or {})
        remaining_errors = [
            error for error in (merged_meta.get("validation_errors") or [])
            if not str(error).lower().startswith(("thin or missing job description", "incomplete job description:"))
        ]
        if remaining_errors:
            merged_meta["validation_errors"] = remaining_errors
        else:
            merged_meta.pop("validation_errors", None)
        merged_meta["jd_complete"] = True
        merged_meta["jd_completeness_policy"] = COMPLETE_JD_POLICY_VERSION
        for key in ("description_hydrated", "description_hydrated_from", "description_extractor", "description_html"):
            if key in existing_meta:
                merged_meta[key] = existing_meta[key]
        values = dict(values)
        values["extra_metadata"] = merged_meta

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

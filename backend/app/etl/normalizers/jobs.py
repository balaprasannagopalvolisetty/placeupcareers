"""Normalize existing JobPost payloads into the central jobs schema."""

from __future__ import annotations

from app.db.postgres import normalize_text


def normalize_job_payload(job: dict) -> dict:
    salary = job.get("salary") or {}
    visa = job.get("visa") or {}
    source = job.get("source") or "unknown"
    category = job.get("category") or "Other"

    if hasattr(source, "value"):
        source = source.value
    if hasattr(category, "value"):
        category = category.value

    return {
        "id": job.get("id"),
        "company_name": job.get("company") or "",
        "title": job.get("title") or "",
        "normalized_title": normalize_text(job.get("title") or ""),
        "location": job.get("location") or "",
        "country": infer_country(job.get("location") or ""),
        "category": category,
        "source_name": source,
        "source_job_id": job.get("source_job_id") or None,
        "source_url": job.get("job_url") or job.get("job_url_direct") or "",
        "description": job.get("description") or "",
        "employment_type": job.get("job_type") or "",
        "remote_type": "remote" if job.get("is_remote") else "",
        "salary_min": salary.get("min_salary") if isinstance(salary, dict) else None,
        "salary_max": salary.get("max_salary") if isinstance(salary, dict) else None,
        "currency": salary.get("currency") if isinstance(salary, dict) else "USD",
        "visa_opt": bool(visa.get("visa_opt")) if isinstance(visa, dict) else False,
        "visa_stem_opt": bool(visa.get("visa_stem_opt")) if isinstance(visa, dict) else False,
        "visa_h1b": bool(visa.get("visa_h1b")) if isinstance(visa, dict) else False,
        "h1b_verified": bool(visa.get("h1b_verified")) if isinstance(visa, dict) else False,
        "visa_score": int(visa.get("visa_score") or 0) if isinstance(visa, dict) else 0,
        "content_hash": job.get("content_hash") or "",
        "status": job.get("status") or "active",
        "posted_at": job.get("posted_at"),
        "extra_metadata": job.get("extra_metadata") or {},
    }


def infer_country(location: str) -> str:
    lowered = location.lower()
    if "canada" in lowered or any(token in lowered for token in (" toronto", " vancouver", " ontario", " bc")):
        return "CA"
    return "US"

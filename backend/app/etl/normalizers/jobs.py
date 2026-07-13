"""Normalize existing JobPost payloads into the central jobs schema."""

from __future__ import annotations

from app.db.postgres import normalize_text
from app.utils.job_quality import (
    clean_job_company,
    clean_job_description,
    COMPLETE_JD_POLICY_VERSION,
    complete_job_description_reason,
    infer_posted_at,
    is_probably_fake_or_scam_job,
    is_probably_job_search_page,
    job_description_text,
    sanitize_job_description_html,
)
from app.services.global_visa_rules import classify_global_visa, resolve_country


def normalize_job_payload(job: dict) -> dict:
    salary = job.get("salary") or {}
    visa = job.get("visa") or {}
    source = job.get("source") or "unknown"
    category = job.get("category") or "Other"

    if hasattr(source, "value"):
        source = source.value
    if hasattr(category, "value"):
        category = category.value
    raw_description = job.get("description") or ""
    title = job.get("title") or ""
    company_name = clean_job_company(job.get("company") or "", raw_description, title)
    posted_at = infer_posted_at(job.get("posted_at"), raw_description)
    cleaned_description = clean_job_description(raw_description)
    description_html = sanitize_job_description_html(cleaned_description)
    description = job_description_text(cleaned_description)
    inferred_country = (
        job.get("visa_country")
        or (visa.get("visa_country") if isinstance(visa, dict) else None)
        or (job.get("extra_metadata") or {}).get("visa_country")
        or infer_country(job.get("location") or "")
    )
    sponsor_verified = bool(
        visa.get("h1b_verified") if isinstance(visa, dict) else False
    ) or bool(visa.get("sponsor_verified") if isinstance(visa, dict) else False) or bool((job.get("extra_metadata") or {}).get("sponsor_verified"))
    sponsor_source = (visa.get("sponsor_source") if isinstance(visa, dict) else None) or (job.get("extra_metadata") or {}).get("sponsor_source")
    global_visa = classify_global_visa(
        title=title,
        company=company_name,
        description=description,
        location=job.get("location") or "",
        country_code=inferred_country,
        sponsor_verified=sponsor_verified,
        sponsor_source=sponsor_source,
    )
    validation_errors = []
    if is_probably_job_search_page(title, job.get("company") or "", raw_description, source):
        validation_errors.append("search/category page, not a job posting")
        company_name = ""
    if is_probably_fake_or_scam_job(title, company_name or job.get("company") or "", description, job.get("job_url") or job.get("job_url_direct") or ""):
        validation_errors.append("high-confidence fake/scam or non-posting artifact")
    jd_error = complete_job_description_reason(description)
    if jd_error:
        validation_errors.append(f"incomplete job description: {jd_error}")
    if not str(job.get("job_url") or job.get("job_url_direct") or "").strip():
        validation_errors.append("missing apply URL")
    if not str(job.get("location") or "").strip():
        validation_errors.append("missing location")

    salary_min = _positive_salary(salary.get("min_salary")) if isinstance(salary, dict) else None
    salary_max = _positive_salary(salary.get("max_salary")) if isinstance(salary, dict) else None
    if salary_min is not None and salary_max is not None and salary_min > salary_max:
        salary_min, salary_max = salary_max, salary_min
    metadata = (job.get("extra_metadata") or {}) | {
        "visa_country": global_visa["country_code"],
        "visa_country_name": global_visa["country_name"],
        "visa_programs": global_visa["visa_programs"],
        "visa_program_names": global_visa["visa_program_names"],
        "sponsor_verified": global_visa["sponsor_verified"],
        "sponsor_source": global_visa["sponsor_source"],
        "english_friendly": global_visa["english_friendly"],
        "jd_completeness_policy": COMPLETE_JD_POLICY_VERSION,
        "jd_complete": jd_error is None,
    }
    if description_html:
        metadata["description_html"] = description_html
    if validation_errors:
        metadata["validation_errors"] = validation_errors

    return {
        "id": job.get("id"),
        "company_name": company_name,
        "title": title,
        "normalized_title": normalize_text(title),
        "location": job.get("location") or "",
        "country": global_visa["country_code"],
        "category": category,
        "source_name": source,
        "source_job_id": job.get("source_job_id") or None,
        "source_url": job.get("job_url") or job.get("job_url_direct") or "",
        "description": description,
        "employment_type": job.get("job_type") or "",
        "remote_type": "remote" if job.get("is_remote") else "",
        "salary_min": salary_min,
        "salary_max": salary_max,
        "currency": salary.get("currency") if isinstance(salary, dict) else "USD",
        "visa_opt": bool(visa.get("visa_opt")) if isinstance(visa, dict) else False,
        "visa_stem_opt": bool(visa.get("visa_stem_opt")) if isinstance(visa, dict) else False,
        "visa_h1b": bool(visa.get("visa_h1b")) if isinstance(visa, dict) else False,
        "h1b_verified": bool(visa.get("h1b_verified")) if isinstance(visa, dict) else False,
        "visa_score": max(
            int(visa.get("visa_score") or 0) if isinstance(visa, dict) else 0,
            int(global_visa.get("score") or 0),
        ),
        "content_hash": job.get("content_hash") or "",
        "status": "quarantined" if validation_errors else (job.get("status") or "active"),
        "posted_at": posted_at,
        "extra_metadata": metadata,
    }


def _positive_salary(value: object) -> float | None:
    try:
        amount = float(value) if value is not None else 0.0
    except (TypeError, ValueError):
        return None
    return amount if amount > 0 else None


def infer_country(location: str) -> str:
    # Leave the country UNKNOWN when the location can't be resolved instead of
    # guessing "US". A blanket US default mislabeled non-US/remote postings as
    # US; an empty country still passes the target-country prefilter (which
    # admits NULL/empty for remote/unspecified roles) and shows in broad views.
    return resolve_country(location) or ""

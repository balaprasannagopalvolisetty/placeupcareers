"""
PlaceUp Career — Jobs API Routes
Endpoints for listing, filtering, and scraping job postings.
"""

import logging
import math
from fastapi import APIRouter, Body, Depends, HTTPException, Query
from typing import Any, Optional

from app.db import user_store
from app.dependencies import get_db
from app.job_taxonomy import categorize, to_payload
from app.models.job import (
    JobPost, JobFilter, JobListResponse, JobStats,
    ScrapeRequest, ScrapeResult, JobSource, JobCategory,
)
from app.security import optional_user_id
from app.services.job_exporter import export_jobs
from app.utils.terminal_table import render_table

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/jobs", tags=["Jobs"])


def _score_job_against_resume(resume_text: str, job_text: str) -> int:
    """
    Lightweight per-job ATS-style match score (0-100).

    We don't want to fire the LLM on every list call, so we do a
    keyword-overlap scoring pass that's fast enough to compute for
    every job in the page on each request.
    """
    if not resume_text or not job_text:
        return 0
    try:
        from app.utils.text_processing import (
            extract_keywords, extract_skills_from_text, compute_keyword_overlap,
        )
        jd_kw = list(set(extract_keywords(job_text, top_n=40) + extract_skills_from_text(job_text)))
        r_kw = list(set(extract_keywords(resume_text, top_n=60) + extract_skills_from_text(resume_text)))
        if not jd_kw:
            return 0
        _, _, pct = compute_keyword_overlap(r_kw, jd_kw)
        return int(round(min(100, max(0, pct))))
    except Exception:
        return 0


async def _active_resume_text(user_id: Optional[str]) -> Optional[str]:
    """Return the parsed text of the user's active resume, if any."""
    if not user_id:
        return None
    resumes = user_store.list_resumes(user_id)
    active = next((r for r in resumes if r.get("active")), None) or (resumes[0] if resumes else None)
    if not active:
        return None
    path = active.get("storage_path")
    if not path:
        return None
    try:
        from app.services.resume_parser import parse_resume_file
        with open(path, "rb") as fh:
            content = fh.read()
        parsed = await parse_resume_file(content, active.get("name") or "resume.pdf")
        return parsed.get("text") or None
    except Exception:
        return None


@router.get("/taxonomy")
async def get_job_taxonomy():
    """Return the full category/role taxonomy for the Jobs page filter UI."""
    return to_payload()


@router.get("")  # response_model dropped so taxonomy_category / role survive
async def list_jobs(
    search: Optional[str] = Query(None, description="Search jobs by title, company, or description"),
    location: Optional[str] = Query(None, description="Filter by location"),
    category: Optional[str] = Query(None, description="Filter by category"),
    source: Optional[str] = Query(None, description="Filter by source"),
    visa_only: bool = Query(False, description="Only show visa-friendly jobs"),
    min_salary: Optional[float] = Query(None, description="Minimum salary filter"),
    job_type: Optional[str] = Query(None, description="Full-time, Part-time, Contract"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Results per page"),
    role: Optional[str] = Query(None, description="Filter by taxonomy role name"),
    entry_level: bool = Query(True, description="Prioritize 0-5 yr roles (default true)"),
    db=Depends(get_db),
    user_id: Optional[str] = Depends(optional_user_id),
):
    """List job postings with filtering, pagination, and per-user ATS scores.

    When a JWT is supplied, each job is scored against the caller's active
    resume so the UI can sort/show match percentages without a second call.
    """
    filters = {}
    if search:
        filters["search"] = search
    if location:
        filters["location"] = location
    # NOTE: `category` (taxonomy name) and `role` (taxonomy role) are applied
    # post-fetch via in-memory filtering further down, since the DB column
    # uses the legacy JobCategory enum which doesn't match our taxonomy names.
    if source:
        filters["source"] = source
    if visa_only:
        filters["visa_only"] = True

    offset = (page - 1) * page_size

    # When a taxonomy filter is in use, fetch a wider page so post-filter
    # leaves us with enough rows.
    fetch_limit = page_size * 5 if (category or role) else page_size
    fetch_offset = 0 if (category or role) else offset

    try:
        jobs = await db.get_jobs(filters=filters, limit=fetch_limit, offset=fetch_offset)
        total = await db.count_jobs(filters=filters)
        total_pages = math.ceil(total / page_size) if total > 0 else 1

        # Tag each job with taxonomy category + role under sibling fields so we
        # don't collide with JobPost.category (which is a strict Enum).
        decorated: list[dict] = []
        for j in jobs:
            cat, rname = categorize(j.get("title") or "")
            j = dict(j)
            j["taxonomy_category"] = cat
            j["role"] = rname
            decorated.append(j)
        if role:
            role_l = role.strip().lower()
            decorated = [j for j in decorated if (j.get("role") or "").lower() == role_l]
            total = len(decorated)
            total_pages = max(1, math.ceil(total / page_size))

        # Likewise, when the user filters by category they pass the
        # taxonomy name ("Technology & Engineering"); resolve that here
        # since the DB column uses the legacy enum.
        if category:
            cat_l = category.strip().lower()
            decorated = [j for j in decorated if (j.get("taxonomy_category") or "").lower() == cat_l]
            total = len(decorated)
            total_pages = max(1, math.ceil(total / page_size))

        # Per-user ATS scoring against the active resume.
        resume_text = await _active_resume_text(user_id)
        for j in decorated:
            jd = j.get("description") or ""
            jt = j.get("title") or ""
            if resume_text and (jd or jt):
                j["match_score"] = _score_job_against_resume(resume_text, f"{jt}\n{jd}")

        # 0-5 yr prioritization. Tags come from the scraper (extra_metadata).
        if entry_level:
            def _entry_score(j: dict) -> tuple:
                meta = j.get("extra_metadata") or {}
                if not isinstance(meta, dict):
                    meta = {}
                ymin = meta.get("years_min")
                # Bucket: 0-5 yr roles (incl. unknown) come first.
                bucket = 0 if (ymin is None or 0 <= int(ymin) <= 5) else 1
                # Inside the bucket, sort by descending ATS match score.
                match = -(j.get("match_score") or 0)
                return (bucket, match)
            decorated.sort(key=_entry_score)

        # Convert to JobPost models for the response. Stash the taxonomy
        # extras and re-attach them post-validation so the strict JobPost
        # enum doesn't reject "Technology & Engineering" etc.
        job_posts: list = []
        for job_data in decorated:
            tax_cat = job_data.pop("taxonomy_category", None)
            tax_role = job_data.pop("role", None)
            try:
                model = JobPost(**job_data)
                payload = model.model_dump(mode="json")
            except Exception:
                payload = dict(job_data)
            if tax_cat is not None:
                payload["taxonomy_category"] = tax_cat
            if tax_role is not None:
                payload["role"] = tax_role
            job_posts.append(payload)

        # Return a plain dict so taxonomy_category / role survive — FastAPI's
        # default jsonable_encoder doesn't drop unknown keys.
        return {
            "jobs": job_posts,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
            "filters_applied": {
                **filters,
                **({"role": role} if role else {}),
                **({"category": category} if category else {}),
            },
        }
    except Exception as e:
        logger.error(f"Error listing jobs: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats", response_model=JobStats)
async def get_job_stats(db=Depends(get_db)):
    """Get aggregated job statistics for dashboard.

    Returns total counts, breakdowns by category/source/visa,
    and recent activity metrics.
    """
    try:
        total = await db.count_jobs()

        # Get category breakdown
        by_category = {}
        for cat in JobCategory:
            count = await db.count_jobs({"category": cat.value})
            if count > 0:
                by_category[cat.value] = count

        return JobStats(
            total_jobs=total,
            by_category=by_category,
        )
    except Exception as e:
        logger.error(f"Error getting job stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/scrape", response_model=ScrapeResult)
async def trigger_scrape(
    request: Optional[ScrapeRequest] = Body(default=None),
    db=Depends(get_db),
):
    """Trigger a manual job scraping cycle.

    Runs all configured scraping sources in parallel,
    deduplicates results, classifies for visa compatibility,
    and stores new jobs in the database.

    This endpoint is typically called by:
    - Admin dashboard
    - Cloud Scheduler cron job (every 2 hours)
    """
    from app.services.job_scraper import run_scrape_cycle

    try:
        # Get existing hashes for deduplication
        existing_hashes = await db.get_existing_hashes()

        # Run scrape cycle
        result, jobs = await run_scrape_cycle(
            request=request or ScrapeRequest(),
            existing_hashes=existing_hashes,
        )

        # Store new jobs in database
        if jobs:
            job_dicts = [job.model_dump(mode="json") for job in jobs]
            stored = await db.upsert_jobs_batch(job_dicts)
            logger.info(f"Stored {stored} new jobs in database")

            artifacts = export_jobs(job_dicts)
            if artifacts:
                logger.info(f"Exported jobs: {artifacts}")
                export_rows = [{"artifact": name, "path": path} for name, path in artifacts.items()]
                logger.info("Export artifacts:\n%s", render_table(export_rows, headers=["artifact", "path"]))

        return result

    except Exception as e:
        logger.error(f"Scrape cycle failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/export")
async def export_all_jobs(db=Depends(get_db)):
    """Export all jobs currently in DB to a single rolling CSV/XLSX."""
    try:
        jobs = await db.get_jobs(limit=100000, offset=0)
        artifacts = export_jobs(jobs)
        return {"exported_rows": len(jobs), "artifacts": artifacts}
    except Exception as e:
        logger.error(f"Job export failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{job_id}")
async def get_job(job_id: str, db=Depends(get_db)):
    """Get a single job posting by ID."""
    job = await db.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.get("/detail/{job_id}")
async def get_job_detail(
    job_id: str,
    db=Depends(get_db),
    user_id: Optional[str] = Depends(optional_user_id),
):
    """Job detail with taxonomy, contacts, and per-active-resume ATS score."""
    job = await db.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    title = job.get("title") or ""
    description = job.get("description") or ""
    cat, rname = categorize(title)
    payload = dict(job)
    payload["taxonomy_category"] = cat
    payload["role"] = rname

    resume_text = await _active_resume_text(user_id)
    if resume_text:
        combined = title + "\n" + description
        payload["match_score"] = _score_job_against_resume(resume_text, combined)

    try:
        contacts = await db.get_contacts(job_id=job_id, limit=3)
    except Exception:
        contacts = []
    payload["contacts"] = contacts
    return payload

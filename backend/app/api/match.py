"""
PlaceUp Career — Match Scoring API Routes
Endpoints for resume-to-job match scoring.
"""

import logging
import time
from fastapi import APIRouter, Depends, File, Form, UploadFile, HTTPException
from typing import Optional

from app.dependencies import get_db
from app.models.match import MatchResponse, BatchMatchResult

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/match", tags=["Match Scoring"])


@router.post("/score", response_model=MatchResponse)
async def match_resume_to_job(
    file: UploadFile = File(..., description="Resume file (PDF or DOCX)"),
    job_id: str = Form(..., description="Job posting ID to match against"),
    job_description: Optional[str] = Form(None, description="Override JD (optional)"),
    job_title: Optional[str] = Form(None, description="Job title (optional)"),
    db=Depends(get_db),
):
    """Score how well a resume matches a specific job posting.

    Uses a hybrid scoring algorithm:
    1. TF-IDF cosine similarity (30% weight)
    2. Keyword overlap analysis (30% weight)
    3. LLM semantic relevance scoring (40% weight)

    The result includes the composite score, individual dimension scores,
    matched/missing keywords, and actionable improvement suggestions.
    """
    start_time = time.time()

    try:
        # Get job data if no description override
        jd_text = job_description
        jt = job_title or ""
        company = ""

        if not jd_text:
            job = await db.get_job(job_id)
            if not job:
                raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
            jd_text = job.get("description", "")
            jt = jt or job.get("title", "")
            company = job.get("company", "")

        if not jd_text or len(jd_text.strip()) < 50:
            raise HTTPException(
                status_code=400,
                detail="Job description is too short for meaningful matching."
            )

        # Parse resume
        content = await file.read()
        filename = file.filename or "resume.pdf"

        from app.services.resume_parser import parse_resume_file
        parsed_file = await parse_resume_file(content, filename)
        resume_text = parsed_file["text"]

        if not resume_text or len(resume_text.strip()) < 50:
            raise HTTPException(status_code=400, detail="Could not extract text from resume.")

        # Get visa badges if job exists in DB
        visa_badges = None
        job_data = await db.get_job(job_id) if not job_description else None
        if job_data and job_data.get("visa"):
            from app.models.job import VisaBadges
            try:
                visa_badges = VisaBadges(**job_data["visa"])
            except Exception:
                pass

        # Compute match score
        from app.services.match_engine import compute_match_score
        match_result = await compute_match_score(
            resume_text=resume_text,
            job_description=jd_text,
            job_title=jt,
            visa_badges=visa_badges,
        )

        elapsed = (time.time() - start_time) * 1000

        return MatchResponse(
            success=True,
            match=match_result,
            job_id=job_id,
            job_title=jt,
            company=company,
            processing_time_ms=round(elapsed, 1),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Match scoring failed: {e}")
        raise HTTPException(status_code=500, detail=f"Match scoring failed: {str(e)}")


@router.post("/batch", response_model=BatchMatchResult)
async def batch_match(
    file: UploadFile = File(..., description="Resume file (PDF or DOCX)"),
    job_ids: str = Form(..., description="Comma-separated job IDs (max 20)"),
    db=Depends(get_db),
):
    """Score a resume against multiple jobs and return ranked results.

    Accepts a resume file and a comma-separated list of job IDs.
    Returns a ranked list of matches sorted by match score (descending).

    Maximum 20 jobs per batch to prevent timeout.
    """
    start_time = time.time()

    try:
        # Parse job IDs
        ids = [id.strip() for id in job_ids.split(",") if id.strip()]
        if len(ids) > 20:
            raise HTTPException(status_code=400, detail="Maximum 20 jobs per batch")
        if not ids:
            raise HTTPException(status_code=400, detail="No job IDs provided")

        # Parse resume
        content = await file.read()
        filename = file.filename or "resume.pdf"

        from app.services.resume_parser import parse_resume_file
        parsed_file = await parse_resume_file(content, filename)
        resume_text = parsed_file["text"]

        if not resume_text or len(resume_text.strip()) < 50:
            raise HTTPException(status_code=400, detail="Could not extract text from resume.")

        # Score against each job
        from app.services.match_engine import compute_match_score
        results = []

        for job_id in ids:
            try:
                job = await db.get_job(job_id)
                if not job:
                    continue

                jd_text = job.get("description", "")
                if len(jd_text.strip()) < 50:
                    continue

                match_result = await compute_match_score(
                    resume_text=resume_text,
                    job_description=jd_text,
                    job_title=job.get("title", ""),
                )

                results.append({
                    "job_id": job_id,
                    "job_title": job.get("title", ""),
                    "company": job.get("company", ""),
                    "match_score": match_result.overall_match_score,
                    "recommendation": match_result.recommendation,
                })
            except Exception as e:
                logger.debug(f"Batch match: Skipping {job_id}: {e}")
                continue

        # Sort by match score descending
        results.sort(key=lambda x: x["match_score"], reverse=True)

        elapsed = (time.time() - start_time) * 1000

        return BatchMatchResult(
            results=results,
            total_matched=len(results),
            processing_time_ms=round(elapsed, 1),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Batch match failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

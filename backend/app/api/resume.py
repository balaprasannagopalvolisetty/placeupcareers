"""
PlaceUp Career — Resume API Routes
Endpoints for resume parsing and ATS scoring.
"""

import logging
import time
from fastapi import APIRouter, File, Form, UploadFile, HTTPException
from typing import Optional

from app.models.resume import ResumeParseResponse, ResumeScoreResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/resume", tags=["Resume & ATS"])

@router.post("/parse", response_model=ResumeParseResponse)
async def parse_resume(
    file: UploadFile = File(..., description="Resume file (PDF or DOCX)"),
):
    """Parse a resume file into structured data.

    Accepts PDF or DOCX files. Extracts text, then uses LLM
    to parse into structured fields (skills, experience, education).

    Returns:
        Structured resume data with skills, experience, education, etc.
    """
    start_time = time.time()

    # Validate file type
    allowed_types = {"application/pdf", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}
    filename = file.filename or "resume.pdf"
    ext = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""

    if ext not in ("pdf", "docx", "doc"):
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: .{ext}. Please upload a PDF or DOCX file."
        )

    try:
        # Read file content
        content = await file.read()
        if len(content) > 10 * 1024 * 1024:  # 10MB limit
            raise HTTPException(status_code=400, detail="File too large. Maximum size is 10MB.")

        # Parse resume text
        from app.services.resume_parser import parse_resume_file
        parsed_file = await parse_resume_file(content, filename)

        resume_text = parsed_file["text"]
        if not resume_text or len(resume_text.strip()) < 50:
            raise HTTPException(
                status_code=400,
                detail="Could not extract meaningful text from the file. Please check the file format."
            )

        # Parse with LLM for structured data
        from app.services.ats_scorer import parse_resume_with_llm
        parsed_resume = await parse_resume_with_llm(resume_text)

        elapsed = (time.time() - start_time) * 1000

        return ResumeParseResponse(
            success=True,
            resume=parsed_resume,
            word_count=parsed_file["word_count"],
            page_count=parsed_file["page_count"],
            parse_time_ms=round(elapsed, 1),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Resume parsing failed: {e}")
        raise HTTPException(status_code=500, detail=f"Resume parsing failed: {str(e)}")


@router.get("/list")
async def list_resumes():
    """Legacy unauthenticated endpoint kept for compatibility."""
    return []


@router.post("/upload")
async def upload_resume(file: UploadFile = File(..., description="Resume file (PDF or DOCX)")):
    """Legacy unauthenticated endpoint kept for compatibility."""
    raise HTTPException(status_code=410, detail="Use /api/user/resumes/upload")


@router.post("/score", response_model=ResumeScoreResponse)
async def score_resume(
    file: UploadFile = File(..., description="Resume file (PDF or DOCX)"),
    job_description: str = Form(..., description="Full job description text"),
    job_title: Optional[str] = Form(None, description="Job title"),
    company: Optional[str] = Form(None, description="Company name"),
):
    """Score a resume against a job description using AI-powered ATS analysis.

    Accepts a resume file and job description text. Returns:
    - Overall ATS score (0-100)
    - Category scores (skills, experience, education, etc.)
    - Keyword analysis (strong, missing, additional keywords)
    - Specific improvement suggestions

    This is the primary endpoint for the ATS scoring feature.
    """
    start_time = time.time()

    # Validate file
    filename = file.filename or "resume.pdf"
    ext = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    if ext not in ("pdf", "docx", "doc"):
        raise HTTPException(status_code=400, detail=f"Unsupported file type: .{ext}")

    if not job_description or len(job_description.strip()) < 50:
        raise HTTPException(
            status_code=400,
            detail="Job description is too short. Please provide a complete job description."
        )

    try:
        # Read and parse resume
        content = await file.read()
        if len(content) > 10 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="File too large. Maximum size is 10MB.")

        from app.services.resume_parser import parse_resume_file
        parsed_file = await parse_resume_file(content, filename)
        resume_text = parsed_file["text"]

        if not resume_text or len(resume_text.strip()) < 50:
            raise HTTPException(status_code=400, detail="Could not extract text from resume file.")

        # Parse resume structure
        from app.services.ats_scorer import parse_resume_with_llm, score_resume_against_job
        parsed_resume = await parse_resume_with_llm(resume_text)

        # Score against job description
        ats_result = await score_resume_against_job(
            resume_text=resume_text,
            job_description=job_description,
            job_title=job_title or "",
            company=company or "",
        )

        elapsed = (time.time() - start_time) * 1000

        return ResumeScoreResponse(
            success=True,
            ats_result=ats_result,
            parsed_resume=parsed_resume,
            job_title=job_title or "",
            company=company or "",
            processing_time_ms=round(elapsed, 1),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"ATS scoring failed: {e}")
        raise HTTPException(status_code=500, detail=f"ATS scoring failed: {str(e)}")


@router.post("/keywords")
async def extract_keywords(
    file: UploadFile = File(..., description="Resume file (PDF or DOCX)"),
    job_description: str = Form(..., description="Job description text"),
):
    """Extract and compare keywords between resume and job description.

    Returns matched keywords, missing keywords with impact levels,
    and keyword density score. Useful for quick keyword gap analysis
    without full ATS scoring.
    """
    try:
        # Read and parse resume
        content = await file.read()
        filename = file.filename or "resume.pdf"

        from app.services.resume_parser import parse_resume_file
        parsed_file = await parse_resume_file(content, filename)
        resume_text = parsed_file["text"]

        from app.utils.text_processing import (
            extract_keywords as extract_kws,
            extract_skills_from_text,
            compute_keyword_overlap,
        )

        # Extract keywords from both documents
        jd_keywords = extract_kws(job_description, top_n=30)
        resume_keywords = extract_kws(resume_text, top_n=40)

        jd_skills = extract_skills_from_text(job_description)
        resume_skills = extract_skills_from_text(resume_text)

        # Combine and compare
        jd_all = list(set(jd_keywords + jd_skills))
        resume_all = list(set(resume_keywords + resume_skills))

        matched, missing, overlap_pct = compute_keyword_overlap(resume_all, jd_all)

        return {
            "matched_keywords": matched,
            "missing_keywords": missing,
            "additional_keywords": sorted(set(resume_all) - set(jd_all))[:10],
            "keyword_density_score": overlap_pct,
            "jd_skills_found": jd_skills,
            "resume_skills_found": resume_skills,
            "total_jd_keywords": len(jd_all),
            "total_resume_keywords": len(resume_all),
        }

    except Exception as e:
        logger.error(f"Keyword extraction failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

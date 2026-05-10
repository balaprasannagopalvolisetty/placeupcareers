"""
PlaceUp Career — ATS Scoring Service
AI-powered resume scoring using Instructor + Groq/OpenAI for structured LLM outputs.

Inspired by: github.com/sohamjyotimondal/resume_screener (Instructor pattern)
Provides multi-criteria ATS analysis with actionable feedback.
"""

import logging
import re
import time
from typing import Optional

from app.config import settings
from app.models.resume import (
    ParsedResume, ATSResult, SkillMatch, KeywordAnalysis, KeywordWithImpact,
)
from app.utils.text_processing import (
    extract_keywords, extract_skills_from_text,
    compute_keyword_overlap, truncate_text, clean_text,
)

logger = logging.getLogger(__name__)





async def parse_resume_with_llm(resume_text: str) -> ParsedResume:
    """Parse resume text into structured data.
    
    (Note: Switched to local NLP processing per requirements to avoid LLM costs)

    Args:
        resume_text: Raw text extracted from resume file

    Returns:
        ParsedResume with structured fields (skills, experience, etc.)
    """
    logger.info("Using local NLP for resume parsing")
    return _fallback_parse(resume_text)


async def score_resume_against_job(
    resume_text: str,
    job_description: str,
    job_title: str = "",
    company: str = "",
) -> ATSResult:
    """Score a resume against a job description using local NLP rules.

    (Note: Switched to local NLP processing per requirements to avoid LLM costs)

    Args:
        resume_text: Full resume text
        job_description: Full job description text
        job_title: Job title for context
        company: Company name for context

    Returns:
        ATSResult with comprehensive scoring and recommendations
    """
    logger.info("Using local TF-IDF/NLP for ATS scoring")
    return _fallback_score(resume_text, job_description)


def _enhance_keyword_analysis(resume_text: str, job_description: str) -> KeywordAnalysis:
    """Enhance LLM analysis with NLP-based keyword extraction.

    Uses TF-IDF keyword extraction and direct skill matching
    to provide more accurate keyword coverage metrics.

    Args:
        resume_text: Resume text
        job_description: Job description text

    Returns:
        KeywordAnalysis with strong/missing/additional keywords
    """
    # Extract keywords from both documents
    jd_keywords = extract_keywords(job_description, top_n=30)
    resume_keywords = extract_keywords(resume_text, top_n=40)

    # Also extract recognized technical skills
    jd_skills = extract_skills_from_text(job_description)
    resume_skills = extract_skills_from_text(resume_text)

    # Combine keywords and skills for comprehensive analysis
    jd_all = list(set(jd_keywords + jd_skills))
    resume_all = list(set(resume_keywords + resume_skills))

    matched, missing_list, density = compute_keyword_overlap(resume_all, jd_all)

    # Create KeywordWithImpact for missing keywords
    missing_with_impact = []
    for kw in missing_list[:15]:  # Top 15 missing keywords
        impact = "high" if kw in jd_skills else "medium"
        missing_with_impact.append(KeywordWithImpact(
            keyword=kw,
            impact=impact,
            category="technical" if kw in jd_skills else "general",
            suggestion=f"Consider adding '{kw}' to your skills or experience section",
        ))

    # Additional resume keywords not in JD
    additional = sorted(set(resume_all) - set(jd_all))

    return KeywordAnalysis(
        strong_keywords=matched,
        missing_keywords=missing_with_impact,
        additional_keywords=additional[:10],
        keyword_density_score=density,
    )


def _fallback_parse(resume_text: str) -> ParsedResume:
    """Fallback resume parsing without LLM (keyword extraction only).

    Used when LLM is unavailable or fails.
    """
    from app.models.resume import SkillEntry

    skills = extract_skills_from_text(resume_text)
    skill_entries = [SkillEntry(name=s, category="Technical") for s in skills]

    return ParsedResume(
        summary=resume_text[:500] if len(resume_text) > 500 else resume_text,
        skills=skill_entries,
    )


def _fallback_score(resume_text: str, job_description: str) -> ATSResult:
    """Fallback ATS scoring using keyword analysis only (no LLM).

    Provides a basic score based on keyword overlap when the LLM
    is unavailable or the API call fails.
    """
    keyword_analysis = _enhance_keyword_analysis(resume_text, job_description)
    density = keyword_analysis.keyword_density_score

    # Simple score based on keyword density
    overall = min(density * 1.2, 100)

    recommendation = "Strong Match" if overall >= 80 else \
                     "Potential Match" if overall >= 60 else \
                     "Weak Match" if overall >= 40 else "Not Recommended"

    return ATSResult(
        overall_score=round(overall, 1),
        recommendation=recommendation,
        skill_match=SkillMatch(
            matched_skills=keyword_analysis.strong_keywords,
            missing_skills=[kw.keyword for kw in keyword_analysis.missing_keywords],
            match_percentage=density,
        ),
        experience_score=50.0,  # Default when LLM unavailable
        education_score=50.0,
        projects_score=50.0,
        certifications_score=50.0,
        cultural_fit_score=50.0,
        keyword_analysis=keyword_analysis,
        strengths=["Keyword-only analysis (LLM unavailable)"],
        concerns=["Full AI analysis could not be performed"],
        improvement_suggestions=[kw.suggestion for kw in keyword_analysis.missing_keywords[:5]],
    )


def score_resume_quality(resume_text: str) -> float:
    """Compute a generic resume quality score for UI upload/ATS preview."""
    if not resume_text or len(resume_text.strip()) < 50:
        return 0.0

    cleaned = clean_text(resume_text)
    words = cleaned.split()
    word_count = len(words)
    skills = extract_skills_from_text(cleaned)
    keywords = extract_keywords(cleaned, top_n=40)

    sections = 0
    for section in ("experience", "education", "skills", "projects", "certifications", "summary", "contact", "work history"):
        if re.search(rf"\b{re.escape(section)}\b", cleaned.lower()):
            sections += 1

    score = 40.0
    score += min(25.0, len(skills) * 3.0)
    score += min(20.0, len(set(keywords)) * 0.5)
    score += min(15.0, sections * 3.0)
    score += min(20.0, max(0.0, min(word_count, 1200) - 200) / 50.0)
    return round(min(100.0, max(0.0, score)), 1)

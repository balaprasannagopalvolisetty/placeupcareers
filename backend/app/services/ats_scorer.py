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
    extract_relevant_keywords, extract_skills_from_text,
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
    combined_jd = "\n".join(part for part in [job_title, company, job_description] if part)
    return _fallback_score(resume_text, combined_jd)


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
    jd_keywords = extract_relevant_keywords(job_description, top_n=30)
    resume_keywords = extract_relevant_keywords(resume_text, top_n=40)

    # Also extract recognized technical skills
    jd_skills = extract_skills_from_text(job_description)
    resume_skills = extract_skills_from_text(resume_text)

    # Combine keywords and skills for comprehensive analysis
    jd_all = list(dict.fromkeys(jd_skills + jd_keywords))
    resume_all = list(dict.fromkeys(resume_skills + resume_keywords))

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
    jd_skills = extract_skills_from_text(job_description)
    resume_skills = extract_skills_from_text(resume_text)
    matched_skills, missing_skills, skill_pct = compute_keyword_overlap(resume_skills, jd_skills)

    resume_words = len(clean_text(resume_text).split())
    sections = 0
    for section in ("experience", "education", "skills", "projects", "certifications", "summary"):
        if re.search(rf"\b{re.escape(section)}\b", resume_text.lower()):
            sections += 1
    completeness_pct = min(100.0, sections * 16.7)
    length_pct = 100.0 if 350 <= resume_words <= 1200 else max(30.0, min(100.0, resume_words / 350 * 100))

    overall = (
        density * 0.45
        + skill_pct * 0.35
        + completeness_pct * 0.12
        + length_pct * 0.08
    )

    recommendation = "Strong Match" if overall >= 80 else \
                     "Potential Match" if overall >= 60 else \
                     "Weak Match" if overall >= 40 else "Not Recommended"

    from app.utils.text_processing import TECH_SKILLS

    # Derive strengths from matched skills
    tech_matched = [s for s in (matched_skills or keyword_analysis.strong_keywords) if s in TECH_SKILLS]
    general_matched = [s for s in keyword_analysis.strong_keywords if s not in TECH_SKILLS]
    strengths: list[str] = []
    if tech_matched:
        strengths.append(f"Technical skills present: {', '.join(tech_matched[:6])}")
    if general_matched:
        strengths.append(f"Keyword alignment: {', '.join(general_matched[:5])}")
    if completeness_pct >= 50:
        strengths.append(f"Resume covers {sections} of 6 key sections")
    if not strengths:
        strengths.append("Add more targeted skills and keywords to improve match")

    # Derive concerns from gaps
    top_missing = (missing_skills or [kw.keyword for kw in keyword_analysis.missing_keywords])[:5]
    concerns: list[str] = []
    if top_missing:
        concerns.append(f"Missing skills/keywords: {', '.join(top_missing)}")
    if sections < 3:
        concerns.append("Resume is missing standard sections (experience, education, skills)")
    if resume_words < 200:
        concerns.append("Resume appears too short — add more detail to experience entries")

    return ATSResult(
        overall_score=round(overall, 1),
        recommendation=recommendation,
        skill_match=SkillMatch(
            matched_skills=matched_skills or keyword_analysis.strong_keywords,
            missing_skills=missing_skills or [kw.keyword for kw in keyword_analysis.missing_keywords],
            match_percentage=round(skill_pct or density, 1),
        ),
        experience_score=round(min(100.0, completeness_pct + 20), 1),
        education_score=100.0 if re.search(r"\beducation\b", resume_text.lower()) else 45.0,
        projects_score=100.0 if re.search(r"\b(project|projects)\b", resume_text.lower()) else 45.0,
        certifications_score=100.0 if re.search(r"\b(certification|certifications)\b", resume_text.lower()) else 45.0,
        cultural_fit_score=round(min(100.0, (density + skill_pct) / 2), 1),
        keyword_analysis=keyword_analysis,
        strengths=strengths,
        concerns=concerns,
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
    keywords = extract_relevant_keywords(cleaned, top_n=40)

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

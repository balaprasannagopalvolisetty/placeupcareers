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
    """Strict deterministic ATS score using 6 weighted dimensions."""
    keyword_analysis = _enhance_keyword_analysis(resume_text, job_description)
    jd_skills = extract_skills_from_text(job_description)
    resume_skills = extract_skills_from_text(resume_text)
    matched_skills, missing_skills, skill_pct = compute_keyword_overlap(resume_skills, jd_skills)
    jd_keywords = extract_relevant_keywords(job_description, top_n=45)
    resume_keywords = extract_relevant_keywords(resume_text, top_n=60)
    matched_keywords, missing_keywords, keyword_pct = compute_keyword_overlap(resume_keywords + resume_skills, jd_keywords + jd_skills)

    resume_clean = clean_text(resume_text).lower()
    jd_clean = clean_text(job_description).lower()
    resume_words = len(resume_clean.split())
    sections = 0
    for section in ("experience", "education", "skills", "projects", "certifications", "summary"):
        if re.search(rf"\b{re.escape(section)}\b", resume_clean):
            sections += 1
    resume_quality = min(100.0, sections * 12.0)
    if 350 <= resume_words <= 1200:
        resume_quality += 10
    if re.search(r"\b\d+%|\$\d+|\b\d+x\b|team of \d+|reduced \d+|increased \d+", resume_text, re.I):
        resume_quality += 18
    resume_quality = min(100.0, resume_quality)

    required_years = _years_hint(job_description)
    resume_years = _years_hint(resume_text)
    title_score = 60.0
    if required_years and resume_years is not None:
        title_score = 100.0 if resume_years >= required_years else max(20.0, 100.0 - (required_years - resume_years) * 14.0)
    elif required_years and resume_years is None:
        title_score = 50.0

    degree_terms = ("bachelor", "master", "phd", "degree", "computer science", "engineering", "statistics", "mba")
    cert_terms = ("certification", "certified", "cissp", "security+", "aws certified", "pmp", "cpa")
    jd_education_terms = [term for term in degree_terms + cert_terms if term in jd_clean]
    education_score = 80.0 if not jd_education_terms or "equivalent experience" in jd_clean else (
        sum(1 for term in jd_education_terms if term in resume_clean) / len(jd_education_terms) * 100
    )

    soft_terms = ("communication", "leadership", "collaborat", "stakeholder", "mentor", "cross-functional", "agile", "scrum", "customer")
    jd_soft_terms = [term for term in soft_terms if term in jd_clean]
    soft_score = 70.0 if not jd_soft_terms else sum(1 for term in jd_soft_terms if term in resume_clean) / len(jd_soft_terms) * 100

    overall = (
        skill_pct * 0.30
        + title_score * 0.25
        + keyword_pct * 0.15
        + education_score * 0.10
        + soft_score * 0.10
        + resume_quality * 0.10
    )
    if jd_skills and len(matched_skills) <= 1:
        overall = min(overall, 45.0)
    if required_years and resume_years is None:
        overall = min(overall, 65.0)

    recommendation = "Strong Match" if overall >= 80 else \
                     "Good Match" if overall >= 65 else \
                     "Partial Match" if overall >= 45 else "Weak Match"

    from app.utils.text_processing import TECH_SKILLS

    # Derive strengths from matched skills
    tech_matched = [s for s in (matched_skills or keyword_analysis.strong_keywords) if s in TECH_SKILLS]
    general_matched = [s for s in keyword_analysis.strong_keywords if s not in TECH_SKILLS]
    strengths: list[str] = []
    if tech_matched:
        strengths.append(f"Technical skills present: {', '.join(tech_matched[:6])}")
    if general_matched:
        strengths.append(f"Keyword alignment: {', '.join(general_matched[:5])}")
    if resume_quality >= 60:
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
            match_percentage=round(skill_pct or keyword_pct, 1),
        ),
        experience_score=round(title_score, 1),
        education_score=round(education_score, 1),
        projects_score=100.0 if re.search(r"\b(project|projects)\b", resume_text.lower()) else 45.0,
        certifications_score=100.0 if re.search(r"\b(certification|certifications)\b", resume_text.lower()) else 45.0,
        cultural_fit_score=round(soft_score, 1),
        keyword_analysis=keyword_analysis,
        strengths=strengths,
        concerns=concerns,
        improvement_suggestions=[kw.suggestion for kw in keyword_analysis.missing_keywords[:5]] or [
            f"Add evidence for {kw}" for kw in missing_keywords[:3]
        ],
    )


def _years_hint(text: str) -> int | None:
    matches = re.findall(r"(?i)\b(\d{1,2})\+?\s*(?:years?|yrs?)\s+(?:of\s+)?(?:professional\s+)?(?:experience|exp)\b", text or "")
    if not matches:
        return None
    try:
        return max(int(v) for v in matches)
    except ValueError:
        return None


def score_resume_quality(resume_text: str) -> float:
    """Compute a generic resume quality score for UI upload/ATS preview.

    Strict scoring policy (rework after a bad resume reportedly scored 97):
      - A resume cannot reach 80+ without ALL FOUR pillars present:
        Experience section, Education section, real date ranges
        ("Jan 2022 - Present", "2020-2023"), AND quantified achievements.
      - A resume cannot reach 90+ without rich skill coverage (≥8 distinct
        TECH_SKILLS matches).
      - Buzzword dumps without sections or dates correctly score 30-55.
    """
    if not resume_text or len(resume_text.strip()) < 50:
        return 0.0

    cleaned = clean_text(resume_text)
    text_lower = cleaned.lower()
    words = cleaned.split()
    word_count = len(words)
    skills = set(extract_skills_from_text(cleaned))
    keywords = extract_relevant_keywords(cleaned, top_n=40)

    # Section detection — REQUIRE experience + education explicitly.
    has_experience = bool(re.search(r"\b(experience|work history|employment)\b", text_lower))
    has_education = bool(re.search(r"\b(education|university|college|bachelor|master|b\.s\.|m\.s\.|phd)\b", text_lower))
    OPTIONAL_SECTIONS = ("skills", "projects", "certifications", "summary", "contact", "achievements", "publications", "awards")
    optional_hits = sum(1 for s in OPTIONAL_SECTIONS if re.search(rf"\b{re.escape(s)}\b", text_lower))
    sections = (1 if has_experience else 0) + (1 if has_education else 0) + optional_hits

    # Date / employment ranges — "Jan 2022 - Present", "2020-2023", "06/2019 - 08/2021".
    date_ranges = len(re.findall(
        r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\w*\s*\.?\s*\d{4}|"
        r"\b\d{4}\s*[\-–—to]+\s*(\d{4}|present|current)|"
        r"\b\d{1,2}/\d{4}\s*[\-–—]\s*(\d{1,2}/\d{4}|present|current)",
        text_lower,
    ))

    # Quantified achievements — real metrics, not just any number.
    metrics = len(re.findall(
        r"\b\d+%|\$\d+[kKmMbB]?|\b\d+x\b(?!\d)|\bby\s+\d+|team\s+of\s+\d+|\bsaved\s+\d+|\breduced\s+\d+|\bincreased\s+\d+",
        resume_text,
    ))

    # Professional signals.
    has_email = bool(re.search(r"[a-z0-9._-]+@[a-z0-9.-]+\.[a-z]{2,}", text_lower))
    has_links = bool(re.search(r"\b(github\.com|linkedin\.com|portfolio|gitlab\.com)\b", text_lower))

    # Component scores — each capped so no single signal can dominate.
    skills_pts  = min(20.0, len(skills) * 1.4)
    keyword_pts = min(8.0,  len(set(keywords)) * 0.15)
    section_pts = min(20.0, sections * 3.0)
    length_pts  = min(12.0, max(0.0, min(word_count, 1100) - 280) / 70.0)
    date_pts    = min(10.0, date_ranges * 2.5)
    metrics_pts = min(10.0, metrics * 1.5)
    contact_pts = (4.0 if has_email else 0.0) + (4.0 if has_links else 0.0)

    score = 8.0 + skills_pts + keyword_pts + section_pts + length_pts + date_pts + metrics_pts + contact_pts

    # Hard penalties for missing structural pillars.
    if not has_experience: score -= 18.0
    if not has_education:  score -= 10.0
    if word_count < 200:   score -= 20.0
    if date_ranges == 0:   score -= 12.0
    if metrics == 0:       score -= 6.0

    # Hard caps — cannot escape these without quality markers.
    has_all_pillars = has_experience and has_education and date_ranges >= 2 and metrics >= 2
    if not has_all_pillars:
        score = min(score, 75.0)
    if len(skills) < 8:
        score = min(score, 78.0)

    return round(min(100.0, max(0.0, score)), 1)

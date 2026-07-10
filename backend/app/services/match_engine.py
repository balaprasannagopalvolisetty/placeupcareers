"""
PlaceUp Career — Match Scoring Engine
Hybrid resume-to-job matching using TF-IDF + keyword overlap scoring.

Scoring weights:
- TF-IDF cosine similarity: 50%
- Keyword overlap: 50%

Inspired by: github.com/srbhr/Resume-Matcher (TF-IDF approach)
"""

import logging
import time
from typing import Optional

from app.config import settings
from app.models.match import MatchResult, MatchScores
from app.models.resume import KeywordWithImpact
from app.models.job import VisaBadges
from app.utils.text_processing import (
    extract_relevant_keywords, extract_skills_from_text,
    compute_keyword_overlap, truncate_text, clean_text,
)

logger = logging.getLogger(__name__)

# Score weights
TFIDF_WEIGHT = 0.50
KEYWORD_WEIGHT = 0.50
SEMANTIC_WEIGHT = 0.0

# Validation thresholds — below these, inputs are too thin for a trustworthy
# score, so the result is capped and flagged instead of silently misleading.
MIN_RESUME_CHARS = 200
MIN_JD_CHARS = 120
LOW_CONFIDENCE_CAP = 60


def _clamp(value: float) -> float:
    """Clamp any component score into the valid 0-100 range."""
    try:
        return max(0.0, min(100.0, float(value)))
    except (TypeError, ValueError):
        return 0.0


def _input_confidence(resume_text: str, job_description: str) -> tuple[bool, list[str]]:
    """Validate scoring inputs. Returns (is_confident, warnings).

    Empty or near-empty inputs previously produced arbitrary scores (an empty
    JD can yield 100% keyword overlap). Now they are detected up front.
    """
    warnings: list[str] = []
    resume_len = len((resume_text or "").strip())
    jd_len = len((job_description or "").strip())
    if resume_len < MIN_RESUME_CHARS:
        warnings.append("Resume text is too short for a reliable match score")
    if jd_len < MIN_JD_CHARS:
        warnings.append("Job description is too short for a reliable match score")
    return not warnings, warnings


def _calibrate_tfidf(raw_score: float) -> float:
    """Calibrate raw TF-IDF cosine similarity to the 0-100 UI scale.

    Raw cosine similarity between a resume and a JD rarely exceeds ~0.5 even
    for excellent matches (different document lengths and vocabularies), which
    systematically dragged the composite down. A concave power curve keeps
    0→0 and 100→100 fixed while giving realistic mid-range separation:
    raw 25 → ~41, raw 40 → ~55, raw 60 → ~72.
    """
    raw = _clamp(raw_score)
    if raw <= 0:
        return 0.0
    return round(100.0 * (raw / 100.0) ** 0.65, 1)


def compute_tfidf_score(resume_text: str, job_description: str) -> float:
    """Compute TF-IDF cosine similarity between resume and job description.

    Uses scikit-learn's TfidfVectorizer to transform both documents
    into TF-IDF vectors, then computes cosine similarity.

    This is the core technique from Resume-Matcher.

    Args:
        resume_text: Full resume text
        job_description: Full job description text

    Returns:
        Similarity score from 0-100
    """
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.metrics.pairwise import cosine_similarity

        # Clean texts
        resume_clean = clean_text(resume_text)
        jd_clean = clean_text(job_description)

        if not resume_clean or not jd_clean:
            return 0.0

        # TF-IDF vectorization
        vectorizer = TfidfVectorizer(
            max_features=5000,
            stop_words="english",
            ngram_range=(1, 2),  # Unigrams + bigrams for better matching
            min_df=1,
            max_df=0.95,
        )

        tfidf_matrix = vectorizer.fit_transform([resume_clean, jd_clean])

        # Cosine similarity
        similarity = cosine_similarity(tfidf_matrix[0:1], tfidf_matrix[1:2])[0][0]

        # Scale to 0-100
        score = round(similarity * 100, 1)
        return min(score, 100.0)

    except ImportError:
        logger.error("scikit-learn not installed. Run: pip install scikit-learn")
        return 0.0
    except Exception as e:
        logger.error(f"TF-IDF scoring error: {e}")
        return 0.0


def compute_keyword_score(resume_text: str, job_description: str) -> tuple[float, list[str], list[KeywordWithImpact]]:
    """Compute keyword overlap score between resume and job description.

    Extracts top keywords from both documents, compares overlap,
    and returns matched/missing keyword lists.

    Args:
        resume_text: Full resume text
        job_description: Full job description text

    Returns:
        Tuple of (score 0-100, matched_keywords, missing_keywords)
    """
    # Extract keywords + technical skills
    jd_keywords = extract_relevant_keywords(job_description, top_n=30)
    jd_skills = extract_skills_from_text(job_description)
    jd_all = list(set(jd_keywords + jd_skills))

    resume_keywords = extract_relevant_keywords(resume_text, top_n=40)
    resume_skills = extract_skills_from_text(resume_text)
    resume_all = list(set(resume_keywords + resume_skills))

    matched, missing, overlap_pct = compute_keyword_overlap(resume_all, jd_all)

    # Create missing keywords with impact levels
    missing_with_impact = []
    for kw in missing[:15]:
        impact = "high" if kw in jd_skills else "medium"
        missing_with_impact.append(KeywordWithImpact(
            keyword=kw,
            impact=impact,
            category="technical" if kw in jd_skills else "general",
            suggestion=f"Add '{kw}' to your resume's skills or experience section",
        ))

    return overlap_pct, matched, missing_with_impact


def _build_insights(
    matched_kws: list[str],
    missing_kws: list[KeywordWithImpact],
    tfidf_score: float,
    keyword_score: float,
    overall: int,
) -> tuple[list[str], list[str], list[str]]:
    """Derive strengths, gaps, and suggestions from keyword analysis results."""
    from app.utils.text_processing import TECH_SKILLS

    # Strengths — highlight matched technical skills and keyword coverage
    strengths: list[str] = []
    tech_matched = [kw for kw in matched_kws if kw in TECH_SKILLS]
    if tech_matched:
        strengths.append(f"Technical skills aligned: {', '.join(tech_matched[:6])}")
    general_matched = [kw for kw in matched_kws if kw not in TECH_SKILLS]
    if general_matched:
        strengths.append(f"Strong keyword coverage: {', '.join(general_matched[:5])}")
    if tfidf_score >= 60:
        strengths.append("High overall content similarity to the job description")
    if not strengths:
        strengths.append("Upload a more targeted resume to identify strengths")

    # Gaps — missing high-impact keywords
    high = [kw for kw in missing_kws if kw.impact == "high"]
    medium = [kw for kw in missing_kws if kw.impact == "medium"]
    gaps: list[str] = []
    if high:
        gaps.append(f"Missing technical skills: {', '.join(k.keyword for k in high[:5])}")
    if medium:
        gaps.append(f"Missing keywords: {', '.join(k.keyword for k in medium[:4])}")
    if overall < 45:
        gaps.append("Resume vocabulary significantly diverges from this job description")

    # Suggestions — actionable per missing keyword
    suggestions = [kw.suggestion for kw in missing_kws[:8]]
    if not suggestions and overall < 65:
        suggestions.append("Tailor your resume summary and skills section to mirror the job description language")

    return strengths, gaps, suggestions


async def compute_match_score(
    resume_text: str,
    job_description: str,
    job_title: str = "",
    visa_badges: Optional[VisaBadges] = None,
) -> MatchResult:
    """Compute the full hybrid match score.

    Combines TF-IDF cosine similarity (50%) and keyword overlap (50%).

    Args:
        resume_text: Full resume text
        job_description: Full job description text
        job_title: Job title for context
        visa_badges: Pre-computed visa compatibility

    Returns:
        MatchResult with composite score and detailed analysis
    """
    start_time = time.time()

    # 0. Input validation — thin inputs get flagged + capped, empty gets 0.
    confident, input_warnings = _input_confidence(resume_text, job_description)
    if not (resume_text or "").strip() or not (job_description or "").strip():
        return MatchResult(
            overall_match_score=0,
            recommendation="Needs Work",
            scores=MatchScores(tfidf_score=0.0, keyword_score=0.0, semantic_score=0.0),
            matched_keywords=[],
            missing_keywords=[],
            visa_compatibility=visa_badges or VisaBadges(),
            strengths=[],
            gaps=input_warnings or ["Missing resume or job description text"],
            suggestions=["Upload a complete resume to compute an accurate match score"],
        )

    # 1. TF-IDF score (calibrated — raw cosine underestimates real matches)
    tfidf_score = _calibrate_tfidf(compute_tfidf_score(resume_text, job_description))

    # 2. Keyword score
    keyword_score, matched_kws, missing_kws = compute_keyword_score(resume_text, job_description)
    keyword_score = _clamp(keyword_score)

    # Cross-validation: a high keyword score with zero actually-matched
    # keywords (or vice versa) indicates extraction noise — trust the
    # conservative signal.
    if keyword_score > 50 and not matched_kws:
        keyword_score = 25.0

    # Compute weighted composite
    overall = round(
        tfidf_score * TFIDF_WEIGHT +
        keyword_score * KEYWORD_WEIGHT
    )
    overall = max(0, min(100, overall))
    if not confident:
        overall = min(overall, LOW_CONFIDENCE_CAP)

    # Determine recommendation
    if overall >= 80:
        recommendation = "Strong Match"
    elif overall >= 65:
        recommendation = "Good Match"
    elif overall >= 45:
        recommendation = "Fair Match"
    else:
        recommendation = "Needs Work"

    # Build actionable insights from keyword analysis
    strengths, gaps, suggestions = _build_insights(
        matched_kws, missing_kws, tfidf_score, keyword_score, overall
    )
    if input_warnings:
        gaps = input_warnings + gaps

    elapsed = (time.time() - start_time) * 1000
    logger.info(f"Match scoring completed in {elapsed:.0f}ms — Score: {overall}")

    return MatchResult(
        overall_match_score=overall,
        recommendation=recommendation,
        scores=MatchScores(
            tfidf_score=tfidf_score,
            keyword_score=keyword_score,
            semantic_score=0.0,
        ),
        matched_keywords=matched_kws,
        missing_keywords=missing_kws,
        visa_compatibility=visa_badges or VisaBadges(),
        strengths=strengths,
        gaps=gaps,
        suggestions=suggestions,
    )

"""
PlaceUp Career — Match Scoring Engine
Hybrid resume-to-job matching using TF-IDF + keywords + LLM semantic analysis.

Scoring weights:
- TF-IDF cosine similarity: 30%
- Keyword overlap: 30%
- LLM semantic score: 40%

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
    extract_keywords, extract_skills_from_text,
    compute_keyword_overlap, truncate_text, clean_text,
)

logger = logging.getLogger(__name__)

# Score weights
TFIDF_WEIGHT = 0.50
KEYWORD_WEIGHT = 0.50
SEMANTIC_WEIGHT = 0.0


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
    jd_keywords = extract_keywords(job_description, top_n=30)
    jd_skills = extract_skills_from_text(job_description)
    jd_all = list(set(jd_keywords + jd_skills))

    resume_keywords = extract_keywords(resume_text, top_n=40)
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


async def compute_semantic_score(
    resume_text: str,
    job_description: str,
    job_title: str = "",
) -> tuple[float, list[str], list[str], list[str]]:
    """Compute LLM-based semantic relevance score.

    (Note: Switched to local NLP processing per requirements to avoid LLM costs)
    Returns dummy fallback data.
    """
    logger.info("Semantic scoring skipped (local-only mode)")
    return 50.0, [], ["Semantic analysis disabled to save costs"], []


async def compute_match_score(
    resume_text: str,
    job_description: str,
    job_title: str = "",
    visa_badges: Optional[VisaBadges] = None,
) -> MatchResult:
    """Compute the full hybrid match score.

    Combines three scoring methods with weighted averaging:
    1. TF-IDF cosine similarity (30%)
    2. Keyword overlap (30%)
    3. LLM semantic analysis (40%)

    Args:
        resume_text: Full resume text
        job_description: Full job description text
        job_title: Job title for LLM context
        visa_badges: Pre-computed visa compatibility

    Returns:
        MatchResult with composite score and detailed analysis
    """
    start_time = time.time()

    # 1. TF-IDF score
    tfidf_score = compute_tfidf_score(resume_text, job_description)

    # 2. Keyword score
    keyword_score, matched_kws, missing_kws = compute_keyword_score(resume_text, job_description)

    # 3. Semantic score (async LLM call)
    semantic_score, strengths, gaps, suggestions = await compute_semantic_score(
        resume_text, job_description, job_title
    )

    # Compute weighted composite
    overall = round(
        tfidf_score * TFIDF_WEIGHT +
        keyword_score * KEYWORD_WEIGHT +
        semantic_score * SEMANTIC_WEIGHT
    )
    overall = max(0, min(100, overall))

    # Determine recommendation
    if overall >= 80:
        recommendation = "Strong Match"
    elif overall >= 65:
        recommendation = "Good Match"
    elif overall >= 45:
        recommendation = "Fair Match"
    else:
        recommendation = "Needs Work"

    elapsed = (time.time() - start_time) * 1000
    logger.info(f"Match scoring completed in {elapsed:.0f}ms — Score: {overall}")

    return MatchResult(
        overall_match_score=overall,
        recommendation=recommendation,
        scores=MatchScores(
            tfidf_score=tfidf_score,
            keyword_score=keyword_score,
            semantic_score=semantic_score,
        ),
        matched_keywords=matched_kws,
        missing_keywords=missing_kws,
        visa_compatibility=visa_badges or VisaBadges(),
        strengths=strengths,
        gaps=gaps,
        suggestions=suggestions,
    )

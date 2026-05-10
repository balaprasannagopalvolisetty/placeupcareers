"""
PlaceUp Career — Match Scoring Data Models
Defines Pydantic schemas for the hybrid resume-to-job matching engine.
Inspired by Resume-Matcher's TF-IDF approach combined with LLM semantic analysis.
"""

from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from app.models.resume import KeywordWithImpact
from app.models.job import VisaBadges


class MatchScores(BaseModel):
    """Individual scoring dimensions for the match."""
    tfidf_score: float = Field(default=0.0, ge=0, le=100, description="TF-IDF cosine similarity score")
    keyword_score: float = Field(default=0.0, ge=0, le=100, description="Keyword overlap percentage")
    semantic_score: float = Field(default=0.0, ge=0, le=100, description="LLM semantic relevance score")


class MatchResult(BaseModel):
    """Complete match analysis between a resume and a job posting.

    Combines three scoring methods:
    1. TF-IDF cosine similarity (30% weight)
    2. Keyword overlap (30% weight)
    3. LLM semantic analysis (40% weight)
    """
    # Composite score
    overall_match_score: int = Field(ge=0, le=100, description="Weighted composite match score")
    recommendation: str = Field(description="Strong Match | Good Match | Fair Match | Needs Work")

    # Individual scores
    scores: MatchScores = Field(default_factory=MatchScores)

    # Keyword analysis
    matched_keywords: list[str] = Field(default=[], description="Keywords found in both resume and JD")
    missing_keywords: list[KeywordWithImpact] = Field(
        default=[], description="Important JD keywords missing from resume"
    )

    # Visa compatibility
    visa_compatibility: VisaBadges = Field(default_factory=VisaBadges)

    # LLM insights
    strengths: list[str] = Field(default=[], description="Why this is a good match")
    gaps: list[str] = Field(default=[], description="Areas where resume falls short")
    suggestions: list[str] = Field(default=[], description="How to improve match score")

    class Config:
        json_schema_extra = {
            "example": {
                "overall_match_score": 78,
                "recommendation": "Good Match",
                "scores": {"tfidf_score": 72.5, "keyword_score": 80.0, "semantic_score": 82.0},
                "matched_keywords": ["Python", "FastAPI", "Docker", "AWS"],
                "missing_keywords": [
                    {"keyword": "Kubernetes", "impact": "high", "suggestion": "Add K8s experience"}
                ],
                "strengths": ["Strong Python background", "Relevant cloud experience"],
                "gaps": ["No container orchestration experience"],
            }
        }


class MatchRequest(BaseModel):
    """Request body for single match scoring."""
    job_id: str = Field(description="Job posting ID to match against")
    job_description: Optional[str] = Field(
        default=None, description="Override job description text (optional if job_id provided)"
    )
    job_title: Optional[str] = None


class BatchMatchRequest(BaseModel):
    """Request body for batch match scoring — score resume against multiple jobs."""
    job_ids: list[str] = Field(
        description="List of job posting IDs to match against",
        min_length=1,
        max_length=20,
    )


class BatchMatchResult(BaseModel):
    """Result from batch matching — ranked list of job matches."""
    results: list[dict] = Field(
        default=[], description="List of {job_id, match_score, recommendation}"
    )
    total_matched: int = 0
    processing_time_ms: float = 0.0


class MatchResponse(BaseModel):
    """API response for match scoring."""
    success: bool = True
    match: MatchResult
    job_id: str
    job_title: str = ""
    company: str = ""
    scored_at: datetime = Field(default_factory=datetime.utcnow)
    processing_time_ms: float = 0.0

"""JD-aware match scoring wrapper (Part B).

Runs the JD-quality gate *before* the existing scorer. When the JD is too thin
to score honestly (the 41/100-on-boilerplate problem), it returns
``score=None`` with a surfaced reason instead of a misleading number. When the
JD is scoreable, it delegates to the existing ``compute_match_score`` and
passes the boilerplate-stripped JD through so the scorer keys off real
requirements rather than company puffery.

This is additive: it does not change ``MatchResult`` (whose ``overall_match_
score`` is a required int). Callers in app/api/match.py can switch to
``score_job_match`` and branch on ``result.score is None``.

    res = await score_job_match(resume_text, jd, job_title)
    if res.score is None:
        card["match_score"] = None
        card["match_reason"] = res.reason      # "JD too thin to score reliably"
    else:
        card["match_score"] = res.score
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from app.models.match import MatchResult
from app.models.job import VisaBadges
from app.services.jd_quality_gate import assess_jd, JDQuality


@dataclass
class ScoredMatch:
    score: Optional[int]              # None => not confidently scoreable
    recommendation: str
    reason: str
    jd_depth: str
    detail: Optional[MatchResult] = None  # full breakdown when scoreable


async def score_job_match(
    resume_text: str,
    job_description: str,
    job_title: str = "",
    visa_badges: Optional["VisaBadges"] = None,
    *,
    min_words: int = 60,
    min_skills: int = 2,
) -> ScoredMatch:
    """Gate, then score. Returns ``score=None`` for unscoreable JDs."""
    quality: JDQuality = assess_jd(
        job_description, min_words=min_words, min_skills=min_skills
    )
    if not quality.scoreable:
        return ScoredMatch(
            score=None,
            recommendation="Insufficient JD",
            reason="JD too thin to score reliably — "
                   f"{quality.keyword_count} extractable skills, "
                   f"{quality.section_count} sections.",
            jd_depth=quality.depth,
        )

    # Import here to avoid a heavy import at module load.
    from app.services.match_engine import compute_match_score

    detail = await compute_match_score(
        resume_text=resume_text,
        # Use the boilerplate-stripped JD so marketing fluff doesn't inflate.
        job_description=quality.cleaned_jd or job_description,
        job_title=job_title,
        visa_badges=visa_badges,
    )
    return ScoredMatch(
        score=detail.overall_match_score,
        recommendation=detail.recommendation,
        reason="ok",
        jd_depth=quality.depth,
        detail=detail,
    )

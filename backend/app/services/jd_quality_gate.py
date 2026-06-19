"""JD-quality gate for the match scorer (Part B).

The trust bug: a Visa posting with ~2 boilerplate sentences scored 41/100.
A keyword scorer rewards fluff ("Visa", "world", "impact") and inflates from
length, so a JD with *no extractable requirements* still produces a confident-
looking number. A 41 on an unscoreable posting is worse than honest silence.

This module assesses whether a JD is rich enough to score at all. If not, the
scorer should return ``score=None`` with a human reason ("JD too thin to score
reliably") rather than a misleading number.

It also strips company-marketing boilerplate before requirement extraction so
the downstream scorer keys off real skills/tools/years, not puffery.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.utils.text_processing import extract_skills_from_text

# Marketing / boilerplate sentence starters to drop before extraction.
_BOILERPLATE_LINE_RE = re.compile(
    r"(?i)^(?:"
    r"at\s+\w+[^.]*?,\s*(?:you|we|our)|"          # "At Visa, you'll have..."
    r"we\s+are\s+(?:a|an|the|proud|committed|looking)|"
    r"our\s+(?:mission|vision|culture|team|company|values)|"
    r"join\s+(?:us|our)|"
    r"(?:about|who)\s+we\s+are|"
    r"equal\s+opportunity|we\s+are\s+an\s+equal|"
    r"as\s+a\s+(?:global|leading|world)"
    r")"
)
# Section headers that signal a real, structured JD.
_SECTION_RE = re.compile(
    r"(?i)\b("
    r"responsibilities|requirements|qualifications|what you'?ll do|"
    r"what you will do|minimum qualifications|basic qualifications|"
    r"preferred qualifications|skills|experience|duties|"
    r"who you are|what we'?re looking for"
    r")\b"
)
_YEARS_RE = re.compile(r"(?i)\b\d{1,2}\+?\s*(?:years?|yrs?)\b")


@dataclass
class JDQuality:
    scoreable: bool
    depth: str                       # "rich" | "moderate" | "thin"
    reason: str
    keyword_count: int
    section_count: int
    word_count: int
    cleaned_jd: str = ""
    skills: list[str] = field(default_factory=list)


def strip_boilerplate(job_description: str) -> str:
    """Drop marketing lines so requirement extraction keys off real content."""
    lines = re.split(r"[\n\r]+|(?<=[.!?])\s+(?=[A-Z])", job_description or "")
    kept = [ln for ln in lines if ln.strip() and not _BOILERPLATE_LINE_RE.match(ln.strip())]
    return "\n".join(kept).strip()


def assess_jd(
    job_description: str,
    *,
    min_words: int = 60,
    min_skills: int = 2,
) -> JDQuality:
    """Decide whether a JD is rich enough to produce a confident match score.

    Mirrors the signals the UI already flags (JD depth, section count,
    extractable keywords). Returns ``scoreable=False`` for thin JDs.
    """
    raw = job_description or ""
    cleaned = strip_boilerplate(raw)
    words = re.findall(r"\b[a-zA-Z][a-zA-Z0-9+#./-]*\b", cleaned)
    word_count = len(words)
    skills = list(dict.fromkeys(extract_skills_from_text(cleaned)))
    section_count = len(set(mt.group(1).lower() for mt in _SECTION_RE.finditer(raw)))
    has_years = bool(_YEARS_RE.search(raw))

    # Hard gate: no extractable requirements => not scoreable.
    # A short JD is fine if it is skill-dense; only reject when it is BOTH
    # short AND sparse (the 2-sentence-boilerplate case).
    too_few_skills = len(skills) < min_skills
    too_short_and_sparse = word_count < min_words and len(skills) < 5
    if too_few_skills or too_short_and_sparse:
        return JDQuality(
            scoreable=False,
            depth="thin",
            reason="insufficient_jd: JD too thin to score reliably "
                   f"({word_count} words, {len(skills)} extractable skills)",
            keyword_count=len(skills),
            section_count=section_count,
            word_count=word_count,
            cleaned_jd=cleaned,
            skills=skills,
        )
    if section_count <= 1 and not has_years and len(skills) < 4:
        return JDQuality(
            scoreable=False,
            depth="thin",
            reason="insufficient_jd: no clear requirements section or "
                   "experience signal to anchor a match",
            keyword_count=len(skills),
            section_count=section_count,
            word_count=word_count,
            cleaned_jd=cleaned,
            skills=skills,
        )

    depth = "rich" if (section_count >= 2 and len(skills) >= 5) else "moderate"
    return JDQuality(
        scoreable=True,
        depth=depth,
        reason="ok",
        keyword_count=len(skills),
        section_count=section_count,
        word_count=word_count,
        cleaned_jd=cleaned,
        skills=skills,
    )

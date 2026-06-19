"""Post-scrape job filters and enrichment."""
from __future__ import annotations

import re
from typing import Optional, Tuple

from app.services.global_visa_rules import in_target_country


def is_target_country_scope(location: str) -> bool:
    """True when a job is in any PlaceUp target country."""
    return in_target_country(location)[0]


def in_scope_country(location: str, default_country: str | None = None) -> tuple[bool, str | None]:
    return in_target_country(location, default=default_country)


_YEARS_PATTERNS = (
    re.compile(r"(\d{1,2})\s*[-–to]+\s*(\d{1,2})\s*\+?\s*(?:years|yrs)\b", re.I),
    re.compile(r"(\d{1,2})\s*\+\s*(?:years|yrs)\b", re.I),
    re.compile(r"(?:minimum|at least)\s+(\d{1,2})\s*(?:years|yrs)\b", re.I),
    re.compile(r"(\d{1,2})\s*(?:years|yrs)\s+of\s+experience", re.I),
)


def parse_years(text: str) -> Tuple[Optional[int], Optional[int]]:
    """Extract the most-permissive years range declared by a JD."""
    if not text:
        return (None, None)
    best_min: Optional[int] = None
    best_max: Optional[int] = None
    for pattern in _YEARS_PATTERNS:
        for m in pattern.finditer(text):
            groups = [g for g in m.groups() if g is not None]
            if len(groups) == 2:
                lo, hi = int(groups[0]), int(groups[1])
                if best_min is None or lo < best_min:
                    best_min = lo
                if best_max is None or hi > best_max:
                    best_max = hi
            elif len(groups) == 1:
                lo = int(groups[0])
                if best_min is None or lo < best_min:
                    best_min = lo
    return (best_min, best_max)


HIGH_LEVEL_TITLE_PATTERNS = (
    re.compile(r"\b(chief|cxo|cto|cio|cfo|ceo|vp|vice president|head of|director|executive director)\b", re.I),
    re.compile(r"\b(principal|distinguished|fellow|architect manager|engineering manager|staff engineer|staff software|staff data)\b", re.I),
)


SENIOR_TITLE_PATTERNS = (
    re.compile(r"\b(senior|sr\.?|lead)\b", re.I),
)


EARLY_CAREER_TITLE_PATTERNS = (
    re.compile(r"\b(intern|internship|co-op|new grad|new graduate|graduate|entry[- ]level|junior|jr\.?|associate|trainee|apprentice)\b", re.I),
)


def is_entry_level(years_min: Optional[int]) -> bool:
    """Treat 0-5 yr roles as entry-level priority. Unknown experience counts too."""
    if years_min is None:
        return True
    return 0 <= years_min <= 5


# Approximate floor of years a seniority signal implies when the JD doesn't
# state an explicit number. Used so the Experience filter actually narrows the
# list when the user picks a tight band (0-2 / 0-5) instead of silently keeping
# every senior/lead role that happens to omit a "X+ years" line.
_SENIOR_TITLE_IMPLIED_MIN = 5


def is_senior_title(title: str) -> bool:
    """True for senior-ish titles that can be kept but should sort below junior/mid."""
    return any(pattern.search(title or "") for pattern in SENIOR_TITLE_PATTERNS)


def is_target_experience(
    title: str,
    years_min: Optional[int],
    years_max: Optional[int],
    *,
    max_years: int = 10,
    description: str | None = None,
) -> bool:
    """Return True for roles appropriate for 0 through max_years experience.

    When the user narrows the Experience band (max_years < 10) the filter must
    visibly bite. Most rows have no parsed years in metadata, so we (a) parse a
    range from the JD/title text as a fallback, and (b) treat senior/lead titles
    as implying ~5 yrs when nothing explicit is stated. max_years >= 50 ("Any")
    stays fully permissive.
    """
    title = title or ""
    try:
        years_min = int(years_min) if years_min is not None else None
    except (TypeError, ValueError):
        years_min = None
    try:
        years_max = int(years_max) if years_max is not None else None
    except (TypeError, ValueError):
        years_max = None
    if any(pattern.search(title) for pattern in HIGH_LEVEL_TITLE_PATTERNS):
        return False
    # "Any" -- do not narrow at all.
    if max_years >= 50:
        return years_min is None or years_min <= max_years

    # Fall back to text-parsed years when metadata is missing.
    if years_min is None and years_max is None and description:
        parsed_min, parsed_max = parse_years(description)
        if parsed_min is not None:
            years_min = parsed_min
        if parsed_max is not None:
            years_max = parsed_max

    if years_min is not None and years_min > max_years:
        return False
    if any(pattern.search(title) for pattern in EARLY_CAREER_TITLE_PATTERNS):
        return True
    if years_min is not None:
        return years_min <= max_years
    if years_max is not None:
        return years_max <= max_years
    # Unknown years: for a tight band, a senior/lead title implies more years
    # than the band allows, so drop it; otherwise keep (unknown = eligible).
    if max_years < _SENIOR_TITLE_IMPLIED_MIN and is_senior_title(title):
        return False
    return True


def is_high_level_title(title: str) -> bool:
    """True for titles we do not want in the default 0-10 student-friendly pool."""
    return any(pattern.search(title or "") for pattern in HIGH_LEVEL_TITLE_PATTERNS)


def is_early_career_title(title: str) -> bool:
    """True for explicit junior/new-grad/intern/associate titles."""
    return any(pattern.search(title or "") for pattern in EARLY_CAREER_TITLE_PATTERNS)

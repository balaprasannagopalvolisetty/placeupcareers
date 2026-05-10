"""
Post-scrape job filters & enrichment.

- USA + Canada geo filter (rejects everything else)
- Years-of-experience parser (tags `years_min` / `years_max`, prioritizes 0-5)

Kept self-contained so the scraper can call one function and the rest of
the pipeline doesn't need to know how the heuristics work.
"""
from __future__ import annotations

import re
from typing import Optional, Tuple

US_STATES = {
    "AL","AK","AZ","AR","CA","CO","CT","DE","FL","GA","HI","ID","IL","IN","IA",
    "KS","KY","LA","ME","MD","MA","MI","MN","MS","MO","MT","NE","NV","NH","NJ",
    "NM","NY","NC","ND","OH","OK","OR","PA","RI","SC","SD","TN","TX","UT","VT",
    "VA","WA","WV","WI","WY","DC","PR",
}
CA_PROVINCES = {
    "AB","BC","MB","NB","NL","NS","NT","NU","ON","PE","QC","SK","YT",
}
US_KEYWORDS = (
    "united states", "u.s.a", "u.s.", "usa", "u s a",
    "remote, us", "remote us", "us remote", "remote (us)",
    "remote — us", "remote - us", "anywhere in the us",
)
CA_KEYWORDS = (
    "canada", "remote, canada", "canada remote", "remote (canada)",
    "remote — canada", "remote - canada",
)
EXCLUDE_KEYWORDS = (
    # If we see explicit non-NA mentions, drop the job.
    "india", "bangalore", "bengaluru", "hyderabad", "chennai", "mumbai", "delhi", "noida", "pune", "gurgaon", "gurugram",
    "philippines", "manila", "cebu",
    "uk only", "united kingdom", "london", "england", "ireland", "dublin",
    "europe only", "eu only", "emea only",
    "germany", "berlin", "munich", "france", "paris", "spain", "barcelona", "madrid",
    "australia", "sydney", "melbourne",
    "singapore", "hong kong", "tokyo", "japan", "china", "shanghai", "beijing",
    "mexico", "argentina", "brazil",
)

REMOTE_KEYWORDS = ("remote", "anywhere", "work from home", "wfh")


def is_us_or_canada(location: str) -> bool:
    """Return True iff the location string clearly maps to US or Canada."""
    if not location:
        # No location info — be lenient (let the visa classifier decide later).
        return True
    loc = location.lower().strip()

    # Hard reject if any non-NA keyword shows up.
    for bad in EXCLUDE_KEYWORDS:
        if bad in loc:
            return False

    # Direct keyword wins.
    for kw in US_KEYWORDS + CA_KEYWORDS:
        if kw in loc:
            return True

    # Look for trailing state/province codes (e.g. "Austin, TX" or "Toronto, ON").
    # Match the LAST 2-letter token at the end.
    m = re.search(r"\b([A-Z]{2})\b\s*$", location.strip())
    if m and (m.group(1) in US_STATES or m.group(1) in CA_PROVINCES):
        return True

    # Remote-only roles without a country — accept (the JD will be checked elsewhere).
    if any(kw in loc for kw in REMOTE_KEYWORDS):
        return True

    return False


_YEARS_PATTERNS = (
    # "3-5 years", "3 to 5 years", "3+ years"
    re.compile(r"(\d{1,2})\s*[-–to]+\s*(\d{1,2})\s*\+?\s*(?:years|yrs)\b", re.I),
    re.compile(r"(\d{1,2})\s*\+\s*(?:years|yrs)\b", re.I),
    re.compile(r"(?:minimum|at least)\s+(\d{1,2})\s*(?:years|yrs)\b", re.I),
    re.compile(r"(\d{1,2})\s*(?:years|yrs)\s+of\s+experience", re.I),
)


def parse_years(text: str) -> Tuple[Optional[int], Optional[int]]:
    """
    Extract the most-permissive (years_min, years_max) the JD declares.

    "3-5 years experience" → (3, 5)
    "5+ years"             → (5, None)
    "at least 3 years"     → (3, None)
    No match               → (None, None)
    """
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


def is_entry_level(years_min: Optional[int]) -> bool:
    """Treat 0-5 yr roles as priority. Unknown experience counts as entry too."""
    if years_min is None:
        return True
    return 0 <= years_min <= 5

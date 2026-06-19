"""Staffing / body-shop detection — downrank + flag, not hard block (A5).

Per product decision: staffing agencies are *kept* (many genuinely sponsor
F1-OPT / H-1B) but flagged and pushed down in ranking, rather than removed.
This avoids nuking sponsorship-friendly roles while cleaning up the feed's
signal.

Usage in the loader / ranking layer::

    flag = classify_staffing(job["company"], job.get("description", ""))
    if flag.is_staffing:
        job.setdefault("extra_metadata", {})["staffing_agency"] = True
        job["rank_penalty"] = flag.penalty          # subtract in sort score
        job["staffing_reason"] = flag.reason

Nothing here sets ``status: inactive``. If you later want a hard block for a
subset, promote those keys into ``HARD_BLOCK`` and check it explicitly.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from app.services.employer_normalizer import normalize_employer

# Known body-shops / generic-req staffing agencies (normalized keys).
# These are *downranked + flagged*, not deleted. Confirmed from the sample set;
# extend over time. Keys must match normalize_employer() output.
STAFFING_AGENCIES: frozenset[str] = frozenset(
    {
        "teksystems", "kforce", "kforce technology staffing", "amtex system",
        "amtex systems", "cloud destinations", "algo soft solutions",
        "sierra business solution", "lorvenk technologies",
        "phoenix technology partners", "yoh", "robert half", "insight global",
        "apex systems", "collabera", "mindlance", "judge group", "diverse lynx",
        "softhq", "intelliswift", "nityo infotech", "artech", "akraya",
        "compunnel", "vdart", "stellent it", "sunsoft technologies",
        "net2source", "talentburst", "russell tobin", "first tek",
    }
)

# If you ever want a true hard block for the worst offenders, list keys here
# and have the loader skip them. Empty by default (downrank-only policy).
HARD_BLOCK: frozenset[str] = frozenset()

# Generic staffing language in the company name or JD.
_STAFFING_NAME_RE = re.compile(
    r"(?i)\b("
    r"staffing|recruit(?:ing|ment)?|talent\s+solutions?|consult(?:ing|ants?)|"
    r"technologies\s+llc|tech\s+solutions?|it\s+solutions?|workforce|"
    r"placement|manpower|resourc(?:e|ing)"
    r")\b"
)
_STAFFING_JD_RE = re.compile(
    r"(?i)\b("
    r"our client|client is (?:seeking|looking)|on behalf of our client|"
    r"contract(?:[- ]to[- ]hire)?\s+(?:position|role|opportunity)|"
    r"w2 only|c2c|corp[- ]to[- ]corp|multiple positions|various locations"
    r")\b"
)

# Penalty applied to the ranking score (tune to your sort scale, 0-100).
PENALTY_LISTED = 25.0   # on the curated agency list
PENALTY_HEURISTIC = 12.0  # name/JD language only


@dataclass(frozen=True)
class StaffingFlag:
    is_staffing: bool
    penalty: float = 0.0
    reason: Optional[str] = None
    hard_block: bool = False


def classify_staffing(company: Optional[str], description: str = "") -> StaffingFlag:
    """Classify an employer as staffing/body-shop for downranking.

    >>> classify_staffing("TEKsystems c/o Allegis Group").is_staffing
    True
    >>> classify_staffing("Google").is_staffing
    False
    """
    key = normalize_employer(company)
    name = str(company or "")
    if key in HARD_BLOCK:
        return StaffingFlag(True, PENALTY_LISTED, "hard_block_listed", hard_block=True)
    if key in STAFFING_AGENCIES:
        return StaffingFlag(True, PENALTY_LISTED, "known_staffing_agency")
    if _STAFFING_NAME_RE.search(name):
        return StaffingFlag(True, PENALTY_HEURISTIC, "staffing_name_pattern")
    if description and _STAFFING_JD_RE.search(description):
        return StaffingFlag(True, PENALTY_HEURISTIC, "staffing_jd_language")
    return StaffingFlag(False)


def apply_staffing_flag(job: dict) -> dict:
    """Annotate a job dict in place with staffing flags + rank penalty.

    Non-destructive: never changes ``status``. Returns the same dict for
    chaining. Wire this into the loader after normalization.
    """
    flag = classify_staffing(job.get("company") or job.get("company_name"), job.get("description", ""))
    if flag.is_staffing:
        meta = job.setdefault("extra_metadata", {})
        meta["staffing_agency"] = True
        meta["staffing_reason"] = flag.reason
        job["rank_penalty"] = float(job.get("rank_penalty", 0.0)) + flag.penalty
    return job

"""Employer-name normalization + H-1B approval-rate resolution (A4).

Two distinct bugs in the visa enrichment surfaced as "0% approval":

  1. *Join misses.* The LCA / USCIS Employer Data Hub is keyed on the legal
     entity name. A scraped ``company`` like "Yoh - A Day & Zimmerman Company"
     or "TEKsystems c/o Allegis Group" never string-matches the registry, so
     the join returns nothing.
  2. *0 vs. unknown.* When the join misses, the old code defaulted the
     approval rate to ``0`` and the UI rendered "0% approval" — which reads as
     "this sponsor is rejected every time" rather than "we have no data".

:func:`normalize_employer` produces a stable join key (suffix-stripped,
lowercased, punctuation-collapsed). :func:`resolve_approval_rate` returns
``None`` for a miss so callers can render "—"/"unknown" instead of "0%".
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

# Legal/commercial suffixes to strip from the tail of an employer name.
_SUFFIXES = (
    "incorporated", "corporation", "company", "limited", "holdings",
    "inc", "llc", "llp", "lp", "ltd", "plc", "co", "corp", "gmbh", "ag",
    "sa", "sas", "srl", "bv", "nv", "pvt", "pte", "pty",
)
_SUFFIX_RE = re.compile(
    r"[\s,]*(?:"
    + "|".join(re.escape(s) for s in _SUFFIXES)
    + r")\.?\s*$",
    re.I,
)
# "c/o Allegis Group", "dba BrandName", "a Day & Zimmerman company" tails.
_CO_RE = re.compile(r"\s*(?:c/?o|dba|d/b/a|a\s+\w[\w &]*\s+company)\b.*$", re.I)
_PAREN_RE = re.compile(r"\([^)]*\)")
_NONWORD_RE = re.compile(r"[^a-z0-9 ]+")
_WS_RE = re.compile(r"\s+")
_AMP_RE = re.compile(r"\s*&\s*")


def normalize_employer(name: Optional[str]) -> str:
    """Return a stable lowercase join key for LCA / USCIS matching.

    >>> normalize_employer("Yoh - A Day & Zimmerman Company")
    'yoh'
    >>> normalize_employer("TEKsystems c/o Allegis Group")
    'teksystems'
    >>> normalize_employer("Amtex System Inc.")
    'amtex system'
    >>> normalize_employer("Google LLC")
    'google'
    """
    text = str(name or "").strip()
    if not text:
        return ""
    text = _PAREN_RE.sub(" ", text)
    text = text.replace("’", "'")
    text = _AMP_RE.sub(" and ", text)
    text = _CO_RE.sub("", text)
    # Drop a leading-entity tail like " - A Day Zimmerman ...".
    text = re.split(r"\s[-–—]\s", text)[0]
    text = text.lower()
    text = _NONWORD_RE.sub(" ", text)
    text = _WS_RE.sub(" ", text).strip()
    # Strip trailing legal suffixes (may repeat: "Foo Inc LLC").
    prev = None
    while prev != text:
        prev = text
        text = _SUFFIX_RE.sub("", text).strip()
    return text


@dataclass(frozen=True)
class ApprovalResult:
    """Outcome of an H-1B approval-rate lookup.

    ``rate is None`` => no registry match (render "unknown" / "—").
    ``matched is False`` distinguishes a genuine miss from a real 0.0.
    """

    rate: Optional[float]
    matched: bool
    approvals: int = 0
    denials: int = 0
    matched_name: Optional[str] = None


def resolve_approval_rate(
    employer: Optional[str],
    registry: dict[str, dict],
) -> ApprovalResult:
    """Look up an employer in a normalized H-1B registry.

    *registry* maps ``normalize_employer(name) -> {"approvals": int,
    "denials": int, "name": str}``. Build it once from the USCIS hub /
    LCA data using the same :func:`normalize_employer` key.

    Returns ``ApprovalResult(rate=None, matched=False)`` on a miss so the
    frontend can show "unknown" rather than a misleading 0%.
    """
    key = normalize_employer(employer)
    if not key:
        return ApprovalResult(rate=None, matched=False)
    row = registry.get(key)
    if row is None:
        return ApprovalResult(rate=None, matched=False)
    approvals = int(row.get("approvals", 0) or 0)
    denials = int(row.get("denials", 0) or 0)
    total = approvals + denials
    if total <= 0:
        # Matched the entity but it filed no decided petitions — still unknown,
        # not "0% approved".
        return ApprovalResult(
            rate=None, matched=True, approvals=approvals,
            denials=denials, matched_name=row.get("name"),
        )
    return ApprovalResult(
        rate=round(approvals / total * 100, 1),
        matched=True,
        approvals=approvals,
        denials=denials,
        matched_name=row.get("name"),
    )


def build_registry(rows: list[dict]) -> dict[str, dict]:
    """Index raw sponsor rows by normalized employer key.

    Each row needs an employer name field (``employer``/``name``/``company``)
    plus ``approvals`` and ``denials`` (or ``initial_approvals`` etc.).
    Later rows for the same key are merged (counts summed).
    """
    out: dict[str, dict] = {}
    for row in rows:
        name = row.get("employer") or row.get("name") or row.get("company") or ""
        key = normalize_employer(name)
        if not key:
            continue
        approvals = int(
            row.get("approvals")
            or (row.get("initial_approvals", 0) or 0) + (row.get("continuing_approvals", 0) or 0)
        )
        denials = int(
            row.get("denials")
            or (row.get("initial_denials", 0) or 0) + (row.get("continuing_denials", 0) or 0)
        )
        if key in out:
            out[key]["approvals"] += approvals
            out[key]["denials"] += denials
        else:
            out[key] = {"approvals": approvals, "denials": denials, "name": name}
    return out

"""Resolve third-party job postings to the company's official career page.

Pipeline position: jobs scraped from LinkedIn / Dice / Glassdoor / Indeed give
us (company, title, location). This module tries to find the same opening on
the employer's own careers site so the "Apply on Company Website" button sends
the candidate to the source — and so we can pull a complete, first-party JD.

Resolution order:
    1. Probe public ATS board APIs using slug candidates derived from the
       company name.
       If a board exists, fuzzy-match the job title (+ location bonus).
    2. Fall back to the company's corporate domain (curated sponsor map first,
       then conservative guess) and probe standard careers paths.
    3. If nothing is found, return None — caller keeps the third-party link.

All lookups are cached in-process per company to avoid hammering ATS APIs.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Optional
from urllib.parse import urlparse

import httpx

from app.services.careers_ats import scrape_ats
from app.services.sponsor_domains import best_domain, is_safe_domain

logger = logging.getLogger(__name__)

# ATS platforms with cheap public JSON probes (board token = company slug).
PROBE_ATS = (
    "greenhouse",
    "lever",
    "ashby",
    "smartrecruiters",
    "recruitee",
    "workable",
    "personio",
    "teamtailor",
    "jazzhr",
    "rippling",
    "bamboohr",
)

# Common careers paths to probe on the corporate domain, in order.
CAREERS_PATHS = (
    "/careers",
    "/careers/",
    "/careers/search",
    "/careers/jobs",
    "/jobs",
    "/jobs/",
    "/jobs/search",
    "/en/careers",
    "/en/careers/jobs",
    "/en/jobs",
    "/en-us/careers",
    "/en-us/jobs",
    "/company/careers",
    "/company/jobs",
    "/about/careers",
    "/join",
    "/join-us",
    "/work-with-us",
    "/recruiting/jobs",
    "/job-openings",
)

TITLE_MATCH_THRESHOLD = 0.78
CACHE_TTL_SECONDS = 6 * 3600
MAX_CACHE_ENTRIES = 4000

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/json;q=0.9,*/*;q=0.8",
}

_LEGAL_SUFFIX_RE = re.compile(
    r"\b(incorporated|technologies|technology|corporation|consulting|solutions|"
    r"services|systems|holdings|company|group|global|labs|inc|llc|ltd|corp|co|plc|gmbh)\b\.?",
    re.I,
)
_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")


@dataclass(slots=True)
class CompanyLink:
    """Resolved official link for a scraped third-party posting."""

    url: str
    link_type: str  # "ats_posting" | "careers_page"
    ats: Optional[str] = None
    company_domain: Optional[str] = None
    description: Optional[str] = None
    matched_title: Optional[str] = None
    confidence: float = 0.0

    def to_metadata(self) -> dict:
        return {
            "url": self.url,
            "link_type": self.link_type,
            "ats": self.ats,
            "company_domain": self.company_domain,
            "matched_title": self.matched_title,
            "confidence": round(self.confidence, 3),
        }


@dataclass(slots=True)
class _BoardCache:
    """Per-company cache of ATS board postings (or the negative result)."""

    expires: float
    ats: Optional[str] = None
    postings: list = field(default_factory=list)
    careers_url: Optional[str] = None
    domain: Optional[str] = None


_company_cache: dict[str, _BoardCache] = {}
_cache_lock = asyncio.Lock()


def _normalize_company(name: str) -> str:
    return _NON_ALNUM_RE.sub(" ", (name or "").lower()).strip()


def _slug_candidates(company: str) -> list[str]:
    """Generate plausible ATS board tokens from a company name."""
    base = _normalize_company(company)
    if not base:
        return []
    stripped = _LEGAL_SUFFIX_RE.sub(" ", base).strip()
    words = [w for w in stripped.split() if w]
    candidates: list[str] = []

    def _add(token: str) -> None:
        token = token.strip("-")
        alpha = re.sub(r"[^a-z]", "", token)
        digits = re.sub(r"\D", "", token)
        if digits and len(digits) >= len(alpha):
            return
        if token and len(alpha) >= 3 and len(token) >= 3 and token not in candidates:
            candidates.append(token)

    if words:
        _add("".join(words))          # delltechnologies
        _add("-".join(words))         # dell-technologies
        _add(words[0])                # dell
        if len(words) >= 2:
            _add("".join(words[:2]))  # first two words joined
    return candidates[:4]


def _title_similarity(a: str, b: str) -> float:
    na, nb = _normalize_company(a), _normalize_company(b)
    if not na or not nb:
        return 0.0
    ratio = SequenceMatcher(None, na, nb).ratio()
    # Token containment bonus: "Sr Systems Engineer" vs "Senior Systems Engineer"
    ta, tb = set(na.split()), set(nb.split())
    if ta and tb:
        overlap = len(ta & tb) / min(len(ta), len(tb))
        ratio = max(ratio, 0.55 * ratio + 0.45 * overlap)
    return ratio


def _location_bonus(job_location: str, posting_location: str) -> float:
    ja = set(_normalize_company(job_location).split())
    jb = set(_normalize_company(posting_location).split())
    if not ja or not jb:
        return 0.0
    return 0.06 if ja & jb else 0.0


async def _probe_ats_boards(company: str) -> tuple[Optional[str], list]:
    """Try slug candidates against public ATS APIs; first board with postings wins."""
    for slug in _slug_candidates(company):
        for ats_name in PROBE_ATS:
            try:
                postings = await scrape_ats(ats_name, slug, max_jobs=500)
            except Exception as exc:  # noqa: BLE001 — probe must never raise
                logger.debug("ATS probe %s/%s failed: %s", ats_name, slug, exc)
                continue
            if postings:
                # Sanity check: the board actually belongs to this company.
                board_company = _normalize_company(getattr(postings[0], "company", "") or slug)
                if board_company and _title_similarity(board_company, company) < 0.55 \
                        and slug not in board_company.replace(" ", ""):
                    continue
                logger.info("ATS board found for %r: %s/%s (%d postings)", company, ats_name, slug, len(postings))
                return ats_name, postings
    return None, []


_PRIVATE_HOST_RE = re.compile(
    r"^(localhost|127\.|10\.|192\.168\.|169\.254\.|0\.|\[|::1)|\.(local|internal|lan|corp|home)$"
    r"|^\d{1,3}(\.\d{1,3}){3}$",
    re.I,
)


def _is_probeable_public_domain(domain: str) -> bool:
    """SSRF guard: only probe public, name-based hosts over HTTPS."""
    d = (domain or "").strip().lower().rstrip(".")
    if not d or "/" in d or ":" in d or "@" in d:
        return False
    if _PRIVATE_HOST_RE.search(d):
        return False
    return is_safe_domain(d)


async def _probe_careers_page(company: str) -> tuple[Optional[str], Optional[str]]:
    """Find a reachable careers page on the company's corporate domain."""
    domain = best_domain(company)
    if not domain or not _is_probeable_public_domain(domain):
        return None, None
    async with httpx.AsyncClient(
        headers=_HEADERS, timeout=8.0, follow_redirects=True, verify=True
    ) as client:
        for path in CAREERS_PATHS:
            url = f"https://{domain}{path}"
            try:
                resp = await client.get(url)
            except Exception:
                continue
            if resp.status_code < 400:
                final = str(resp.url)
                # Refuse redirects that bounce to an unrelated host.
                host = (urlparse(final).hostname or "").lower()
                if domain.split(".")[0] in host or host.endswith(domain):
                    return final, domain
        # Root domain reachable? Still useful as a company link of last resort.
        try:
            resp = await client.get(f"https://{domain}")
            if resp.status_code < 400:
                return None, domain
        except Exception:
            pass
    return None, domain


async def _get_company_intel(company: str) -> _BoardCache:
    key = _normalize_company(company)
    now = time.monotonic()
    async with _cache_lock:
        cached = _company_cache.get(key)
        if cached and cached.expires > now:
            return cached

    ats_name, postings = await _probe_ats_boards(company)
    careers_url = None
    domain = None
    if not postings:
        careers_url, domain = await _probe_careers_page(company)

    entry = _BoardCache(
        expires=now + CACHE_TTL_SECONDS,
        ats=ats_name,
        postings=postings,
        careers_url=careers_url,
        domain=domain,
    )
    async with _cache_lock:
        if len(_company_cache) >= MAX_CACHE_ENTRIES:
            # Drop expired entries first; if still full, drop oldest.
            for k in [k for k, v in _company_cache.items() if v.expires <= now]:
                _company_cache.pop(k, None)
            while len(_company_cache) >= MAX_CACHE_ENTRIES and _company_cache:
                _company_cache.pop(next(iter(_company_cache)))
        _company_cache[key] = entry
    return entry


async def get_board_postings(company: str) -> list:
    """All open postings on the company's ATS board (cached; no extra network
    cost after resolve_company_job has probed the same company).

    Used by the company-link worker to harvest ENTIRE boards: one scraped
    LinkedIn job leads us to the employer's ATS, and from there we ingest
    every open position with first-party data and direct apply links.
    """
    try:
        intel = await _get_company_intel(company)
    except Exception as exc:  # noqa: BLE001
        logger.debug("Board postings lookup failed for %r: %s", company, exc)
        return []
    return list(intel.postings or [])


async def resolve_company_job(
    company: str,
    title: str,
    location: str = "",
) -> Optional[CompanyLink]:
    """Find the official company posting (or careers page) for a scraped job.

    Returns None when nothing trustworthy is found — callers must keep the
    third-party link in that case.
    """
    company = (company or "").strip()
    title = (title or "").strip()
    if not company or not title:
        return None

    try:
        intel = await _get_company_intel(company)
    except Exception as exc:  # noqa: BLE001 — resolution must never break ingestion
        logger.warning("Company intel lookup failed for %r: %s", company, exc)
        return None

    # 1. Exact posting on the company's ATS board.
    if intel.postings:
        best, best_score = None, 0.0
        for posting in intel.postings:
            p_title = getattr(posting, "title", "") or ""
            score = _title_similarity(title, p_title)
            score += _location_bonus(location, getattr(posting, "location", "") or "")
            if score > best_score:
                best, best_score = posting, score
        if best is not None and best_score >= TITLE_MATCH_THRESHOLD:
            url = (getattr(best, "job_url", "") or "").strip()
            if url:
                return CompanyLink(
                    url=url,
                    link_type="ats_posting",
                    ats=intel.ats,
                    description=(getattr(best, "description", "") or "").strip() or None,
                    matched_title=getattr(best, "title", None),
                    confidence=min(1.0, best_score),
                )

    # 2. Careers page on the corporate domain.
    if intel.careers_url:
        return CompanyLink(
            url=intel.careers_url,
            link_type="careers_page",
            company_domain=intel.domain,
            confidence=0.5,
        )

    return None

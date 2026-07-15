"""
PlaceUp Career — Jobs API Routes
Endpoints for listing, filtering, and scraping job postings.
"""

import logging
import math
import os
import re
import html
import copy
import hashlib
import json
import time
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, BackgroundTasks, Body, Depends, Header, HTTPException, Query
from typing import Any, Optional

from app.db import user_store
from app.dependencies import get_db
from app.job_taxonomy import CATEGORIES, categorize, to_payload
from app.models.job import (
    JobPost, JobFilter, JobListResponse, JobStats,
    ScrapeRequest, ScrapeResult, JobSource, JobCategory,
)
from app.security import decode_access_token, optional_user_id, require_internal_api_key
from app.config import settings
from app.services.job_exporter import export_jobs
from app.services.job_description_details import (
    clean_description_text,
    fetch_full_job_description,
    is_html_fetch_allowed,
    is_thin_description,
)
from app.services.global_visa_rules import (
    COUNTRY_RULES,
    country_options,
    normalize_country_code,
    resolve_country,
    visa_program_options,
)
from app.services.apply.tiers import infer_ats_type, is_one_click_ready, parse_credentialed
from app.utils.job_quality import (
    has_complete_job_description,
    has_usable_job_description,
    is_probably_fake_or_scam_job,
    sanitize_job_description_html,
)
from app.utils.terminal_table import render_table

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/jobs", tags=["Jobs"])
DEFAULT_VISIBLE_MAX_AGE_HOURS = 24
DEFAULT_RECENT_JOB_HOURS = 8
_detail_repair_recent: dict[str, datetime] = {}
_match_score_cache: dict[str, tuple[datetime, int]] = {}
_MATCH_SCORE_CACHE_TTL = timedelta(minutes=30)
_MATCH_SCORE_CACHE_MAX = 20000
_USER_CONTEXT_CACHE_TTL_SECONDS = 60
_user_preference_cache: dict[str, tuple[float, tuple[list[str], list[str]]]] = {}
_active_resume_text_cache: dict[str, tuple[float, str, Optional[str]]] = {}
_FAST_RESPONSE_CACHE_TTL_SECONDS = 45
_FAST_RESPONSE_CACHE_MAX = 250
_fast_response_cache: dict[str, tuple[float, dict]] = {}


async def fast_optional_user_id(
    authorization: Optional[str] = Header(default=None, alias="Authorization"),
) -> Optional[str]:
    """Decode identity for optional/personalized reads without Firestore roundtrips."""
    if not authorization or not authorization.lower().startswith("bearer "):
        return None
    try:
        claims = decode_access_token(authorization.split(" ", 1)[1].strip())
        user_id = claims.get("sub")
        return str(user_id) if user_id else None
    except Exception:
        return None


def _description_quality(title: str, description: str) -> dict[str, Any]:
    """Decide whether a posting has enough JD text for ATS scoring."""
    title_clean = re.sub(r"\s+", " ", html.unescape(title or "")).strip().lower()
    desc = html.unescape(description or "")
    desc = re.sub(r"<[^>]+>", " ", desc)
    desc = re.sub(r"\s+", " ", desc).strip()
    stripped = desc.lower()
    if title_clean:
        stripped = re.sub(rf"^(?:{re.escape(title_clean)}\s*){{1,3}}", "", stripped).strip()
    words = re.findall(r"\b[a-z][a-z0-9+#./-]*\b", stripped)
    has_jd_marker = bool(re.search(
        r"(?i)\b(about the job|description|responsibilities|qualifications|requirements|"
        r"what you'?ll do|minimum requirements|basic qualifications|job duties)\b",
        desc,
    ))
    has_action_content = len(re.findall(
        r"(?i)\b(design|build|develop|manage|lead|implement|collaborate|monitor|"
        r"secure|analyze|maintain|support|architect|drive|own|create)\b",
        desc,
    )) >= 3
    scorable = len(words) >= 55 or (len(words) >= 35 and (has_jd_marker or has_action_content))
    return {"scorable": scorable, "word_count": len(words), "char_count": len(desc)}


def _can_score_job_text(title: str, description: str) -> bool:
    return bool(_description_quality(title, description).get("scorable"))

SPONSORSHIP_BLOCK_RE = re.compile(
    r"(?i)\b("
    r"no\s+(?:visa\s+)?sponsorship|"
    r"not\s+(?:able|eligible|willing)\s+to\s+(?:offer\s+)?(?:visa\s+)?sponsorship|"
    r"not\s+(?:able|eligible|willing)\s+to\s+(?:offer\s+)?visa\s+transfer\s+or\s+sponsorship|"
    r"(?:will|can|do)\s+not\s+sponsor|"
    r"unable\s+to\s+sponsor|"
    r"cannot\s+sponsor|"
    r"without\s+sponsorship|"
    r"without\s+(?:visa\s+)?transfer\s+or\s+sponsorship|"
    r"without\s+(?:current\s+)?(?:or\s+future\s+)?sponsorship|"
    r"authorized\s+to\s+work\s+.*without\s+sponsorship|"
    r"u\.?s\.?\s+citizens?\s+only|"
    r"citizenship\s+required|"
    r"(?:secret|top\s+secret|ts[./\-\s]*sci|sci)\s+clearance\s+required|"
    r"minimum\s+clearance\s+required\s*:\s*(?:secret|top\s+secret|ts[./\-\s]*sci)|"
    r"clearance\s+level\s+must\s+be\s+able\s+to\s+obtain\s*:\s*(?:secret|top\s+secret|ts[./\-\s]*sci)|"
    r"active\s+(?:dod\s+)?(?:secret|top\s+secret|ts[./\-\s]*sci)\s+clearance"
    r")\b"
)


def _apply_job_specific_visa_rules(job: dict) -> dict:
    """Let explicit JD work-authorization text override broad employer signals."""
    visa = job.get("visa")
    if not isinstance(visa, dict):
        return job
    text = html.unescape(f"{job.get('title') or ''}\n{job.get('description') or ''}")
    if not SPONSORSHIP_BLOCK_RE.search(text):
        return job
    updated = dict(job)
    updated["visa"] = {
        **visa,
        "visa_opt": False,
        "visa_stem_opt": False,
        "visa_h1b": False,
        "h1b_verified": False,
        "visa_score": 0,
        "no_sponsorship": True,
    }
    return updated


def _should_schedule_detail_repair(job: dict) -> bool:
    description = clean_description_text(job.get("description") or "")
    if not is_thin_description(description, min_chars=1200, min_words=120):
        return False
    url = str(job.get("job_url") or job.get("source_url") or job.get("job_url_direct") or "").strip()
    if not url or not is_html_fetch_allowed(url):
        return False
    job_id = str(job.get("id") or "")
    now = datetime.now(timezone.utc)
    last = _detail_repair_recent.get(job_id)
    if last and (now - last).total_seconds() < 900:
        return False
    _detail_repair_recent[job_id] = now
    if len(_detail_repair_recent) > 5000:
        cutoff = now - timedelta(hours=2)
        for key, value in list(_detail_repair_recent.items()):
            if value < cutoff:
                _detail_repair_recent.pop(key, None)
    return True


async def _repair_detail_description_background(job: dict, db) -> None:
    """Expand a thin direct-company JD after the user-facing response."""
    description = clean_description_text(job.get("description") or "")
    url = str(job.get("job_url") or job.get("source_url") or job.get("job_url_direct") or "").strip()
    details = await fetch_full_job_description(url, timeout=12.0, expand_links=True)
    if not details:
        return
    repaired = clean_description_text(details.description)
    if not has_complete_job_description(repaired) or len(repaired) <= len(description):
        return
    meta = dict(job.get("extra_metadata") or {})
    meta["description_hydrated"] = True
    meta["description_hydrated_from"] = details.source_url
    meta["description_extractor"] = details.extractor
    meta["description_hydrated_on_detail"] = True
    try:
        update_description = getattr(db, "update_job_description", None)
        if update_description:
            await update_description(
                str(job.get("id") or ""),
                repaired,
                source_url=details.source_url or url,
                extra_metadata=meta,
            )
    except Exception as exc:
        logger.debug("Unable to persist repaired JD for %s: %s", job.get("id"), exc)


# ── Stale-if-error cache for the Jobs list ──────────────────────────────────
# Keeps the site readable while the scraper (or any incident) saturates the
# database. Entries live 30 minutes and the cache is capped to 2000 pages.
_STALE_JOBS_TTL_SECONDS = 30 * 60
_STALE_JOBS_MAX_ENTRIES = 2000
_stale_jobs_cache: "dict[str, tuple[float, dict]]" = {}


def _store_stale_jobs_response(key: str, payload: dict) -> None:
    import time as _time
    now = _time.monotonic()
    if len(_stale_jobs_cache) >= _STALE_JOBS_MAX_ENTRIES:
        expired = [k for k, (at, _) in _stale_jobs_cache.items() if now - at > _STALE_JOBS_TTL_SECONDS]
        for k in expired:
            _stale_jobs_cache.pop(k, None)
        while len(_stale_jobs_cache) >= _STALE_JOBS_MAX_ENTRIES and _stale_jobs_cache:
            _stale_jobs_cache.pop(next(iter(_stale_jobs_cache)))
    _stale_jobs_cache[key] = (now, payload)


def _get_stale_jobs_response(key: str) -> "dict | None":
    import time as _time
    entry = _stale_jobs_cache.get(key)
    if not entry:
        return None
    at, payload = entry
    if _time.monotonic() - at > _STALE_JOBS_TTL_SECONDS:
        _stale_jobs_cache.pop(key, None)
        return None
    return payload


# Sources already serving first-party employer data — everything NOT in this
# set is an intermediary and qualifies for company-page resolution. Inverted
# (vs. listing portals) so country job boards in registry-less countries
# (EURES, MyCareersFuture, France Travail, Jobbank CA, ...) are covered too.
from app.scrape_constants import FIRST_PARTY_ATS_SOURCES

_FIRST_PARTY_SOURCES = set(FIRST_PARTY_ATS_SOURCES)
_company_link_recent: dict[str, datetime] = {}

# 5-minute cache of exact inventory counts for personalized/role feeds.
_title_count_cache: dict[str, tuple[float, int]] = {}


def _resume_signature(resume_text: Optional[str]) -> str:
    if not resume_text:
        return "none"
    return hashlib.sha1(resume_text[:50000].encode("utf-8", "ignore")).hexdigest()[:16]


def _stable_cache_key(namespace: str, payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
    return f"{namespace}:{hashlib.sha1(raw.encode('utf-8', 'ignore')).hexdigest()}"


def _cache_copy(payload: dict) -> dict:
    return copy.deepcopy(payload)


def _get_fast_response(key: str) -> Optional[dict]:
    entry = _fast_response_cache.get(key)
    if not entry:
        return None
    at, payload = entry
    age = time.monotonic() - at
    if age > _FAST_RESPONSE_CACHE_TTL_SECONDS:
        _fast_response_cache.pop(key, None)
        return None
    cached = _cache_copy(payload)
    cached["cached"] = True
    cached["cache_age_seconds"] = round(age, 3)
    return cached


def _store_fast_response(key: str, payload: dict) -> None:
    now = time.monotonic()
    if len(_fast_response_cache) >= _FAST_RESPONSE_CACHE_MAX:
        expired = [k for k, (at, _) in _fast_response_cache.items() if now - at > _FAST_RESPONSE_CACHE_TTL_SECONDS]
        for k in expired:
            _fast_response_cache.pop(k, None)
        while len(_fast_response_cache) >= _FAST_RESPONSE_CACHE_MAX and _fast_response_cache:
            _fast_response_cache.pop(next(iter(_fast_response_cache)))
    _fast_response_cache[key] = (now, _cache_copy(payload))


def invalidate_user_job_caches(user_id: Optional[str] = None) -> None:
    """Clear short-lived jobs caches after resume/preference mutations."""
    if user_id:
        _user_preference_cache.pop(user_id, None)
        _active_resume_text_cache.pop(user_id, None)
    _fast_response_cache.clear()


def _should_schedule_company_link(job: dict) -> bool:
    """Schedule official-careers-page resolution for third-party postings."""
    source = str(job.get("source") or job.get("source_name") or "").lower()
    if not source or source in _FIRST_PARTY_SOURCES:
        return False
    meta = job.get("extra_metadata") or {}
    if isinstance(meta, dict) and (meta.get("company_link_checked") or meta.get("company_link")):
        return False
    if not (job.get("company") and job.get("title")):
        return False
    job_id = str(job.get("id") or "")
    now = datetime.now(timezone.utc)
    last = _company_link_recent.get(job_id)
    if last and (now - last).total_seconds() < 3600:
        return False
    _company_link_recent[job_id] = now
    if len(_company_link_recent) > 5000:
        cutoff = now - timedelta(hours=4)
        for key, value in list(_company_link_recent.items()):
            if value < cutoff:
                _company_link_recent.pop(key, None)
    return True


async def _resolve_company_link_background(job: dict, db) -> None:
    """Find the employer's official posting/careers page after the response is sent."""
    try:
        from app.services.company_career_resolver import resolve_company_job

        link = await resolve_company_job(
            str(job.get("company") or ""),
            str(job.get("title") or ""),
            str(job.get("location") or ""),
        )
        metadata: dict = {"company_link_checked": datetime.now(timezone.utc).isoformat()}
        description = None
        if link is not None:
            metadata["company_link"] = link.to_metadata()
            if link.description:
                current = clean_description_text(job.get("description") or "")
                candidate = clean_description_text(link.description)[:60000]
                if len(candidate) > max(len(current) + 300, 600):
                    description = candidate
        merge = getattr(db, "merge_job_metadata", None)
        if merge:
            await merge(str(job.get("id") or ""), metadata, description=description)
    except Exception as exc:  # noqa: BLE001 — background enrichment must never raise
        logger.debug("Company link resolution failed for %s: %s", job.get("id"), exc)


def _prepare_resume_tokens(resume_text: str) -> dict:
    """Pre-tokenize the resume once so per-job scoring is fast.

    Called ONCE per list request, then re-used across every job. Without
    this cache, _score_job_against_resume tokenized the resume on every
    iteration — turning a 40-job page into 40 redundant NLP passes, which
    is exactly what made the Today / Yesterday filters feel slow.
    """
    if not resume_text:
        return {}
    try:
        from app.utils.text_processing import (
            clean_text, extract_relevant_keywords, extract_skills_from_text,
        )
        resume_text = html.unescape(resume_text)
        resume_clean = clean_text(resume_text).lower()
        r_skills = list(dict.fromkeys(extract_skills_from_text(resume_text)))
        r_kw = list(dict.fromkeys(r_skills + extract_relevant_keywords(resume_text, top_n=70)))
        return {
            "raw": resume_text,
            "clean": resume_clean,
            "skills": r_skills,
            "keywords": r_kw,
        }
    except Exception:
        return {}


_SENIORITY_WORDS = {
    "intern": 0, "internship": 0, "entry": 1, "junior": 1, "associate": 2,
    "mid": 4, "senior": 6, "sr": 6, "staff": 8, "principal": 9, "lead": 8,
    "manager": 7, "director": 10, "head": 10,
}


def _extract_years_required(text: str) -> int | None:
    matches = re.findall(
        r"(?i)\b(\d{1,2})\+?\s*(?:-\s*\d{1,2})?\s*(?:years?|yrs?)\s+(?:of\s+)?(?:professional\s+)?(?:experience|exp)\b",
        text or "",
    )
    if not matches:
        return None
    try:
        return max(int(v) for v in matches)
    except ValueError:
        return None


def _resume_years_hint(resume_text: str) -> int | None:
    matches = re.findall(
        r"(?i)\b(\d{1,2})\+?\s*(?:years?|yrs?)\s+(?:of\s+)?(?:professional\s+)?(?:experience|exp)\b",
        resume_text or "",
    )
    if not matches:
        return None
    try:
        return max(int(v) for v in matches)
    except ValueError:
        return None


def _seniority_level(text: str) -> int:
    low = f" {html.unescape(text or '').lower()} "
    level = 3
    for word, value in _SENIORITY_WORDS.items():
        if re.search(rf"\b{re.escape(word)}\b", low):
            level = max(level, value)
    years = _extract_years_required(low)
    if years is not None:
        level = max(level, min(10, years))
    return level


def _required_text(text: str) -> str:
    clean = html.unescape(text or "")
    sections = re.split(
        r"(?i)\b(preferred qualifications|nice to have|benefits|perks|about us|equal opportunity)\b",
        clean,
        maxsplit=1,
    )[0]
    match = re.search(
        r"(?is)\b(requirements?|qualifications?|minimum qualifications?|basic qualifications?|must have|what you bring)\b[:\s-]*(.+)",
        sections,
    )
    return match.group(2) if match else sections


def _role_title_score(resume_text: str, title: str) -> float:
    title_tokens = [
        token for token in re.findall(r"\b[a-z][a-z+#./-]{2,}\b", (title or "").lower())
        if token not in {"senior", "staff", "lead", "principal", "junior", "associate", "manager", "remote", "engineer", "analyst"}
    ][:8]
    if not title_tokens:
        return 50.0
    resume = html.unescape(resume_text or "").lower()
    hits = sum(1 for token in title_tokens if re.search(rf"\b{re.escape(token)}\b", resume))
    return hits / len(title_tokens) * 100


def _ats_score_v2(resume_text: str, job_text: str, *, resume_cache: Optional[dict] = None) -> dict[str, Any]:
    from app.utils.text_processing import (
        clean_text,
        compute_keyword_overlap,
        extract_relevant_keywords,
        extract_skills_from_text,
    )

    title, _, body = job_text.partition("\n")
    r_skills = list(dict.fromkeys((resume_cache.get("skills") or []) if resume_cache else extract_skills_from_text(resume_text)))
    r_kw = list(dict.fromkeys((resume_cache.get("keywords") or []) if resume_cache else (r_skills + extract_relevant_keywords(resume_text, top_n=80))))
    resume_clean = clean_text(resume_text).lower()
    job_clean = clean_text(job_text).lower()
    required = _required_text(job_text)

    jd_skills = list(dict.fromkeys(extract_skills_from_text(job_text)))
    required_skills = list(dict.fromkeys(extract_skills_from_text(required))) or jd_skills[:12]
    preferred_text = re.split(r"(?i)\b(preferred qualifications|nice to have|bonus|preferred skills)\b", job_text, maxsplit=1)
    preferred = preferred_text[2] if len(preferred_text) >= 3 else ""
    preferred_skills = [skill for skill in extract_skills_from_text(preferred) if skill not in required_skills]
    jd_keywords = [kw for kw in extract_relevant_keywords(job_text, top_n=60) if _is_real_skill(kw)]
    required_keywords = [kw for kw in extract_relevant_keywords(required, top_n=32) if _is_real_skill(kw)]

    matched_skills, missing_skills, skill_pct = compute_keyword_overlap(r_skills, jd_skills) if jd_skills else ([], [], 0)
    required_pool = list(dict.fromkeys(required_skills + required_keywords))
    matched_required, missing_required, required_pct = compute_keyword_overlap(r_kw, required_pool) if required_pool else ([], [], skill_pct)
    matched_keywords, missing_keywords, keyword_pct = compute_keyword_overlap(r_kw, list(dict.fromkeys(jd_skills + jd_keywords))) if (jd_skills or jd_keywords) else ([], [], 0)
    title_pct = _role_title_score(resume_text, title)

    resume_years = _resume_years_hint(resume_text)
    required_years = _extract_years_required(job_text)
    seniority_gap = 0.0
    if required_years is not None and resume_years is not None and resume_years + 1 < required_years:
        seniority_gap = min(45.0, (required_years - resume_years) * 10.0)
    elif _seniority_level(title) >= 7 and _seniority_level(resume_text[:1200]) <= 3:
        seniority_gap = 35.0

    hard_skill_score = required_pct
    if required_skills or preferred_skills:
        required_weight = max(1, len(required_skills)) * 2
        preferred_weight = max(0, len(preferred_skills))
        required_hits = sum(1 for skill in required_skills if skill in matched_required or skill in matched_skills)
        preferred_hits = sum(1 for skill in preferred_skills if skill in r_skills or skill in r_kw)
        hard_skill_score = ((required_hits * 2 + preferred_hits) / max(1, required_weight + preferred_weight)) * 100

    experience_score = max(0.0, min(100.0, (title_pct * 0.45) + 55.0 - seniority_gap))
    if required_years is not None and resume_years is None:
        experience_score = min(experience_score, 58.0)
    elif required_years is not None and resume_years is not None and resume_years >= required_years:
        experience_score = max(experience_score, 75.0)

    degree_terms = ("bachelor", "master", "phd", "degree", "computer science", "engineering", "statistics", "mba")
    cert_terms = ("certification", "certified", "cissp", "security+", "aws certified", "pmp", "cpa", "rn")
    jd_education_terms = [term for term in degree_terms + cert_terms if term in job_clean]
    matched_education = [term for term in jd_education_terms if term in resume_clean]
    if not jd_education_terms or "equivalent experience" in job_clean:
        education_score = 80.0 if any(term in resume_clean for term in degree_terms) else 60.0
    else:
        education_score = len(matched_education) / len(jd_education_terms) * 100

    soft_terms = ("communication", "leadership", "collaborat", "stakeholder", "mentor", "cross-functional", "agile", "scrum", "customer")
    jd_soft_terms = [term for term in soft_terms if term in job_clean]
    matched_soft_terms = [term for term in jd_soft_terms if term in resume_clean]
    soft_score = 70.0 if not jd_soft_terms else len(matched_soft_terms) / len(jd_soft_terms) * 100

    resume_words = len(clean_text(resume_text).split())
    has_sections = sum(1 for section in ("experience", "education", "skills", "projects", "certifications") if section in resume_clean)
    has_metrics = bool(re.search(r"\b\d+%|\$\d+|\b\d+x\b|team of \d+|reduced \d+|increased \d+", resume_text, re.I))
    resume_quality = min(100.0, has_sections * 14.0 + (22.0 if has_metrics else 0.0) + (8.0 if 350 <= resume_words <= 1200 else 0.0))

    authorization_blocked = bool(SPONSORSHIP_BLOCK_RE.search(job_text.lower()))

    score = (
        hard_skill_score * 0.30
        + experience_score * 0.25
        + keyword_pct * 0.15
        + education_score * 0.10
        + soft_score * 0.10
        + resume_quality * 0.10
    )
    if required_skills and not matched_required:
        score = min(score, 42)
    if len(jd_skills) >= 4 and len(matched_skills) <= 1:
        score = min(score, 45)
    if title_pct < 20 and required_pct < 30:
        score = min(score, 42)
    if seniority_gap >= 35:
        score = min(score, 48)
    if authorization_blocked:
        score = min(score, 34)
    if hard_skill_score >= 80 and experience_score >= 75:
        score = min(98, score + 5)

    return {
        "score": int(round(max(6, min(98, score)))),
        "components": {
            "hard_skills": round(hard_skill_score, 1),
            "experience_relevance": round(experience_score, 1),
            "keyword_alignment": round(keyword_pct, 1),
            "education_certs": round(education_score, 1),
            "soft_skills_domain": round(soft_score, 1),
            "resume_quality": round(resume_quality, 1),
            "title_match_pct": round(title_pct, 1),
            "skill_match_pct": round(skill_pct, 1),
            "required_terms_pct": round(required_pct, 1),
            "keyword_overlap_pct": round(keyword_pct, 1),
            "required_years": required_years,
            "resume_years": resume_years,
        },
        "matched_skills": matched_skills[:15],
        "missing_skills": missing_skills[:15],
        "matched_required": matched_required[:15],
        "missing_required": missing_required[:15],
        "matched_keywords": matched_keywords[:15],
        "missing_keywords": missing_keywords[:15],
        "applied_penalties": [
            label for label, active in (
                ("Seniority/years gap", seniority_gap > 0),
                ("Hard requirement gap", required_skills and not matched_required),
                ("Work authorization / clearance block", authorization_blocked),
            ) if active
        ],
    }


def _score_job_against_resume(resume_text: str, job_text: str, *, resume_cache: Optional[dict] = None) -> int:
    """
    Lightweight per-job ATS-style match score (0-100).

    Pass `resume_cache` from _prepare_resume_tokens to skip redundant
    resume tokenization (huge speedup for list endpoints).

    Never returns 0 when the resume + job both have content — falls back
    to a baseline so the UI never shows "0%" for what is actually a
    valid scoring attempt. (Users were complaining "ATS Match Score
    is broken" because borderline matches were silently flooring to 0.)
    """
    if not resume_text or not job_text:
        return 0
    title, _, body = job_text.partition("\n")
    if not _can_score_job_text(title, body):
        return 0
    try:
        return int(_ats_score_v2(resume_text, job_text, resume_cache=resume_cache)["score"])
    except Exception as exc:
        # Log so we can spot scoring regressions, then fall back to a
        # baseline. Returning 0 here is what made the "ATS match score
        # is broken" complaint look like a total failure when it was
        # actually a single bad row poisoning the column.
        logger.warning("ATS match scoring failed (%s); using baseline.", exc)
        return _baseline_ats_score({"title": "", "description": job_text or ""})


def _cached_score_job_against_resume(
    resume_text: str,
    job_text: str,
    *,
    resume_cache: Optional[dict] = None,
    job_id: str = "",
) -> int:
    """Deterministic ATS score with a short in-process cache."""
    if not resume_text or not job_text:
        return 0
    import hashlib

    resume_sig = hashlib.sha1(resume_text[:50000].encode("utf-8", "ignore")).hexdigest()[:16]
    job_sig = hashlib.sha1(job_text[:60000].encode("utf-8", "ignore")).hexdigest()[:16]
    key = f"{resume_sig}:{job_id}:{job_sig}"
    now = datetime.now(timezone.utc)
    cached = _match_score_cache.get(key)
    if cached and now - cached[0] < _MATCH_SCORE_CACHE_TTL:
        return cached[1]
    score = _score_job_against_resume(resume_text, job_text, resume_cache=resume_cache)
    if len(_match_score_cache) > _MATCH_SCORE_CACHE_MAX:
        cutoff = now - _MATCH_SCORE_CACHE_TTL
        for cache_key, (seen_at, _) in list(_match_score_cache.items()):
            if seen_at < cutoff:
                _match_score_cache.pop(cache_key, None)
        if len(_match_score_cache) > _MATCH_SCORE_CACHE_MAX:
            _match_score_cache.clear()
    _match_score_cache[key] = (now, score)
    return score


def score_breakdown(resume_text: str, job_text: str, *, resume_cache: Optional[dict] = None) -> dict:
    """Return an explainable score: the final number AND the inputs that
    went into it. Powers the "Why this score?" tooltip on the Job Detail
    page so users no longer see the match as a black box.

    Returns shape:
        {
          "score": 73,
          "components": {
            "title_match_pct": 60,
            "domain_term_pct": 45,
            "keyword_overlap_pct": 52,
            "skill_match_pct": 65,
            "required_terms_pct": 70,
            "role_coverage_pct": 40,
          },
          "matched_skills": ["python", "aws", "sql"],
          "applied_penalties": ["low role coverage"]  # if any
        }
    """
    if not resume_text or not job_text:
        return {"score": 0, "components": {}, "matched_skills": [], "applied_penalties": ["missing resume or job text"]}
    title, _, body = job_text.partition("\n")
    quality = _description_quality(title, body)
    if not quality["scorable"]:
        return {
            "score": None,
            "components": {"job_description_words": quality["word_count"]},
            "matched_skills": [],
            "applied_penalties": ["Job description too thin for ATS scoring"],
        }
    try:
        return _ats_score_v2(resume_text, job_text, resume_cache=resume_cache)
        from app.utils.text_processing import (
            clean_text, extract_keywords, extract_skills_from_text, compute_keyword_overlap,
        )
        job_clean = clean_text(html.unescape(job_text)).lower()
        if resume_cache:
            resume_clean = resume_cache.get("clean", "")
            r_kw = resume_cache.get("keywords") or []
            r_skills = resume_cache.get("skills") or []
        else:
            resume_clean = clean_text(html.unescape(resume_text)).lower()
            r_skills = list(dict.fromkeys(extract_skills_from_text(resume_text)))
            r_kw = list(dict.fromkeys(r_skills + extract_keywords(resume_text, top_n=70)))

        jd_skills = list(dict.fromkeys(extract_skills_from_text(job_text)))
        jd_kw = list(dict.fromkeys(jd_skills + extract_keywords(job_text, top_n=45)))
        skill_matched, _, skill_pct = compute_keyword_overlap(r_skills, jd_skills) if jd_skills else ([], [], 0)
        _, _, keyword_pct = compute_keyword_overlap(r_kw, jd_kw) if jd_kw else ([], [], 0)
        penalties = []
        if skill_pct < 25:
            penalties.append("Low skill overlap")
        if keyword_pct < 25:
            penalties.append("Low keyword overlap")
        return {
            "score": _score_job_against_resume(resume_text, job_text, resume_cache=resume_cache),
            "components": {
                "skill_match_pct": round(skill_pct, 1),
                "keyword_overlap_pct": round(keyword_pct, 1),
            },
            "matched_skills": skill_matched[:15],
            "applied_penalties": penalties,
        }
    except Exception as exc:
        logger.warning("score_breakdown failed: %s", exc)
        return {"score": 0, "components": {}, "matched_skills": [], "applied_penalties": [str(exc)]}


def _baseline_ats_score(job: dict) -> int:
    """Fallback score shown when no active resume is available."""
    text = f"{job.get('title') or ''}\n{job.get('description') or ''}"
    score = 32
    if len(text) > 900:
        score += 10
    elif len(text) > 300:
        score += 5
    visa = job.get("visa") or {}
    if isinstance(visa, dict):
        if visa.get("no_sponsorship"):
            return max(25, min(45, score))
        score += min(18, int(visa.get("visa_score") or 0) // 5)
        if visa.get("visa_h1b") or visa.get("visa_opt") or visa.get("visa_stem_opt"):
            score += 5
    if job.get("salary"):
        score += 3
    if job.get("job_url") or job.get("source_url"):
        score += 3
    return max(25, min(78, score))


def _set_insufficient_jd_score(job: dict) -> None:
    """Expose an honest estimate when a posting is too thin for exact scoring."""
    job["match_score"] = _baseline_ats_score(job)
    job["score_type"] = "insufficient_jd"
    job["score_guarded"] = True


def _posted_since(value: Optional[str], tz_offset_minutes: int = 0) -> Optional[datetime]:
    """Convert a time filter label to a UTC datetime cutoff.

    Args:
        value: One of 'today', 'yesterday', 'week', 'month'.
        tz_offset_minutes: Client timezone offset in minutes from UTC
            (same sign as JavaScript Date.getTimezoneOffset: positive means
            behind UTC, e.g. CST = 360).
    """
    if not value:
        return None
    now = datetime.now(timezone.utc)
    # Shift "now" into the user's local time to compute their local midnight,
    # then shift back to UTC for the database query.
    user_offset = timedelta(minutes=-tz_offset_minutes)  # JS offset sign is inverted
    user_now = now + user_offset
    key = value.strip().lower()
    if key in {"8h", "last_8h", "recent", "recent_8h"}:
        return now - timedelta(hours=DEFAULT_RECENT_JOB_HOURS)
    if key == "today":
        local_midnight = user_now.replace(hour=0, minute=0, second=0, microsecond=0)
        return local_midnight - user_offset  # convert back to UTC
    if key == "yesterday":
        local_midnight = user_now.replace(hour=0, minute=0, second=0, microsecond=0)
        return (local_midnight - timedelta(days=1)) - user_offset
    if key in {"week", "7d", "last_week"}:
        return now - timedelta(days=7)
    if key in {"month", "30d", "last_month"}:
        return now - timedelta(days=30)
    return None


def _posted_window(value: Optional[str], tz_offset_minutes: int = 0) -> tuple[Optional[datetime], Optional[datetime]]:
    """Return UTC start/end bounds for frontend time filters."""
    if not value:
        return None, None
    now = datetime.now(timezone.utc)
    user_offset = timedelta(minutes=-tz_offset_minutes)
    user_now = now + user_offset
    local_midnight = user_now.replace(hour=0, minute=0, second=0, microsecond=0)
    key = value.strip().lower()
    if key in {"8h", "last_8h", "recent", "recent_8h"}:
        return now - timedelta(hours=DEFAULT_RECENT_JOB_HOURS), None
    if key in {"24h", "last_24h", "recent_24h"}:
        return now - timedelta(hours=DEFAULT_VISIBLE_MAX_AGE_HOURS), None
    if key == "today":
        return local_midnight - user_offset, None
    if key == "yesterday":
        return (local_midnight - timedelta(days=1)) - user_offset, local_midnight - user_offset
    if key in {"week", "7d", "last_week"}:
        return now - timedelta(days=7), None
    if key in {"month", "30d", "last_month"}:
        return now - timedelta(days=30), None
    return None, None


def _visible_jobs_cutoff() -> datetime:
    """Default frontend isolation boundary.

    Older jobs remain in Postgres/master_jobs for audit/history, but normal
    frontend projections show only positions posted/first collected in the
    rolling last 24 hours.
    """
    return datetime.now(timezone.utc) - timedelta(hours=DEFAULT_VISIBLE_MAX_AGE_HOURS)


def _recent_jobs_cutoff() -> datetime:
    return datetime.now(timezone.utc) - timedelta(hours=DEFAULT_RECENT_JOB_HOURS)


def _country_is_english_native(country_code: str | None) -> bool:
    rule = COUNTRY_RULES.get(country_code or "")
    return bool(rule and rule.english_native)


def _is_english_user_friendly(job: dict) -> bool:
    visa = job.get("visa") or {}
    if not isinstance(visa, dict):
        return True
    country = visa.get("visa_country")
    if _country_is_english_native(country):
        return True
    return bool(visa.get("english_friendly"))


def _coerce_datetime(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if not value:
        return None
    try:
        text = str(value).replace("Z", "+00:00")
        parsed = datetime.fromisoformat(text)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _local_date(value: Any, tz_offset_minutes: int = 0):
    dt = _coerce_datetime(value)
    if not dt:
        return None
    return (dt + timedelta(minutes=-tz_offset_minutes)).date()


def _in_datetime_window(value: Any, since: Optional[datetime], before: Optional[datetime]) -> bool:
    dt = _coerce_datetime(value)
    if not dt:
        return False
    if since and dt < since:
        return False
    if before and dt >= before:
        return False
    return True


def _job_effective_datetime(job: dict) -> Optional[datetime]:
    """Best timestamp for user-facing recency filters and ranking.

    Many direct ATS feeds do not expose posted_at. Treat first_seen_at/last_seen_at
    as the live-market timestamp fallback so Today/Last 8h filters do not show
    "0 jobs" just because a provider omitted the original posting date.
    """
    return _coerce_datetime(
        job.get("posted_at")
        or job.get("first_seen_at")
        or job.get("scraped_at")
        or job.get("last_seen_at")
    )


def _first_party_rank(job: dict) -> int:
    """0 = direct ATS/career-page posting (Greenhouse, Workday, iCIMS, ...),
    1 = aggregator (LinkedIn, Indeed, Dice, ...).

    First-party postings carry the real JD and canonical apply link, so
    within the same relevance tier + date bucket they outrank aggregator
    copies. This is what surfaces the ATS-pipeline jobs the platform
    collects instead of letting high-volume aggregator scrapes bury them."""
    source = str(job.get("source_name") or job.get("source") or "").strip().lower()
    return 0 if source in _FIRST_PARTY_SOURCES else 1


def _projection_sort_key(job: dict, tz_offset_minutes: int = 0) -> tuple:
    """Relevance-first projection (Jobright-style ranking).

    Order: target-role tier, exact match score descending, direct source,
    then freshness/newest. A lower match can never outrank a higher match
    inside the same role tier.
    """
    now = datetime.now(timezone.utc)
    effective_at = job.get("posted_at") or job.get("first_seen_at") or job.get("scraped_at") or job.get("last_seen_at")
    effective = _coerce_datetime(effective_at)
    age = (now - effective) if effective else None
    if age is not None and age < timedelta(0):
        age = timedelta(0)
    if age is None:
        freshness = 0
    elif age <= timedelta(hours=24):
        freshness = 14
    elif age <= timedelta(days=3):
        freshness = 10
    elif age <= timedelta(days=7):
        freshness = 6
    elif age <= timedelta(days=14):
        freshness = 3
    elif age <= timedelta(days=30):
        freshness = 1
    else:
        freshness = 0
    score = int(job.get("match_score") or 0)
    effective_ts = effective.timestamp() if effective else 0
    # Three-tier relevance projection (target roles → related roles → rest).
    # Falls back to the legacy binary preference bucket for callers that do
    # not decorate jobs with relevance_tier.
    tier = job.get("relevance_tier")
    preference_bucket = int(tier) if tier is not None else (0 if job.get("preference_match") else 1)
    # Final id tiebreaker keeps ordering identical across requests even when
    # score/timestamps tie — required for stable pagination.
    # Match means match: never let a freshness/source bonus lift a lower score
    # above a higher score. Relevance tier remains first so target roles stay
    # ahead of merely related roles; source quality and recency only break
    # equal-score ties.
    return (
        preference_bucket,
        -score,
        _first_party_rank(job),
        -freshness,
        -effective_ts,
        str(job.get("id") or ""),
    )


def _job_matches_preferences(job: dict, preferred_roles: list[str], preferred_locations: list[str]) -> bool:
    if not preferred_roles and not preferred_locations:
        return False
    hay = f"{job.get('title') or ''} {job.get('role') or ''} {job.get('taxonomy_category') or ''}".lower()
    loc_hay = f"{job.get('location') or ''}".lower()
    role_match = bool(preferred_roles and any(term in hay for term in preferred_roles))
    loc_match = bool(preferred_locations and any(term in loc_hay for term in preferred_locations))
    return role_match or loc_match


def _categories_for_role_names(role_names: list[str]) -> set[str]:
    """Taxonomy categories that contain any of the user's target roles."""
    selected = {str(r).strip().lower() for r in role_names if str(r).strip()}
    if not selected:
        return set()
    cats: set[str] = set()
    for cat in CATEGORIES:
        for role in cat.roles:
            names = {role.name.lower(), *(syn.lower() for syn in role.synonyms)}
            if selected & names or any(term in name for name in names for term in selected):
                cats.add(cat.name.lower())
                break
    return cats


def _relevance_tier(
    job: dict,
    selected_roles: set[str],
    role_terms: list[str],
    target_categories: set[str],
    preferred_locations: list[str],
) -> int:
    """Three-tier projection for the Jobs feed and Featured positions.

    0 = the user's exact target roles (role match or target-role term in title)
    1 = relevant to the target roles (same taxonomy category, related term,
        or preferred location)
    2 = everything else
    Within each tier the sort key still orders by date bucket (recent, today,
    yesterday, ...) and then ATS score high to low.
    """
    if not selected_roles and not role_terms:
        return 2
    role_value = str(job.get("role") or "").strip().lower()
    title = str(job.get("title") or "").strip().lower()
    if role_value and role_value in selected_roles:
        return 0
    if title and role_terms and any(term in title for term in role_terms):
        return 0
    cat = str(job.get("taxonomy_category") or "").strip().lower()
    if cat and cat in target_categories:
        return 1
    hay = f"{title} {role_value} {cat}"
    if selected_roles and any(term in hay for term in selected_roles):
        return 1
    loc_hay = str(job.get("location") or "").lower()
    if preferred_locations and any(term in loc_hay for term in preferred_locations):
        return 1
    return 2


def _job_matches_role_terms(job: dict, role_names: list[str], role_terms: list[str]) -> bool:
    """Strict target-role match for personalized feeds.

    The preference boost can use locations as a soft signal, but the default
    personalized Jobs page must not show unrelated roles just because they are
    fresh or in the same country.
    """
    if not role_names and not role_terms:
        return True
    role_value = str(job.get("role") or "").strip().lower()
    title = str(job.get("title") or "").strip().lower()
    selected = {str(role).strip().lower() for role in role_names if str(role).strip()}
    if role_value and role_value in selected:
        return True
    terms = [str(term).strip().lower() for term in role_terms if len(str(term).strip()) >= 3]
    return bool(title and any(term in title for term in terms))


def _source_diverse_page(jobs: list[dict], page_size: int, page: int = 1) -> list[dict]:
    """Keep one high-volume source from taking over the visible Jobs page."""
    if page_size <= 0:
        return []
    target_count = max(page_size, page * page_size)
    if len(jobs) <= target_count and page <= 1:
        return jobs[:page_size]
    max_per_source = max(2, math.ceil(page_size * 0.45))
    selected: list[dict] = []
    leftovers: list[dict] = []
    counts: dict[str, int] = {}
    for job in jobs:
        source = str(job.get("source") or job.get("source_name") or "unknown").lower()
        if counts.get(source, 0) < max_per_source:
            selected.append(job)
            counts[source] = counts.get(source, 0) + 1
        else:
            leftovers.append(job)
        if len(selected) >= target_count:
            start = (page - 1) * page_size
            return selected[start:start + page_size]
    seen_ids = {str(job.get("id") or "") for job in selected}
    for job in leftovers:
        job_id = str(job.get("id") or "")
        if job_id and job_id in seen_ids:
            continue
        selected.append(job)
        if job_id:
            seen_ids.add(job_id)
        if len(selected) >= target_count:
            break
    start = (page - 1) * page_size
    return selected[start:start + page_size]


def _taxonomy_terms(category: Optional[str], role: Optional[str]) -> list[str]:
    if not (category or role):
        return []
    payload = to_payload()["categories"]
    terms: list[str] = []
    cat_l = (category or "").strip().lower()
    role_l = (role or "").strip().lower()
    for cat in payload:
        if cat_l and cat["name"].lower() != cat_l:
            continue
        for row in cat["roles"]:
            if role_l and row["name"].lower() != role_l:
                continue
            terms.append(row["name"])
            terms.extend(row.get("synonyms") or [])
    # Keep title filtering broad enough for coverage, small enough for query speed.
    seen: set[str] = set()
    out: list[str] = []
    for term in terms:
        clean = str(term).strip()
        key = clean.lower()
        if len(clean) < 3 or key in seen:
            continue
        seen.add(key)
        out.append(clean)
    return out[:80]


def _preference_terms(user_id: Optional[str]) -> tuple[list[str], list[str]]:
    if not user_id:
        return [], []
    now = time.monotonic()
    cached = _user_preference_cache.get(user_id)
    if cached and now - cached[0] < _USER_CONTEXT_CACHE_TTL_SECONDS:
        roles, locations = cached[1]
        return list(roles), list(locations)
    try:
        prefs = user_store.get_preferences(user_id)
    except Exception:
        return [], []
    roles = [str(v).lower() for v in (prefs.get("target_roles") or []) if str(v).strip()]
    locations = [str(v).lower() for v in (prefs.get("target_locations") or []) if str(v).strip()]
    if len(_user_preference_cache) > 2000:
        _user_preference_cache.clear()
    _user_preference_cache[user_id] = (now, (roles, locations))
    return roles, locations


def _terms_for_role_names(role_names: list[str]) -> list[str]:
    selected = {role.strip().lower() for role in role_names if role.strip()}
    if not selected:
        return []
    terms: list[str] = []
    matched: set[str] = set()
    for cat in CATEGORIES:
        for role in cat.roles:
            names = {role.name.lower(), *(syn.lower() for syn in role.synonyms)}
            if selected.intersection(names):
                matched.update(selected.intersection(names))
                terms.append(role.name)
                terms.extend(role.synonyms)
    # Keep user-entered role text useful even when it does not exactly match a
    # canonical taxonomy label. This prevents preferences like "security",
    # "frontend engineer", or "fullstack" from narrowing the Jobs page to zero.
    fuzzy_map = {
        "security": ("security engineer", "cybersecurity analyst", "security analyst", "appsec engineer", "cloud security engineer"),
        "frontend": ("frontend engineer", "front end engineer", "react developer", "ui engineer"),
        "front end": ("frontend engineer", "front end engineer", "react developer", "ui engineer"),
        "backend": ("backend engineer", "back end engineer", "api engineer", "server side engineer"),
        "back end": ("backend engineer", "back end engineer", "api engineer", "server side engineer"),
        "fullstack": ("full stack engineer", "full-stack engineer", "full stack developer"),
        "full stack": ("full stack engineer", "full-stack engineer", "full stack developer"),
        "product manager": ("product manager", "technical product manager", "associate product manager"),
    }
    for original in selected - matched:
        terms.append(original)
        for key, expansions in fuzzy_map.items():
            if key in original:
                terms.extend(expansions)
    seen: set[str] = set()
    out: list[str] = []
    for term in terms:
        clean = str(term).strip()
        key = clean.lower()
        if len(clean) >= 3 and key not in seen:
            seen.add(key)
            out.append(clean)
    return out[:80]


async def _active_resume_text(user_id: Optional[str]) -> Optional[str]:
    """Return the parsed text of the user's active resume, if any."""
    if not user_id:
        return None
    now = time.monotonic()
    cached = _active_resume_text_cache.get(user_id)
    if cached and now - cached[0] < _USER_CONTEXT_CACHE_TTL_SECONDS:
        return cached[2]
    try:
        resumes = user_store.list_resumes(user_id)
    except Exception as exc:
        logger.warning("Active resume lookup skipped for %s: %s", user_id, exc)
        return None
    active = next((r for r in resumes if r.get("active")), None) or (resumes[0] if resumes else None)
    if not active:
        _active_resume_text_cache[user_id] = (now, "none", None)
        return None
    text = (active.get("parsed_text") or "").strip()
    if len(_active_resume_text_cache) > 2000:
        _active_resume_text_cache.clear()
    _active_resume_text_cache[user_id] = (now, _resume_signature(text), text or None)
    return text or None


# Words that aren't real "skills" but constantly show up in extract_keywords()
# because they're dense in job descriptions. Without this filter the UI shows
# "missing keyword: working", "missing keyword: strong", "missing keyword: team"
# which is the noise the user complained about.
_KEYWORD_BLACKLIST: frozenset[str] = frozenset({
    "experience", "experienced", "experiences", "strong", "ability", "abilities",
    "able", "work", "working", "worked", "team", "teams", "teamwork", "join",
    "joining", "company", "business", "role", "roles", "candidate", "candidates",
    "knowledge", "skill", "skills", "skilled", "good", "great", "excellent",
    "proven", "demonstrated", "required", "preferred", "ideal", "looking",
    "passion", "passionate", "drive", "driven", "self", "starter", "motivated",
    "leadership", "communication", "collaborative", "collaboration", "stakeholder",
    "stakeholders", "deliver", "delivering", "delivered", "build", "building",
    "built", "support", "supporting", "develop", "developing", "developed",
    "designing", "designed", "design", "manage", "managing", "managed", "lead",
    "leads", "leading", "led", "responsible", "responsibility", "responsibilities",
    "engineering", "engineer", "engineers", "include", "includes", "including",
    "across", "within", "across", "year", "years", "month", "months", "day",
    "us", "we", "our", "their", "them", "may", "must", "should", "would",
    "could", "use", "using", "used", "make", "making", "made", "way", "well",
    "best", "high", "highly", "deep", "deeply", "broad", "broadly", "across",
    "complex", "rapidly", "growing", "global", "innovative", "scalable", "world",
    "class", "people", "person", "field", "fields", "area", "areas", "level",
    "levels", "scale", "across", "office", "remote", "hybrid", "onsite",
    "full", "part", "time", "type", "based",
    "and/or", "web based", "web-based", "customer service", "customer support",
    "customers support", "customer services", "client service", "client support",
    "salesforce crm", "database sql",
})


def _is_real_skill(token: str) -> bool:
    """Reject noisy tokens that aren't actual job skills.

    Heuristic:
      - Multi-word tokens are kept (e.g. "machine learning", "power bi") — those
        rarely come from generic noise.
      - Single-word tokens are dropped if they appear in _KEYWORD_BLACKLIST
        or are shorter than 3 characters.
      - Single-word tokens that are pure alphabet AND match a "tech-ish"
        regex (containing a digit, dot, +, #, or being all-uppercase original)
        are kept (e.g. "python", "aws", "k8s").
    """
    t = (token or "").strip().lower()
    if not t:
        return False
    if t in _KEYWORD_BLACKLIST:
        return False
    if "/" in t and not re.search(r"\b(?:ci/cd|tcp/ip|icd-10)\b", t):
        return False
    if " " in t:
        if t in {
            "risk management", "risk assessment", "technical support", "active directory",
            "group policy", "incident response", "vulnerability management",
            "penetration testing", "cloud security", "network security",
            "project management", "program management", "data analysis",
            "business analysis", "quality assurance", "process improvement",
        }:
            return True
        parts = re.findall(r"[a-z0-9+#.]+", t)
        if not parts or any(part in _KEYWORD_BLACKLIST for part in parts):
            return False
        # Keep concrete compound skills, not relationship/filler phrases.
        return any(part in {"sql", "crm", "aws", "azure", "gcp", "linux", "windows", "salesforce", "servicenow", "jira", "python", "java", "risk"} for part in parts)
    if "-" in t or "+" in t or "#" in t or "." in t:
        return True  # techy tokens
    if len(t) < 3:
        return False
    # Drop pure-noise English words by length+vowel heuristic — long words
    # of all-vowels-and-consonants without any tech markers are suspect.
    return True


def _keyword_payload(resume_text: Optional[str], job_text: str) -> dict:
    if not job_text:
        return {"strongKeywords": [], "missingKeywords": []}
    job_text = html.unescape(job_text)
    job_text = re.sub(r"<[^>]+>", " ", job_text)
    try:
        from app.utils.text_processing import (
            compute_keyword_overlap,
            extract_relevant_keywords,
            extract_skills_from_text,
        )
        # **SKILLS-FIRST** approach: prefer entries from TECH_SKILLS (which
        # is a curated dictionary) over arbitrary nouns from
        # extract_keywords (which is just "frequent words minus STOP_WORDS").
        # Then filter the long-tail keywords through _is_real_skill to drop
        # generic English words that aren't actually skills.
        jd_skills = list(dict.fromkeys(extract_skills_from_text(job_text)))
        jd_long_tail = [k for k in extract_relevant_keywords(job_text, top_n=40) if _is_real_skill(k)]
        job_keywords = list(dict.fromkeys(jd_skills + jd_long_tail))

        if not resume_text:
            return {"strongKeywords": job_keywords[:10], "missingKeywords": []}

        r_skills = list(dict.fromkeys(extract_skills_from_text(resume_text)))
        r_long_tail = [k for k in extract_relevant_keywords(resume_text, top_n=70) if _is_real_skill(k)]
        resume_keywords = list(dict.fromkeys(r_skills + r_long_tail))
        matched, missing, _ = compute_keyword_overlap(resume_keywords, job_keywords)
        # Surface SKILLS first in "missing" — multi-word skills like
        # "machine learning" should beat single-word "scalable" when both
        # are in `missing`. Sort by (is_skill DESC, original_order).
        skill_set = {s.lower() for s in jd_skills}
        ranked_missing = sorted(
            missing,
            key=lambda kw: (0 if kw.lower() in skill_set else 1, missing.index(kw)),
        )
        missing_payload = [
            {"kw": kw, "impact": "High" if idx < 4 else "Medium"}
            for idx, kw in enumerate(ranked_missing[:10])
        ]
        # Strong keywords: real skills first too.
        ranked_matched = sorted(
            matched,
            key=lambda kw: (0 if kw.lower() in skill_set else 1, matched.index(kw)),
        )
        return {"strongKeywords": ranked_matched[:12], "missingKeywords": missing_payload}
    except Exception:
        return {"strongKeywords": [], "missingKeywords": []}


def _split_description_points(description: str) -> dict[str, list[str]]:
    """Derive display-ready job sections from scraped descriptions."""
    clean = html.unescape(description or "")
    clean = re.sub(r"\r\n?", "\n", clean).strip()
    clean = re.sub(r"<br\s*/?>", "\n", clean, flags=re.I)
    clean = re.sub(r"<(li|p|h[1-6])[^>]*>", "\n", clean, flags=re.I)
    clean = re.sub(r"</(p|li|ul|ol|h[1-6])>", "\n", clean, flags=re.I)
    clean = re.sub(r"<[^>]+>", " ", clean)
    clean = re.sub(
        r"(?i)\b(responsibilities|requirements|qualifications|you have|you will|nice to have|preferred|benefits)\s*:",
        r"\n\1:\n",
        clean,
    )
    clean = re.sub(r"[ \t]+", " ", clean)
    buckets = {"responsibilities": [], "requirements": [], "niceToHave": [], "benefits": []}
    if not clean:
        return buckets

    active: Optional[str] = None
    heading_map = [
        (re.compile(r"^(job responsibilities|responsibilities|what you'?ll do|role overview|about the role)\b", re.I), "responsibilities"),
        (re.compile(r"^(required qualifications|basic qualifications|minimum qualifications|requirements?|qualifications?|what you bring|must have)\b", re.I), "requirements"),
        (re.compile(r"^(preferred qualifications|nice to have|preferred|bonus|plus)\b", re.I), "niceToHave"),
        (re.compile(r"^(benefits?|perks?|compensation|we offer|total rewards)\b", re.I), "benefits"),
    ]
    bad_patterns = re.compile(
        r"(traceback|stack trace|exception|client error|server error|http/\d|"
        r"too many requests|for more information check|undefined|null|nan|"
        r"apply now|submit an application|redact age|date of birth|privacy policy|"
        r"equal opportunity|reasonable accommodation|scam|recruiters only contact|"
        r"salary range|annual salary|base pay|compensation range|\$\d)",
        re.I,
    )

    for raw in clean.split("\n"):
        is_bullet = bool(re.match(r"^\s*(?:[*\-•·]|\d+[.)])\s+", raw))
        line = raw.strip(" \t-*•·")
        if not line:
            continue
        lowered = line.lower()
        if lowered in {"nan", "none", "null", "n/a"} or bad_patterns.search(line):
            continue
        if len(line) <= 100 and not is_bullet:
            matched_heading = False
            for pattern, bucket in heading_map:
                if pattern.search(line):
                    active = bucket
                    matched_heading = True
                    break
            if matched_heading:
                continue
        if (
            active
            and not is_bullet
            and buckets[active]
            and (raw.startswith((" ", "\t")) or (line[:1].islower()))
        ):
            merged = f"{buckets[active][-1]} {line}"
            if len(merged) <= 320:
                buckets[active][-1] = merged
                continue
        if active and 12 <= len(line) <= 280:
            buckets[active].append(line)

    if not any(buckets.values()):
        sentences = re.split(r"(?<=[.!?])\s+", clean)
        buckets["responsibilities"] = [
            s.strip() for s in sentences
            if 20 <= len(s.strip()) <= 220 and not bad_patterns.search(s)
        ][:6]

    seen: set[str] = set()
    deduped: dict[str, list[str]] = {}
    for key, values in buckets.items():
        deduped[key] = []
        for value in values:
            normalized = re.sub(r"\W+", " ", value.lower()).strip()
            if not normalized or normalized in seen or normalized in {"responsibilities", "requirements", "nice to have"}:
                continue
            seen.add(normalized)
            deduped[key].append(value)
    return {key: value[:8] for key, value in deduped.items()}


async def _visa_stats_for_company(company: str, db) -> dict:
    if not company:
        return {"approvalRate": None, "petitions": None}
    try:
        rows = await db.get_h1b_sponsors(employer=company, limit=25)
    except Exception:
        rows = []
    approvals = 0
    denials = 0
    petitions = 0
    for row in rows:
        approvals += int(row.get("initial_approvals") or 0) + int(row.get("continuing_approvals") or 0)
        denials += int(row.get("initial_denials") or 0) + int(row.get("continuing_denials") or 0)
        petitions += int(row.get("total_petitions") or 0)
    total = approvals + denials
    return {
        "approvalRate": round((approvals / total) * 100) if total else None,
        "petitions": (petitions or total) if (petitions or total) else None,
    }


@router.get("/taxonomy")
async def get_job_taxonomy():
    """Return the full category/role taxonomy for the Jobs page filter UI."""
    payload = to_payload()
    payload["target_countries"] = country_options()
    payload["visa_programs"] = visa_program_options()
    return payload


@router.get("")  # response_model dropped so taxonomy_category / role survive
async def list_jobs(
    search: Optional[str] = Query(None, description="Search jobs by title, company, or description"),
    location: Optional[str] = Query(None, description="Filter by location"),
    country: Optional[str] = Query(None, description="Filter by destination country ISO code, e.g. GB, DE, AU"),
    visa_program: Optional[str] = Query(None, description="Filter by country-specific visa program code, e.g. skilled_worker"),
    category: Optional[str] = Query(None, description="Filter by category"),
    source: Optional[str] = Query(None, description="Filter by source"),
    status: Optional[str] = Query(None, description="Filter by job status"),
    visa_only: bool = Query(False, description="Only show visa-friendly jobs"),
    min_salary: Optional[float] = Query(None, description="Minimum salary filter"),
    job_type: Optional[str] = Query(None, description="Full-time, Part-time, Contract"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(40, ge=1, le=100, description="Results per page (matches the Jobs page's 40-per-page serving contract)"),
    role: Optional[str] = Query(None, description="Filter by taxonomy role name"),
    time_filter: Optional[str] = Query(None, description="24h, 8h, today, yesterday, week, month"),
    sort: str = Query("match", description="match or recent"),
    personalized: bool = Query(False, description="Use the caller's target roles/locations when no explicit role filter is selected"),
    include_scores: bool = Query(False, description="Score jobs against the active resume; slower because it reads user resume data"),
    entry_level: bool = Query(True, description="Prioritize 0-10 yr roles (default true)"),
    max_years: int = Query(10, ge=0, le=50, description="Default max required years of experience"),
    tz_offset: int = Query(0, description="Client timezone offset in minutes from UTC (JS getTimezoneOffset)"),
    one_click_only: bool = Query(False, description="Only show positions with a live, configured API submission path"),
    db=Depends(get_db),
    user_id: Optional[str] = Depends(fast_optional_user_id),
):
    """List job postings with filtering, pagination, and per-user ATS scores.

    When a JWT is supplied, each job is scored against the caller's active
    resume so the UI can sort/show match percentages without a second call.
    """
    # Stale-if-error key: while the scraper saturates Cloud SQL, user queries
    # can time out. Instead of an empty Jobs page, serve the last successful
    # response for the same user+filters (up to 30 minutes old).
    _stale_key = "|".join(str(v) for v in (
        user_id or "anon", page, page_size, search, location, country, visa_program,
        category, source, status, visa_only, role, time_filter, sort, personalized,
        include_scores, entry_level, max_years, min_salary, job_type, tz_offset,
        one_click_only,
    ))
    filters = {}
    if search:
        filters["search"] = search
    if location:
        filters["location"] = location
    all_countries_requested = bool(country and country.strip().lower() in {"all", "*", "any"})
    if country and not all_countries_requested:
        normalized_country = normalize_country_code(country)
        if not normalized_country:
            raise HTTPException(status_code=400, detail="Unsupported country filter")
        filters["country"] = normalized_country
    if visa_program:
        filters["visa_program"] = visa_program.strip().lower()
    # NOTE: `category` (taxonomy name) and `role` (taxonomy role) are applied
    # post-fetch via in-memory filtering further down, since the DB column
    # uses the legacy JobCategory enum which doesn't match our taxonomy names.
    if source:
        filters["source"] = source
    filters["status"] = status or "active"
    # Locked frontend boundary: incomplete snippets never enter the candidate
    # pool, regardless of which scraper or source table produced them.
    filters["complete_jd_only"] = True
    if visa_only:
        filters["visa_only"] = True
    if job_type and job_type.strip():
        filters["job_type"] = job_type.strip()
    if min_salary is not None:
        filters["min_salary"] = float(min_salary)
    fresh_since, fresh_before = _posted_window(time_filter, tz_offset_minutes=tz_offset)
    visible_cutoff = _visible_jobs_cutoff()
    post_filter_since: Optional[datetime] = None
    post_filter_before: Optional[datetime] = None
    if fresh_since:
        # Avoid pushing posted_at into Postgres for frontend time chips. The
        # live master_jobs table is large and posted_at is not the fast path;
        # exact posted_at scans were causing Cloud Run 504s for Today/Yesterday.
        # Pull recent, indexed last_seen rows and enforce the posted window
        # below before rendering.
        filters["seen_since"] = visible_cutoff
        post_filter_since = max(fresh_since, visible_cutoff)
        post_filter_before = fresh_before
        # Apply the same honest posting-date rule in PostgreSQL before LIMIT.
        # Without this predicate the first page was drawn from recently
        # re-verified old jobs; valid new postings deeper in that pool were
        # never considered. ATSes that omit posted_at may fall back only to
        # first_seen_at, never last_seen_at.
        filters["honest_since"] = post_filter_since
        if post_filter_before is not None:
            filters["honest_before"] = post_filter_before
    else:
        # The UI default is "All active", so do not silently force the local
        # "today" window here. Keep the database scan bounded to recently
        # active jobs, then let explicit Today/Yesterday/Week/Month filters
        # apply exact posted-date windows above.
        filters["effective_since"] = visible_cutoff
    # Always enforce the frontend visibility boundary against the honest job
    # timestamp after fetching. The indexed DB prefilter uses last_seen_at for
    # speed, but last_seen_at only means "verified again"; it must never make a
    # January posting appear current in July. _job_effective_datetime prefers
    # posted_at and falls back to first_seen only when an ATS omitted its date.
    visibility_since = post_filter_since or visible_cutoff
    visibility_before = post_filter_before
    taxonomy_filter_active = bool(category or role)
    title_terms = _taxonomy_terms(category, role)
    preferred_roles, preferred_locations = _preference_terms(user_id) if personalized else ([], [])
    # Default personalized feeds to the user's destination country. Passing
    # country=all is an explicit escape hatch used by the UI's All countries
    # option, so users can broaden the search without disabling role matching.
    if personalized and not filters.get("country") and not all_countries_requested:
        for preferred_location in preferred_locations:
            preferred_country = resolve_country(preferred_location)
            if normalize_country_code(preferred_country):
                filters["country"] = preferred_country
                break
    preferred_role_terms = _terms_for_role_names(preferred_roles) if preferred_roles else []
    _selected_roles = set(preferred_roles)
    _tier_role_terms = [t.lower() for t in preferred_role_terms if len(str(t).strip()) >= 3]
    _target_categories = _categories_for_role_names(preferred_roles)
    if personalized and not title_terms and not search and preferred_roles:
        title_terms = preferred_role_terms
    if title_terms and not taxonomy_filter_active:
        filters["title_terms"] = title_terms

    offset = (page - 1) * page_size
    resume_text = await _active_resume_text(user_id) if include_scores else None
    resume_sig = _resume_signature(resume_text)
    response_cache_key = _stable_cache_key("jobs:list:v2", {
        "user_id": user_id or "anon",
        "resume_sig": resume_sig if include_scores else "scores_off",
        "page": page,
        "page_size": page_size,
        "search": search,
        "location": location,
        "country": country,
        "visa_program": visa_program,
        "category": category,
        "source": source,
        "status": status,
        "visa_only": visa_only,
        "min_salary": min_salary,
        "job_type": job_type,
        "role": role,
        "time_filter": time_filter,
        "sort": sort,
        "personalized": personalized,
        "include_scores": include_scores,
        "entry_level": entry_level,
        "max_years": max_years,
        "tz_offset": tz_offset,
        "one_click_only": one_click_only,
        "filters": filters,
        "preferred_roles": preferred_roles,
        "preferred_locations": preferred_locations,
    })
    cached_response = _get_fast_response(response_cache_key)
    if cached_response is not None:
        return cached_response

    async def _safe_count(count_filters: dict, *, fallback: int) -> int:
        """Exact COUNT(*) that degrades to an estimate instead of 500-ing.

        Filter clicks were raising "Error listing jobs" because an exact
        COUNT(*) on the large master_jobs table can exceed the DB statement
        timeout (or the Cloud Run request budget) while the scraper is writing.
        A slow/failed count must never break the page — pagination only needs a
        workable upper bound, which `fallback` provides.
        """
        try:
            return await db.count_jobs(filters=count_filters)
        except Exception as count_exc:  # pragma: no cover - depends on live DB load
            logger.warning("count_jobs degraded to estimate (%s): %s", fallback, count_exc)
            return fallback

    source_breakdown: dict[str, int] = {"direct": 0, "aggregator": 0}
    try:
        free_text_search_active = bool(search and search.strip())
        # Taxonomy filters are derived from title/category matching. Counting
        # all matches first doubles the work and makes category clicks feel
        # slow, so fetch a bounded candidate pool and derive total from it.
        #
        # Free-text search can hit the job description as well as title/company.
        # An exact COUNT(*) over that broad text search is nearly as expensive
        # as the page query itself, so avoid doubling the work. The response
        # still reports enough total to keep pagination moving, then tightens it
        # once a short final page is reached.
        exact_count_filters = {
            "country",
            "visa_program",
            "source",
            "visa_only",
            "seen_before",
            "job_type",
            "min_salary",
        }
        exact_count_active = any(key in filters for key in exact_count_filters)
        # The live master_jobs table is large. Exact COUNT(*) on the broad
        # All Jobs path can take longer than the frontend request timeout,
        # even though fetching the first page is fast. Use a pagination-safe
        # estimate for broad views and tighten totals on filtered/taxonomy
        # paths where the exact count is meaningful to the user.
        title_terms_active = bool(filters.get("title_terms")) and not taxonomy_filter_active
        if title_terms_active and not free_text_search_active and not post_filter_since and not post_filter_before:
            # Personalized / role feeds report the EXACT matching inventory
            # (fast thanks to the pg_trgm title index). Users were seeing
            # "338 positions" while Alerts correctly reported thousands for
            # the same target roles — the old heuristic + tiny pool hid the
            # rest of the inventory. Counts are cached 5 min per filter set so
            # page clicks don't re-count.
            import time as _time
            _count_key = "|".join(sorted(map(str, filters.get("title_terms", [])))) + "|" + "|".join(
                f"{k}={filters.get(k)}" for k in ("country", "visa_program", "visa_only", "location", "status")
            )
            _cached = _title_count_cache.get(_count_key)
            if personalized:
                # Exact COUNT over 30-80 wildcard role aliases was consuming
                # the full statement timeout before the page query even ran.
                # The bounded candidate fetch below tightens this estimate as
                # soon as it reaches the end of the actual result set.
                total = _cached[1] if _cached and _time.monotonic() - _cached[0] < 300 else 50000
            elif _cached and _time.monotonic() - _cached[0] < 300:
                total = _cached[1]
            else:
                total = await _safe_count(filters, fallback=_cached[1] if _cached else 50000)
                if len(_title_count_cache) > 500:
                    _title_count_cache.clear()
                _title_count_cache[_count_key] = (_time.monotonic(), total)
        else:
            total = 50000 if (
                taxonomy_filter_active
                or free_text_search_active
                or filters.get("title_terms")
                or post_filter_since
                or post_filter_before
                or not exact_count_active
            ) else await _safe_count(filters, fallback=50000)
        # Category and role are derived from titles in Python. Only those
        # filters need a full pool scan. The normal All Jobs path fetches the
        # requested page directly so the dashboard does not wait on thousands
        # of rows just to render the first 100 cards.
        if taxonomy_filter_active:
            # Pool cap cut from 12k to 4k: pulling 12,000 rows and running the
            # Python quality/visa/categorize pipeline on ALL of them per
            # request was the main reason the Jobs page took seconds to load.
            # 4k rows = 200 pages of results, far beyond real browsing depth.
            fetch_limit = min(max(total, page_size), 4000)
            fetch_offset = 0
            filters["coverage_scan"] = True
        elif title_terms_active and not free_text_search_active:
            # Personalized / role views paginate a deep (but bounded) matching
            # inventory. Descriptions are truncated in the pool query so this
            # stays fast; the visible page is re-scored against full text
            # afterwards.
            # Personalized roles are filtered in Python after an indexed
            # newest-first country query. A first-page pool of only 800 rows
            # routinely found four stale matches and missed current roles
            # deeper in a 400k-row inventory. Pull the bounded 4k pool once;
            # descriptions remain truncated and only matches are scored.
            fetch_limit = 4000 if personalized else min(max(offset + page_size * 8, 800), 4000)
            fetch_offset = 0
        elif post_filter_since or post_filter_before:
            fetch_limit = min(max(offset + page_size * 8, 800), 8000)
            fetch_offset = 0
        else:
            # Post-fetch filters (country scope, is_target_experience) routinely
            # drop ~50-70% of rows, which is why users were seeing ~16 cards even
            # though the API said "20 per page". Over-fetch ×4 so a full page still
            # renders after filtering, then bound to a safe ceiling.
            fetch_limit = min(max(offset + page_size * 8, 800), 8000)
            fetch_offset = 0
        # Do not push a large OR of wildcard title aliases into PostgreSQL for
        # personalized feeds. On the 450K-row production inventory that plan
        # can consume the entire statement timeout before returning one row.
        # Pull a bounded, newest-first country pool using the last_seen index,
        # then apply the same precise role matching below in Python.
        db_filters = dict(filters)
        if title_terms_active and personalized:
            db_filters.pop("title_terms", None)
            effective_cutoff = db_filters.pop("effective_since", None)
            if effective_cutoff is not None:
                db_filters["seen_since"] = effective_cutoff

        source_balanced_fetch = (
            not filters.get("source")
            and hasattr(db, "get_jobs_source_balanced")
            and not taxonomy_filter_active
            # Exact freshness windows must walk the complete newest-first
            # inventory. A per-source cap would omit valid 24-hour postings
            # from high-volume ATSes.
            and not post_filter_since
            # title_terms feeds need the deterministic full-inventory query —
            # the per-source cap of the balanced query would silently drop
            # matching jobs from high-volume sources.
            and not filters.get("title_terms")
            and (personalized or free_text_search_active or not filters.get("title_terms"))
        )
        if source_balanced_fetch:
            jobs = await db.get_jobs_source_balanced(
                filters=filters,
                limit=max(fetch_limit, 360),
                offset=0,
                per_source=90,
            )
        else:
            jobs = await db.get_jobs(filters=db_filters, limit=fetch_limit, offset=fetch_offset)
        total_pages = math.ceil(total / page_size) if total > 0 else 1

        # Tag each job with taxonomy category + role under sibling fields so we
        # don't collide with JobPost.category (which is a strict Enum).
        from app.services.job_filters import (
            is_early_career_title,
            is_senior_title,
            in_scope_country,
            is_target_experience,
            requires_us_clearance,
        )
        decorated: list[dict] = []
        for j in jobs:
            meta = j.get("extra_metadata") or {}
            if not isinstance(meta, dict):
                meta = {}
            requested_location = meta.get("requested_location", "")
            visa_payload = j.get("visa") or {}
            default_country = (
                j.get("country")
                or meta.get("country")
                or meta.get("location_country")
                or visa_payload.get("visa_country")
            )
            location_scope, resolved_location_country = in_scope_country(
                f"{j.get('location') or ''} {requested_location} {j.get('title') or ''}",
                default_country=default_country,
            )
            if not location_scope:
                continue
            # Some aggregator imports stamped the scrape's requested country
            # onto the row even when the returned location was abroad. The
            # visible country filter must trust the posting location/title
            # evidence over that stale metadata or a US feed leaks IN/DE/CA
            # roles. Unknown/remote locations may still use the stored default.
            if filters.get("country") and resolved_location_country != filters["country"]:
                continue
            if resolved_location_country:
                j = dict(j)
                j["country"] = resolved_location_country
                j["visa"] = {**visa_payload, "visa_country": resolved_location_country}
            if not is_target_experience(
                j.get("title") or "",
                meta.get("years_min"),
                meta.get("years_max"),
                max_years=max_years,
                description=j.get("description") or "",
            ):
                continue
            cat, rname = categorize(f"{j.get('title') or ''} {j.get('company') or ''}")
            j = _apply_job_specific_visa_rules(dict(j))
            visa_payload = j.get("visa") or {}
            # US clearance / citizenship-only roles can never sponsor a visa.
            # Strip any visa-friendly signals so they never show as visa-friendly,
            # and drop them entirely from visa-only / visa-program feeds.
            if requires_us_clearance(f"{j.get('title') or ''} {j.get('description') or ''}"):
                if filters.get("visa_only") or filters.get("visa_program"):
                    continue
                visa_payload = {**visa_payload, "visa_score": 0, "visa_programs": [], "requires_clearance": True}
                j["visa"] = visa_payload
            if filters.get("country") and visa_payload.get("visa_country") != filters["country"]:
                continue
            if filters.get("visa_program") and filters["visa_program"] not in (visa_payload.get("visa_programs") or []):
                continue
            if not _in_datetime_window(
                _job_effective_datetime(j),
                visibility_since,
                visibility_before,
            ):
                continue
            if is_probably_fake_or_scam_job(
                j.get("title") or "",
                j.get("company") or j.get("company_name") or "",
                j.get("description") or "",
                j.get("job_url") or j.get("url") or "",
            ):
                continue
            if not has_usable_job_description(j.get("description") or ""):
                continue
            j["taxonomy_category"] = cat
            j["role"] = rname
            decorated.append(j)

        # Apply saved-role matching BEFORE the source policy. The old order
        # chose unrelated direct rows first and then removed them by role,
        # producing an empty personalized page even when matching jobs existed.
        if personalized and preferred_roles and not role and not category and not free_text_search_active:
            decorated = [
                j for j in decorated
                if _job_matches_role_terms(j, preferred_roles, preferred_role_terms)
            ]

        from app.scrape_constants import AGGREGATOR_SOURCES
        source_breakdown = {
            "direct": sum(
                1 for j in decorated
                if str(j.get("source_name") or j.get("source") or "").strip().lower() not in AGGREGATOR_SOURCES
            ),
            "aggregator": sum(
                1 for j in decorated
                if str(j.get("source_name") or j.get("source") or "").strip().lower() in AGGREGATOR_SOURCES
            ),
        }

        # Direct-source policy: the feed serves ATS/company-page postings.
        # Aggregator copies (LinkedIn/Indeed/Dice/...) only backfill when the
        # direct pool can't fill a page, so users apply at the source instead
        # of through re-scraped listings. JOBS_FEED_INCLUDE_AGGREGATORS=true
        # restores blended results without a deploy.
        if not filters.get("source") and os.getenv("JOBS_FEED_INCLUDE_AGGREGATORS", "").strip().lower() not in {"1", "true", "yes", "on"}:
            direct_rows = [
                j for j in decorated
                if str(j.get("source_name") or j.get("source") or "").strip().lower() not in AGGREGATOR_SOURCES
            ]
            if len(direct_rows) >= page_size:
                decorated = direct_rows

        if taxonomy_filter_active:
            total = len(decorated)
            total_pages = max(1, math.ceil(total / page_size))
        if role:
            role_l = role.strip().lower()
            decorated = [j for j in decorated if (j.get("role") or "").lower() == role_l]
            total = len(decorated)
            total_pages = max(1, math.ceil(total / page_size))

        # Likewise, when the user filters by category they pass the
        # taxonomy name ("Technology & Engineering"); resolve that here
        # since the DB column uses the legacy enum.
        if category:
            cat_l = category.strip().lower()
            decorated = [j for j in decorated if (j.get("taxonomy_category") or "").lower() == cat_l]
            total = len(decorated)
            total_pages = max(1, math.ceil(total / page_size))
        elif not taxonomy_filter_active and free_text_search_active:
            if len(decorated) < page_size:
                total = offset + len(decorated)
            else:
                total = max(offset + len(decorated) + page_size, page * page_size + 1)
            total_pages = max(1, math.ceil(total / page_size))
        elif not taxonomy_filter_active and not exact_count_active:
            if len(decorated) < page_size:
                total = offset + len(decorated)
            else:
                total = max(offset + len(decorated) + page_size, page * page_size + 1)
            total_pages = max(1, math.ceil(total / page_size))

        resume_cache = _prepare_resume_tokens(resume_text) if resume_text else None
        def _score_visible_job(j: dict) -> None:
            jd = j.get("description") or ""
            jt = j.get("title") or ""
            if resume_text and (jd or jt):
                if _can_score_job_text(jt, jd):
                    j["match_score"] = _cached_score_job_against_resume(
                        resume_text, f"{jt}\n{jd}", resume_cache=resume_cache, job_id=str(j.get("id") or ""),
                    )
                    j["score_type"] = "resume_match"
                else:
                    _set_insufficient_jd_score(j)
            else:
                j["match_score"] = _baseline_ats_score(j)
                j["score_type"] = "baseline_ats"
            pref_bonus = 0
            hay = f"{j.get('title') or ''} {j.get('role') or ''} {j.get('taxonomy_category') or ''}".lower()
            loc_hay = f"{j.get('location') or ''}".lower()
            if preferred_roles and any(term in hay for term in preferred_roles):
                pref_bonus += 6
            if preferred_locations and any(term in loc_hay for term in preferred_locations):
                pref_bonus += 3
            if pref_bonus and isinstance(j.get("match_score"), int):
                j["match_score"] = min(98, int(j["match_score"]) + pref_bonus)
            j["preference_match"] = _job_matches_preferences(j, preferred_roles, preferred_locations)
            j["relevance_tier"] = _relevance_tier(j, _selected_roles, _tier_role_terms, _target_categories, preferred_locations)

        # Rank broad pools with deterministic baseline signals, then compute
        # exact resume-vs-JD scores only for the visible page below.
        # Personalized target-role/country feeds must be globally rankable by
        # the user's resume score. Score that bounded candidate pool now; broad
        # anonymous/all-country pools retain the cheaper two-stage baseline.
        exact_personalized_pool = bool(resume_text and personalized and preferred_roles)
        deep_pool = len(decorated) > max(page_size * 3, 120) and not exact_personalized_pool
        for job_data in decorated:
            if deep_pool:
                job_data["match_score"] = _baseline_ats_score(job_data)
                job_data["score_type"] = "baseline_ats"
                job_data["preference_match"] = _job_matches_preferences(job_data, preferred_roles, preferred_locations)
                job_data["relevance_tier"] = _relevance_tier(job_data, _selected_roles, _tier_role_terms, _target_categories, preferred_locations)
            else:
                _score_visible_job(job_data)

        # 0-10 yr prioritization remains as a tie-breaker; the primary
        # projection is date bucket + ATS score below.
        if entry_level:
            def _entry_score(j: dict) -> tuple:
                meta = j.get("extra_metadata") or {}
                if not isinstance(meta, dict):
                    meta = {}
                ymin = meta.get("years_min")
                try:
                    years = int(ymin) if ymin is not None else None
                except (TypeError, ValueError):
                    years = None
                title = j.get("title") or ""
                # Bucket: explicit junior/new-grad/associate first, then 0-5,
                # then 6-10, then senior-ish but still <=10, then unknown.
                if is_early_career_title(title):
                    bucket = 0
                elif years is not None and 0 <= years <= 5 and not is_senior_title(title):
                    bucket = 1
                elif years is None:
                    bucket = 4
                elif years <= max_years:
                    bucket = 3 if is_senior_title(title) else 2
                else:
                    bucket = 5
                score = -int(j.get("match_score") or 0)
                return (bucket, score)
            decorated.sort(key=_entry_score)

        if sort == "recent":
            # Day-bucketed recency: newest posting DAY first, first-party
            # ATS/career-page sources before aggregator copies within the
            # same day, then exact time. Pure second-level recency let
            # high-volume aggregator scrapes bury the direct ATS postings.
            def _recency_key(row: dict) -> tuple:
                eff = _job_effective_datetime(row)
                day_ordinal = eff.date().toordinal() if eff else 0
                return (-day_ordinal, _first_party_rank(row), -(eff.timestamp() if eff else 0.0), str(row.get("id") or ""))
            decorated.sort(key=_recency_key)
        elif sort == "match":
            decorated.sort(key=lambda row: _projection_sort_key(row, tz_offset_minutes=tz_offset))
        else:
            decorated.sort(key=lambda row: _projection_sort_key(row, tz_offset_minutes=tz_offset))

        # Honest totals: fetch_offset is always 0, so when the DB returned
        # fewer rows than requested, `decorated` IS the complete result set.
        # Reporting the 50k heuristic in that case rendered page buttons that
        # all pointed at empty/duplicate slices — pagination now only offers
        # pages that really exist.
        if visibility_since or visibility_before:
            total = len(decorated)
            total_pages = max(1, math.ceil(total / page_size)) if total else 1
        elif len(jobs) < fetch_limit:
            total = len(decorated)
            total_pages = max(1, math.ceil(total / page_size)) if total else 1
        elif len(decorated) < page_size:
            # Post-fetch filters (direct-source policy, country/visa/ex-career
            # gates, JD-quality gate) removed the whole first pool. Do not
            # advertise a 50k estimated inventory when this filter state has no
            # renderable rows in the fetched candidate set.
            total = offset + len(decorated)
            total_pages = max(1, math.ceil(total / page_size)) if total else 1
        elif not taxonomy_filter_active and not exact_count_active:
            # Broad-view ceiling: the pool query stops growing at 2500 rows,
            # so pages past that point can never be served. Don't advertise
            # them — deeper exploration goes through country/role filters,
            # which re-pool from the full table.
            total = min(total, fetch_limit)
            total_pages = max(1, math.ceil(total / page_size))

        # Cap to the requested page_size. For taxonomy/category filters we
        # slice from the full pool; for the standard path the over-fetch ×4
        # means we have more than page_size rows after dropping non-US/CA
        # and out-of-experience-range items, so we still trim to page_size.
        credentialed_ats = parse_credentialed(settings.apply_credentialed_ats)
        for row in decorated:
            ats_type = infer_ats_type(row)
            row["ats_type"] = ats_type
            row["one_click_ready"] = bool(
                settings.apply_live_submit_enabled
                and is_one_click_ready(ats_type, credentialed_ats)
            )
        if one_click_only:
            decorated = [row for row in decorated if row.get("one_click_ready")]

        # Hydrate and validate enough candidates to backfill a full page. The
        # old order selected 40 first and then rejected incomplete JDs, which
        # is why users could see only 24 positions on an otherwise full page.
        needed = offset + page_size
        hydrate_limit = min(len(decorated), max(needed * 4, page_size * 4))
        page_candidates = decorated[:hydrate_limit]

        # Hydrate the visible page with FULL descriptions. Pool queries use a
        # 900-char prefix for speed, but the cards/detail/tailor queue should
        # operate on the complete JD for the rows the user can actually see.
        if page_candidates:
            try:
                get_descriptions = getattr(db, "get_job_descriptions", None)
                full_descriptions = (
                    await get_descriptions([str(j.get("id") or "") for j in page_candidates])
                    if get_descriptions else {}
                )
                for j in page_candidates:
                    full = full_descriptions.get(str(j.get("id") or "")) or ""
                    if full and len(full) > len(str(j.get("description") or "")):
                        j["description"] = full[:50000]
            except Exception as exc:
                logger.debug("Full-text candidate hydration skipped: %s", exc)

        # The SQL length predicate keeps pool queries fast; this exact shared
        # policy check runs after full-text hydration and is the final guard
        # before any job description can cross the frontend API boundary.
        complete_candidates = [
            row for row in page_candidates
            if has_complete_job_description(row.get("description") or "")
        ]
        page_jobs = complete_candidates[offset:offset + page_size]
        if hydrate_limit == len(decorated):
            total = len(complete_candidates)
            total_pages = max(1, math.ceil(total / page_size)) if total else 1

        # Re-score the visible page against hydrated descriptions so the list
        # shows the exact number the Job Detail page computes. Pool ranking
        # above scores 900-char truncated JDs for speed, which previously
        # produced mismatches like "74 in detail, 88 in the list".
        if resume_text and page_jobs:
            try:
                for j in page_jobs:
                    full = j.get("description") or ""
                    jt = j.get("title") or ""
                    if _can_score_job_text(jt, full):
                        j["match_score"] = _cached_score_job_against_resume(
                            resume_text, f"{jt}\n{full}", resume_cache=resume_cache, job_id=str(j.get("id") or ""),
                        )
                        j["score_type"] = "resume_match"
                    else:
                        _set_insufficient_jd_score(j)
                if sort == "recent":
                    def _rescored_recent_key(row: dict) -> tuple:
                        effective = _job_effective_datetime(row)
                        return (
                            -(effective.timestamp() if effective else 0.0),
                            -int(row.get("match_score") or 0),
                            str(row.get("id") or ""),
                        )

                    page_jobs.sort(
                        key=_rescored_recent_key
                    )
                else:
                    page_jobs.sort(key=lambda row: _projection_sort_key(row, tz_offset_minutes=tz_offset))
            except Exception as exc:
                logger.debug("Full-text page rescore skipped: %s", exc)
        elif not resume_text:
            for j in page_jobs:
                j["match_score"] = _baseline_ats_score(j)
                j["score_type"] = "baseline_ats"

        # Convert to JobPost models for the response. Stash the taxonomy
        # extras and re-attach them post-validation so the strict JobPost
        # enum doesn't reject "Technology & Engineering" etc.
        job_posts: list = []
        for job_data in page_jobs:
            if not job_data.get("score_type"):
                job_data["match_score"] = job_data.get("match_score") or _baseline_ats_score(job_data)
                job_data["score_type"] = "baseline_ats"
            metadata = dict(job_data.get("extra_metadata") or {})
            metadata.pop("description_html", None)
            job_data["extra_metadata"] = metadata
            tax_cat = job_data.pop("taxonomy_category", None)
            tax_role = job_data.pop("role", None)
            try:
                model = JobPost(**job_data)
                payload = model.model_dump(mode="json")
            except Exception:
                payload = dict(job_data)
            if tax_cat is not None:
                payload["taxonomy_category"] = tax_cat
            if tax_role is not None:
                payload["role"] = tax_role
            job_posts.append(payload)

        if not taxonomy_filter_active:
            total_pages = max(1, math.ceil(total / page_size))

        # Return a plain dict so taxonomy_category / role survive — FastAPI's
        # default jsonable_encoder doesn't drop unknown keys.
        response_payload = {
            "jobs": job_posts,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
            "source_breakdown": source_breakdown,
            "filters_applied": {
                **{k: v for k, v in filters.items() if k != "coverage_scan"},
                **({"role": role} if role else {}),
                **({"category": category} if category else {}),
                **({"country": filters.get("country")} if filters.get("country") else {}),
                **({"visa_program": filters.get("visa_program")} if filters.get("visa_program") else {}),
                **({"time_filter": time_filter} if time_filter else {}),
                **({"status": status} if status else {}),
                **({"sort": sort} if sort else {}),
                **({"personalized": personalized and bool(preferred_roles)} if personalized else {}),
                **({"one_click_only": True} if one_click_only else {}),
            },
        }
        if job_posts:
            _store_stale_jobs_response(_stale_key, response_payload)
            _store_fast_response(response_cache_key, response_payload)
        return response_payload
    except Exception as e:
        logger.error(f"Error listing jobs: {e}")
        # Serve the last-known-good page instead of an error while the
        # scraper (or any incident) has the database under pressure.
        stale = _get_stale_jobs_response(_stale_key)
        if stale is not None:
            logger.warning("Serving stale jobs page for key=%s due to: %s", _stale_key[:80], e)
            return {**stale, "stale": True}
        # Last resort: a single filter click should never show a red error.
        # Retry with a cheap, bounded query (no count, no coverage scan, small
        # pool) so the user still gets a usable first page; only return an
        # empty-but-valid payload if even that fails.
        try:
            light_filters = {
                k: v for k, v in filters.items()
                if k not in {"coverage_scan", "title_terms", "effective_since", "effective_before"}
            }
            light_filters.setdefault("status", status or "active")
            light_filters["skip_target_prefilter"] = True
            light_filters["seen_since"] = visible_cutoff
            light_jobs = await db.get_jobs(
                filters=light_filters,
                limit=min(max(page_size * 10, 400), 800),
                offset=0,
            )
            light_posts: list = []
            from app.services.job_filters import is_target_experience
            for job_data in light_jobs:
                meta = job_data.get("extra_metadata") or {}
                if not isinstance(meta, dict):
                    meta = {}
                if not is_target_experience(
                    job_data.get("title") or "",
                    meta.get("years_min"),
                    meta.get("years_max"),
                    max_years=max_years,
                    description=job_data.get("description") or "",
                ):
                    continue
                if personalized and preferred_roles and not _job_matches_role_terms(
                    job_data, preferred_roles, preferred_role_terms
                ):
                    continue
                effective = _job_effective_datetime(job_data)
                if not effective or effective < visible_cutoff:
                    continue
                if (post_filter_since or post_filter_before) and not _in_datetime_window(
                    effective, post_filter_since, post_filter_before
                ):
                    continue
                job_data = dict(job_data)
                job_data["match_score"] = _baseline_ats_score(job_data)
                job_data["score_type"] = "baseline_ats"
                try:
                    light_posts.append(JobPost(**job_data).model_dump(mode="json"))
                except Exception:
                    light_posts.append(dict(job_data))
                if len(light_posts) >= page_size:
                    break
            return {
                "jobs": light_posts,
                "total": len(light_posts),
                "page": 1,
                "page_size": page_size,
                "total_pages": 1,
                "degraded": True,
                "filters_applied": {k: v for k, v in filters.items() if k != "coverage_scan"},
            }
        except Exception as fallback_exc:
            logger.error("Jobs fallback query also failed: %s", fallback_exc)
            return {
                "jobs": [],
                "total": 0,
                "page": 1,
                "page_size": page_size,
                "total_pages": 1,
                "degraded": True,
                "filters_applied": {},
            }


@router.get("/stats", response_model=JobStats)
async def get_job_stats(db=Depends(get_db)):
    """Get aggregated job statistics for dashboard.

    Returns total counts, breakdowns by category/source/visa,
    and recent activity metrics.
    """
    try:
        total = await db.count_jobs()

        # Get category breakdown
        by_category = {}
        for cat in JobCategory:
            count = await db.count_jobs({"category": cat.value})
            if count > 0:
                by_category[cat.value] = count

        return JobStats(
            total_jobs=total,
            by_category=by_category,
        )
    except Exception as e:
        logger.error(f"Error getting job stats: {e}")
        raise HTTPException(status_code=500, detail="Error getting job stats")


@router.get("/coverage")
async def get_job_coverage(
    max_years: int = Query(10, ge=0, le=50),
    low_threshold: int = Query(10, ge=1, le=100),
    thin_threshold: int = Query(50, ge=1, le=500),
    limit: int = Query(100000, ge=100, le=200000),
    db=Depends(get_db),
):
    """Compute live taxonomy coverage from cloud job data.

    This gives the frontend/admin tools one cloud source of truth for which
    roles are missing, low, thin, or healthy without writing local audit files.
    """
    try:
        from app.services.job_filters import in_scope_country, is_target_experience

        taxonomy = to_payload()["categories"]
        role_rows: dict[str, dict[str, Any]] = {}
        category_counts = {cat["name"]: 0 for cat in taxonomy}
        for cat in taxonomy:
            for role in cat["roles"]:
                key = role["name"].lower()
                role_rows[key] = {
                    "category": cat["name"],
                    "role": role["name"],
                    "count": 0,
                    "status": "MISSING",
                    "examples": [],
                }

        jobs = await db.get_jobs(limit=limit, offset=0)
        considered = 0
        skipped_geo = 0
        skipped_experience = 0
        uncategorized = 0
        for job in jobs:
            meta = job.get("extra_metadata") or {}
            if not isinstance(meta, dict):
                meta = {}
            requested_location = meta.get("requested_location", "")
            if not in_scope_country(f"{job.get('location') or ''} {requested_location} {job.get('title') or ''}")[0]:
                skipped_geo += 1
                continue
            if not is_target_experience(
                job.get("title") or "",
                meta.get("years_min"),
                meta.get("years_max"),
                max_years=max_years,
            ):
                skipped_experience += 1
                continue
            considered += 1
            cat_name, role_name = categorize(f"{job.get('title') or ''} {job.get('company') or ''}")
            if cat_name in category_counts:
                category_counts[cat_name] += 1
            key = role_name.lower()
            row = role_rows.get(key)
            if row:
                row["count"] += 1
                if len(row["examples"]) < 3:
                    row["examples"].append({
                        "title": job.get("title") or "",
                        "company": job.get("company") or "",
                        "location": job.get("location") or "",
                    })
            else:
                uncategorized += 1

        for row in role_rows.values():
            count = row["count"]
            if count == 0:
                row["status"] = "MISSING"
            elif count < low_threshold:
                row["status"] = "LOW"
            elif count < thin_threshold:
                row["status"] = "THIN"
            else:
                row["status"] = "OK"

        roles = sorted(role_rows.values(), key=lambda item: (item["count"], item["category"], item["role"]))
        summary: dict[str, int] = {"MISSING": 0, "LOW": 0, "THIN": 0, "OK": 0}
        for row in roles:
            summary[row["status"]] = summary.get(row["status"], 0) + 1

        return {
            "total_loaded": len(jobs),
            "considered": considered,
            "skipped_geo": skipped_geo,
            "skipped_experience": skipped_experience,
            "uncategorized": uncategorized,
            "thresholds": {"low": low_threshold, "thin": thin_threshold, "max_years": max_years},
            "summary": summary,
            "categories": [{"category": name, "count": count} for name, count in category_counts.items()],
            "roles": roles,
            "missing": [row for row in roles if row["status"] == "MISSING"],
            "low": [row for row in roles if row["status"] == "LOW"],
            "thin": [row for row in roles if row["status"] == "THIN"],
        }
    except Exception as e:
        logger.error(f"Error getting job coverage: {e}")
        raise HTTPException(status_code=500, detail="Error getting job coverage")


@router.get("/scraper-status")
async def get_scraper_status(limit: int = Query(10, ge=1, le=50), db=Depends(get_db)):
    """Return latest cloud scraper ETL runs from Postgres ingest_runs."""
    if not hasattr(db, "session"):
        return {"runs": [], "message": "Scraper run history is available for Postgres-backed deployments."}
    try:
        from sqlalchemy import select
        from app.db.schema import IngestRun

        with db.session() as session:
            rows = session.execute(
                select(IngestRun).order_by(IngestRun.started_at.desc()).limit(limit)
            ).scalars().all()
            return {
                "runs": [
                    {
                        "id": str(row.id),
                        "source_name": row.source_name,
                        "pipeline_name": row.pipeline_name,
                        "schedule_type": row.schedule_type,
                        "status": row.status,
                        "started_at": row.started_at,
                        "finished_at": row.finished_at,
                        "records_seen": row.records_seen,
                        "records_staged": row.records_staged,
                        "records_inserted": row.records_inserted,
                        "records_updated": row.records_updated,
                        "records_failed": row.records_failed,
                        "error_message": row.error_message,
                    }
                    for row in rows
                ]
            }
    except Exception as e:
        logger.error(f"Error getting scraper status: {e}")
        raise HTTPException(status_code=500, detail="Error getting scraper status")


@router.get("/pipeline-status")
async def get_pipeline_status(db=Depends(get_db)):
    """Return lightweight job pipeline health for dashboard/UI diagnostics."""
    try:
        payload: dict[str, Any] = {
            "total_jobs": 0,
            "active_jobs": 0,
            "inactive_jobs": 0,
            "last_scraped_at": None,
            "last_run": None,
            "backend": db.__class__.__name__,
        }
        if hasattr(db, "session"):
            from sqlalchemy import func, select, text
            from app.db.schema import IngestRun, Job, MasterJob

            with db.session() as session:
                table_name = "master_jobs" if hasattr(db, "_master_jobs_available") and db._master_jobs_available() else "jobs"
                estimated_total = session.execute(
                    text("SELECT GREATEST(reltuples::bigint, 0) FROM pg_class WHERE oid = to_regclass(:table_name)"),
                    {"table_name": table_name},
                ).scalar()
                payload["total_jobs"] = int(estimated_total or 0)
                payload["active_jobs"] = int(estimated_total or 0)
                payload["inactive_jobs"] = 0
                run = session.execute(
                    select(IngestRun).order_by(IngestRun.started_at.desc()).limit(1)
                ).scalar_one_or_none()
                if run:
                    payload["last_run"] = {
                        "id": str(run.id),
                        "source_name": run.source_name,
                        "pipeline_name": run.pipeline_name,
                        "status": run.status,
                        "started_at": run.started_at,
                        "finished_at": run.finished_at,
                        "records_seen": run.records_seen,
                        "records_inserted": run.records_inserted,
                        "records_updated": run.records_updated,
                        "records_failed": run.records_failed,
                    }
                    payload["last_scraped_at"] = run.finished_at or run.started_at
                if table_name == "master_jobs":
                    latest_seen = session.execute(select(func.max(MasterJob.last_seen_at))).scalar()
                else:
                    latest_seen = session.execute(select(func.max(Job.last_seen_at))).scalar()
                if latest_seen:
                    payload["last_scraped_at"] = latest_seen
        else:
            payload["total_jobs"] = int(await db.count_jobs())
            payload["active_jobs"] = int(await db.count_jobs({"status": "active"}))
            payload["inactive_jobs"] = int(await db.count_jobs({"status": "inactive"}))
        return payload
    except Exception as e:
        logger.error(f"Error getting pipeline status: {e}")
        raise HTTPException(status_code=500, detail="Error getting pipeline status")


@router.post("/scrape", response_model=ScrapeResult)
async def trigger_scrape(
    request: Optional[ScrapeRequest] = Body(default=None),
    _: None = Depends(require_internal_api_key),
    db=Depends(get_db),
):
    """Trigger a manual job scraping cycle.

    Runs all configured scraping sources in parallel,
    deduplicates results, classifies for visa compatibility,
    and stores new jobs in the database.

    This endpoint is typically called by:
    - Admin dashboard
    - Cloud Scheduler cron job (every 2 hours)
    """
    from app.services.job_scraper import run_scrape_cycle

    try:
        # Get existing hashes for deduplication
        existing_hashes = await db.get_existing_hashes()

        # Run scrape cycle
        result, jobs = await run_scrape_cycle(
            request=request or ScrapeRequest(),
            existing_hashes=existing_hashes,
        )

        # Store new jobs in database
        if jobs:
            job_dicts = [job.model_dump(mode="json") for job in jobs]
            stored = await db.upsert_jobs_batch(job_dicts)
            logger.info(f"Stored {stored} new jobs in database")
            if db.__class__.__name__ == "PostgresClient":
                try:
                    from app.etl.master_jobs import rebuild_master_jobs
                    rebuild_master_jobs(db)
                except Exception as sync_exc:
                    logger.warning("Master jobs sync failed after manual scrape: %s", sync_exc)

            artifacts = export_jobs(job_dicts)
            if artifacts:
                logger.info(f"Exported jobs: {artifacts}")
                export_rows = [{"artifact": name, "path": path} for name, path in artifacts.items()]
                logger.info("Export artifacts:\n%s", render_table(export_rows, headers=["artifact", "path"]))

        return result

    except Exception as e:
        logger.error(f"Scrape cycle failed: {e}")
        raise HTTPException(status_code=500, detail="Scrape cycle failed")


@router.get("/export")
async def export_all_jobs(_: None = Depends(require_internal_api_key), db=Depends(get_db)):
    """Export all jobs currently in DB to a single rolling CSV/XLSX."""
    try:
        jobs = await db.get_jobs(limit=100000, offset=0)
        artifacts = export_jobs(jobs)
        return {"exported_rows": len(jobs), "artifacts": artifacts}
    except Exception as e:
        logger.error(f"Job export failed: {e}")
        raise HTTPException(status_code=500, detail="Job export failed")


@router.post("/ingest/careers-page")
async def ingest_careers_page(
    payload: dict = Body(...),
    _: None = Depends(require_internal_api_key),
    db=Depends(get_db),
):
    """Scrape EVERY open position from a company careers page or ATS board URL.

    Body: {"url": "https://www.strategy.com/careers"} or a direct ATS link
    (SmartRecruiters / Greenhouse / Lever / Ashby / Workable / Recruitee /
    Teamtailor / BambooHR). Detects the board, ingests all open postings with
    first-party descriptions and direct apply links, and syncs master_jobs.
    """
    from app.services.careers_page_ingest import ingest_careers_url

    url = str((payload or {}).get("url") or "").strip()
    if not url:
        raise HTTPException(status_code=400, detail="Body must include {'url': '<careers page or ATS URL>'}")
    result = await ingest_careers_url(url, db)
    if not result.get("ok"):
        raise HTTPException(status_code=422, detail=result.get("error") or "Ingestion failed")
    return result


@router.get("/detail/{job_id}")
async def get_job_detail(
    job_id: str,
    background_tasks: BackgroundTasks,
    db=Depends(get_db),
    user_id: Optional[str] = Depends(optional_user_id),
):
    """Job detail with taxonomy and per-active-resume ATS score."""
    job = await db.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    # Very thin JD (a title + a sentence): try a quick INLINE hydration with a
    # strict budget so the user who just clicked sees the complete description.
    # Background repair alone only fixed the row for the NEXT visitor.
    _desc_now = clean_description_text(job.get("description") or "")
    if not has_complete_job_description(_desc_now):
        _url = str(job.get("job_url") or job.get("source_url") or "").strip()
        if _url and is_html_fetch_allowed(_url):
            try:
                details = await fetch_full_job_description(_url, timeout=6.0, expand_links=True)
                if details:
                    _repaired = clean_description_text(details.description)
                    if has_complete_job_description(_repaired) and len(_repaired) > len(_desc_now):
                        job = dict(job)
                        job["description"] = details.description
                        meta = dict(job.get("extra_metadata") or {})
                        meta["description_hydrated"] = True
                        meta["description_hydrated_from"] = details.source_url
                        meta["description_extractor"] = details.extractor
                        job["extra_metadata"] = meta

                        async def _persist_inline_repair(job_id: str, description: str, source_url: str, meta: dict) -> None:
                            try:
                                update_description = getattr(db, "update_job_description", None)
                                if update_description:
                                    await update_description(job_id, description, source_url=source_url, extra_metadata=meta)
                            except Exception as exc:  # noqa: BLE001
                                logger.debug("Unable to persist inline-repaired JD for %s: %s", job_id, exc)

                        background_tasks.add_task(
                            _persist_inline_repair, str(job.get("id") or job_id),
                            _repaired, details.source_url or _url, meta,
                        )
            except Exception as exc:  # noqa: BLE001
                logger.debug("Inline JD hydration failed for %s: %s", job_id, exc)

    if _should_schedule_detail_repair(job):
        background_tasks.add_task(_repair_detail_description_background, dict(job), db)
    if _should_schedule_company_link(job):
        background_tasks.add_task(_resolve_company_link_background, dict(job), db)
    title = job.get("title") or ""
    description = job.get("description") or ""
    if not has_complete_job_description(description):
        # A direct detail URL must not bypass the same invariant used by lists.
        # The repair task remains scheduled for retry, while the frontend gets
        # an honest temporary response instead of a partial JD.
        if _should_schedule_detail_repair(job):
            background_tasks.add_task(_repair_detail_description_background, dict(job), db)
        raise HTTPException(
            status_code=409,
            detail="This job description is still being completed from the employer source.",
        )
    cat, rname = categorize(title)
    payload = _apply_job_specific_visa_rules(dict(job))
    payload["taxonomy_category"] = cat
    payload["role"] = rname
    metadata = payload.get("extra_metadata") or {}
    stored_html = metadata.get("description_html") if isinstance(metadata, dict) else None
    description_html = sanitize_job_description_html(stored_html or description)
    if description_html:
        payload["description_html"] = description_html

    resume_text = await _active_resume_text(user_id)
    if resume_text:
        combined = title + "\n" + description
        # Compute score AND the explainable breakdown in one pass so the
        # frontend can show a "Why this score?" tooltip — addresses
        # complaints that the match number "feels random".
        breakdown = score_breakdown(resume_text, combined)
        if isinstance(breakdown.get("score"), int):
            payload["match_score"] = breakdown["score"]
            payload["score_type"] = "resume_match"
        else:
            _set_insufficient_jd_score(payload)
        payload["score_breakdown"] = breakdown
    else:
        payload["match_score"] = _baseline_ats_score(payload)
        payload["score_type"] = "baseline_ats"
        payload["score_breakdown"] = None

    sections = _split_description_points(description)
    for key, value in sections.items():
        if value:
            payload[key] = value
    payload.update(_keyword_payload(resume_text, f"{title}\n{description}"))
    if not _can_score_job_text(title, description):
        payload["strongKeywords"] = []
        payload["missingKeywords"] = []
    payload.update(await _visa_stats_for_company(payload.get("company") or "", db))

    payload["contacts"] = []
    for sensitive_key in (
        "hiring_manager",
        "hiringManager",
        "hiring_manager_name",
        "hiring_manager_email",
        "hiring_manager_linkedin",
    ):
        payload.pop(sensitive_key, None)
    return payload


@router.get("/top-matches")
async def get_top_matches(
    limit: int = Query(10, ge=1, le=25),
    location: Optional[str] = Query(None),
    time_filter: Optional[str] = Query(None),
    visa_only: bool = Query(False),
    min_score: Optional[int] = Query(None, ge=0, le=100),
    fresh_basis: str = Query("posted", description="posted uses posted_at; added uses first_seen/created_at"),
    tz_offset: int = Query(0, description="Client timezone offset in minutes from UTC (JS getTimezoneOffset)"),
    db=Depends(get_db),
    user_id: Optional[str] = Depends(fast_optional_user_id),
):
    """Return the strongest jobs for the user's active resume/preferences."""
    filters: dict[str, Any] = {
        "status": "active",
        "complete_jd_only": True,
        # Top Matches scores and returns the JD, so never use the 900-character
        # candidate-pool projection used by the normal list ranking path.
        "full_description": True,
    }
    if location:
        filters["location"] = location
    if visa_only:
        filters["visa_only"] = True
    fresh_since, fresh_before = _posted_window(time_filter, tz_offset_minutes=tz_offset)
    post_filter_since: Optional[datetime] = None
    post_filter_before: Optional[datetime] = None
    if fresh_since:
        if fresh_basis.strip().lower() in {"added", "first_seen", "database", "created"}:
            filters["first_seen_since"] = max(fresh_since, _visible_jobs_cutoff())
        else:
            filters["seen_since"] = _visible_jobs_cutoff()
            post_filter_since = max(fresh_since, _visible_jobs_cutoff())
            post_filter_before = fresh_before
    else:
        today_since, today_before = _posted_window("today", tz_offset_minutes=tz_offset)
        filters["effective_since"] = today_since or _recent_jobs_cutoff()
        post_filter_since = today_since or _recent_jobs_cutoff()
        post_filter_before = today_before
    resume_text = await _active_resume_text(user_id)
    preferred_roles, preferred_locations = _preference_terms(user_id)
    if not location:
        for preferred_location in preferred_locations:
            preferred_country = normalize_country_code(resolve_country(preferred_location))
            if preferred_country:
                filters["country"] = preferred_country
                break
    terms = _terms_for_role_names(preferred_roles)
    _selected_roles = set(preferred_roles)
    _tier_role_terms = [t.lower() for t in terms if len(str(t).strip()) >= 3]
    _target_categories = _categories_for_role_names(preferred_roles)
    if terms:
        filters["title_terms"] = terms
    candidate_limit = 500 if (post_filter_since or post_filter_before) else min(max(limit * 8, 80), 180)
    response_cache_key = _stable_cache_key("jobs:top:v2", {
        "user_id": user_id or "anon",
        "resume_sig": _resume_signature(resume_text),
        "limit": limit,
        "location": location,
        "time_filter": time_filter,
        "visa_only": visa_only,
        "min_score": min_score,
        "fresh_basis": fresh_basis,
        "tz_offset": tz_offset,
        "filters": filters,
        "preferred_roles": preferred_roles,
        "preferred_locations": preferred_locations,
    })
    cached_response = _get_fast_response(response_cache_key)
    if cached_response is not None:
        return cached_response
    resume_cache = _prepare_resume_tokens(resume_text) if resume_text else None

    def _rank_pool(pool: list, *, apply_window: bool) -> list[dict]:
        rows: list[dict] = []
        for job in pool:
            if not has_complete_job_description(job.get("description") or ""):
                continue
            meta = job.get("extra_metadata") or {}
            if not isinstance(meta, dict):
                meta = {}
            cat, rname = categorize(f"{job.get('title') or ''} {job.get('company') or ''}")
            item = _apply_job_specific_visa_rules(dict(job))
            if apply_window and (post_filter_since or post_filter_before) and not _in_datetime_window(
                item.get("posted_at"),
                post_filter_since,
                post_filter_before,
            ):
                continue
            item["taxonomy_category"] = cat
            item["role"] = rname
            if resume_text:
                title = item.get("title") or ""
                description = item.get("description") or ""
                if _can_score_job_text(title, description):
                    item["match_score"] = _cached_score_job_against_resume(
                        resume_text,
                        f"{title}\n{description}",
                        resume_cache=resume_cache,
                        job_id=str(item.get("id") or ""),
                    )
                    item["score_type"] = "resume_match"
                else:
                    _set_insufficient_jd_score(item)
            else:
                item["match_score"] = _baseline_ats_score(item)
                item["score_type"] = "baseline_ats"
            hay = f"{item.get('title') or ''} {rname} {cat}".lower()
            loc_hay = f"{item.get('location') or ''}".lower()
            if isinstance(item.get("match_score"), int) and preferred_roles and any(term.lower() in hay for term in preferred_roles):
                item["match_score"] = min(98, int(item["match_score"] or 0) + 6)
            if isinstance(item.get("match_score"), int) and preferred_locations and any(term in loc_hay for term in preferred_locations):
                item["match_score"] = min(98, int(item["match_score"] or 0) + 3)
            item["preference_match"] = _job_matches_preferences(item, preferred_roles, preferred_locations)
            item["relevance_tier"] = _relevance_tier(item, _selected_roles, _tier_role_terms, _target_categories, preferred_locations)
            rows.append(item)
        return rows

    jobs = await db.get_jobs(filters=filters, limit=candidate_limit, offset=0)
    ranked = _rank_pool(jobs, apply_window=True)

    # Never leave "Featured Positions Today" empty while ANY jobs exist.
    # A stale scrape day, weekend lull, or narrow target roles used to zero
    # this out (the old fallback still pinned effective_since to today).
    # Relax progressively: drop the posted-today window, then role terms.
    if not ranked:
        relaxed = {k: v for k, v in filters.items() if k not in ("effective_since", "seen_since", "first_seen_since")}
        relaxed["seen_since"] = _visible_jobs_cutoff()
        for attempt in (relaxed, {k: v for k, v in relaxed.items() if k != "title_terms"}):
            pool = await db.get_jobs(filters=attempt, limit=min(max(limit * 8, 80), 180), offset=0)
            ranked = _rank_pool(pool, apply_window=False)
            if ranked:
                filters = attempt
                break
    if min_score is not None:
        ranked = [
            row for row in ranked
            if isinstance(row.get("match_score"), int) and int(row.get("match_score") or 0) >= min_score
        ]
    ranked.sort(key=lambda row: _projection_sort_key(row, tz_offset_minutes=tz_offset))
    # Give every selected role a fair chance to appear on Overview instead of
    # allowing one high-volume title family to consume all featured slots.
    role_diverse: list[dict] = []
    selected_ids: set[str] = set()
    for preferred_role in preferred_roles:
        role_terms = _terms_for_role_names([preferred_role])
        match = next(
            (
                row for row in ranked
                if str(row.get("id") or "") not in selected_ids
                and _job_matches_role_terms(row, [preferred_role], role_terms)
            ),
            None,
        )
        if match:
            role_diverse.append(match)
            selected_ids.add(str(match.get("id") or ""))
    role_diverse.extend(row for row in ranked if str(row.get("id") or "") not in selected_ids)
    ranked = role_diverse
    response_payload = {
        "jobs": ranked[:limit],
        "total": len(ranked),
        "page": 1,
        "page_size": limit,
        "total_pages": 1,
        "filters_applied": {**filters, "min_score": min_score, "fresh_basis": fresh_basis},
        "target_roles": preferred_roles,
        "target_country": filters.get("country"),
    }
    _store_fast_response(response_cache_key, response_payload)
    return response_payload


@router.get("/{job_id}")
async def get_job(job_id: str, db=Depends(get_db)):
    """Get a single job posting by ID."""
    job = await db.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if not has_complete_job_description(job.get("description") or ""):
        raise HTTPException(
            status_code=409,
            detail="This job description is still being completed from the employer source.",
        )
    return job

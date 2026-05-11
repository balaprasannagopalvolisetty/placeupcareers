"""
FinalScout Enrichment Client

FinalScout (https://finalscout.com) provides LinkedIn profile -> verified
email enrichment. Three core "find" patterns:

  /v1/find/linkedin/single   - linkedin URL -> email           (5/sec)
  /v1/find/professional/single - name + company -> email       (5/sec)
  /v1/find/author/single     - article URL -> author email     (5/sec)

Plus matching bulk endpoints (2/sec):
  /v1/find/linkedin/bulk
  /v1/find/professional/bulk
  /v1/find/author/bulk
  /v1/find/bulk/status     - check job status   (25/sec)
  /v1/find/bulk/dump       - get partial results (25/sec)
  /v1/find/bulk/export     - export full results (25/sec)

Plus profile lookups (500/sec, mostly cache hits):
  /v1/profile/person       - person profile
  /v1/profile/company      - company profile

Each PlaceUp user can BYOK their own FinalScout key; PlaceUp pays $0.

Docs: https://finalscout.com/public/doc/api.html
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
from datetime import datetime
from typing import Any, Optional
from urllib.parse import urlparse, urlunparse

import httpx

from app.config import settings
from app.models.contact import (
    Contact, ContactConfidence, ContactRole, ContactSource,
)

logger = logging.getLogger(__name__)

# Verified live endpoint via the /api/contacts/debug/finalscout probe:
#   POST https://api.finalscout.com/v1/find/linkedin/single
#   Authorization: Bearer <key>
#   { "linkedin_url": "https://www.linkedin.com/in/<slug>" }
FINALSCOUT_BASE = "https://api.finalscout.com/v1"


# ─── Helpers ─────────────────────────────────────────────────

def _classify_role(position: Optional[str]) -> ContactRole:
    if not position:
        return ContactRole.OTHER
    t = position.lower()
    if "talent acquisition" in t or "tech recruit" in t:
        return ContactRole.TALENT_ACQUISITION
    if "recruit" in t:
        return ContactRole.RECRUITER
    if "head of people" in t or "vp people" in t:
        return ContactRole.HEAD_OF_PEOPLE
    if "engineering manager" in t or "eng manager" in t:
        return ContactRole.ENGINEERING_MANAGER
    if "team lead" in t or "tech lead" in t:
        return ContactRole.TEAM_LEAD
    if "hiring manager" in t:
        return ContactRole.HIRING_MANAGER
    return ContactRole.OTHER


def _email_status_to_confidence(status: Optional[str], score: Optional[int]) -> ContactConfidence:
    s = (status or "").lower()
    if s in {"valid", "deliverable", "verified"}:
        return ContactConfidence.VERIFIED
    if s in {"catchall", "accept_all", "risky", "unknown"}:
        return ContactConfidence.PATTERN
    if s in {"invalid", "undeliverable"}:
        return ContactConfidence.GUESSED
    if score is not None:
        if score >= 90: return ContactConfidence.VERIFIED
        if score >= 60: return ContactConfidence.PATTERN
    return ContactConfidence.UNKNOWN


def _resolve_key(byok: Optional[str]) -> str:
    return (byok or settings.finalscout_api_key or "").strip()


def _contact_id(seed: str) -> str:
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]


def normalize_linkedin_url(url: Optional[str]) -> Optional[str]:
    """Canonicalize LinkedIn profile URLs before storing or sending to FinalScout."""
    if not url:
        return None
    value = str(url).strip().strip('"').strip("'")
    if not value or value == "-":
        return None
    if not value.startswith(("http://", "https://")):
        value = "https://" + value
    try:
        parsed = urlparse(value)
    except Exception:
        return value
    host = parsed.netloc.lower()
    if host in {"linkedin.com", "www.linkedin.com"}:
        host = "www.linkedin.com"
    path = parsed.path
    while "//" in path:
        path = path.replace("//", "/")
    return urlunparse(("https", host, path.rstrip("/"), "", "", ""))


def _first_text(*values: Any) -> Optional[str]:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text and text != "-":
            return text
    return None


def _first_nested(mapping: dict, *paths: str) -> Optional[Any]:
    for path in paths:
        current: Any = mapping
        for part in path.split("."):
            if not isinstance(current, dict):
                current = None
                break
            current = current.get(part)
        if current not in (None, "", "-"):
            return current
    return None


def _extract_email(item: dict) -> tuple[Optional[str], Optional[str], Optional[int], Optional[str]]:
    direct = _first_text(
        item.get("email"),
        item.get("work_email"),
        item.get("professional_email"),
        item.get("email_address"),
        _first_nested(item, "contact.email", "person.email"),
    )
    if direct:
        return direct.lower(), item.get("email_status"), item.get("email_score"), item.get("email_type")

    candidates = item.get("emails") or _first_nested(item, "contact.emails", "person.emails") or []
    if isinstance(candidates, dict):
        candidates = [candidates]
    if isinstance(candidates, list):
        for candidate in candidates:
            if isinstance(candidate, str):
                return candidate.strip().lower(), None, None, None
            if isinstance(candidate, dict):
                email = _first_text(
                    candidate.get("email"),
                    candidate.get("value"),
                    candidate.get("address"),
                    candidate.get("email_address"),
                )
                if email:
                    return (
                        email.lower(),
                        candidate.get("status") or candidate.get("email_status"),
                        candidate.get("score") or candidate.get("email_score"),
                        candidate.get("type") or candidate.get("email_type"),
                    )
    return None, item.get("email_status"), item.get("email_score"), item.get("email_type")


def _unwrap_result(payload: dict) -> dict:
    if not isinstance(payload, dict):
        return {}
    data = payload.get("data") or payload.get("contact") or payload.get("person") or payload
    if isinstance(data, dict):
        for key in ("contact", "person", "result"):
            nested = data.get(key)
            if isinstance(nested, dict):
                merged = dict(data)
                merged.update(nested)
                return merged
        return data
    if isinstance(data, list) and data and isinstance(data[0], dict):
        return data[0]
    return {}


def _result_to_contact(item: dict, *, related_job_id: Optional[str] = None) -> Optional[Contact]:
    """Convert a FinalScout result dict (single or webhook contact.change) to a Contact."""
    if not isinstance(item, dict):
        return None
    full_name = _first_text(
        item.get("full_name"),
        item.get("name"),
        _first_nested(item, "profile.full_name", "person.full_name", "contact.full_name"),
    )
    if not full_name:
        first = _first_text(item.get("first_name"), _first_nested(item, "profile.first_name", "person.first_name", "contact.first_name")) or ""
        last = _first_text(item.get("last_name"), _first_nested(item, "profile.last_name", "person.last_name", "contact.last_name")) or ""
        full_name = (f"{first} {last}").strip() or None
    email, email_status, email_score, email_type = _extract_email(item)
    company = _first_text(
        item.get("company"),
        item.get("company_name"),
        _first_nested(item, "current_company.name", "employment.company", "profile.company", "person.current_company.name"),
    ) or "Unknown"
    title = _first_text(item.get("title"), item.get("position"), item.get("headline"), _first_nested(item, "profile.title", "person.headline"))
    linkedin = normalize_linkedin_url(_first_text(
        item.get("linkedin"),
        item.get("linkedin_url"),
        item.get("profile_url"),
        _first_nested(item, "profile.linkedin_url", "person.profile_url", "person.linkedin_url"),
    ))
    confidence = _email_status_to_confidence(email_status, email_score)
    seed = f"finalscout|{company.lower()}|{(email or linkedin or full_name or '').lower()}"
    return Contact(
        id=_contact_id(seed),
        full_name=full_name,
        first_name=_first_text(item.get("first_name"), _first_nested(item, "profile.first_name", "person.first_name", "contact.first_name")),
        last_name=_first_text(item.get("last_name"), _first_nested(item, "profile.last_name", "person.last_name", "contact.last_name")),
        title=title,
        role=_classify_role(title),
        company=company,
        company_domain=_first_text(item.get("company_domain"), item.get("domain"), item.get("domain_original")),
        email=email,
        linkedin_url=linkedin,
        source=ContactSource.FINALSCOUT,
        confidence=confidence,
        source_payload={
            "endpoint": item.get("_endpoint", ""),
            "email_type": email_type,
            "email_score": email_score,
            "email_is_catchall": item.get("email_is_catchall"),
            "email_status": email_status,
            "industry": item.get("industry"),
            "location": item.get("location"),
            "website": item.get("website"),
            "avatar": item.get("avatar"),
            "raw": item,
        },
        related_job_id=related_job_id,
        discovered_at=datetime.utcnow(),
        last_verified_at=(datetime.utcnow() if confidence == ContactConfidence.VERIFIED else None),
    )


async def _request(method: str, path: str, *, api_key: str, **kw) -> Optional[dict]:
    """Shared request caller with consistent error handling.

    Tries the canonical base first; if the canonical 404s (URL drift), tries
    a couple of historically-valid bases so we don't burn credits silently.
    Each call still uses the SAME api key on every variant.
    """
    if not api_key:
        return None
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    headers.update(kw.pop("headers", {}))

    bases = [FINALSCOUT_BASE]  # locked to the verified live endpoint
    last_status: Optional[int] = None
    last_body: str = ""
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            for base in bases:
                url = f"{base}{path}"
                try:
                    r = await client.request(method, url, headers=headers, **kw)
                except httpx.HTTPError as exc:
                    logger.debug("FinalScout %s %s connection error: %s", method, url, exc)
                    continue
                last_status = r.status_code
                last_body = r.text[:500]
                if r.status_code == 404:
                    continue  # try next base
                if r.status_code in (401, 403):
                    logger.warning("FinalScout %s %s: %s — check API key. body=%s", method, url, r.status_code, last_body[:200])
                    return None
                if r.status_code == 429:
                    logger.warning("FinalScout %s %s: rate limited (429), backing off", method, url)
                    await asyncio.sleep(2.0)
                    return None
                r.raise_for_status()
                return r.json()
        logger.warning("FinalScout %s %s: all bases returned 404 (last=%s body=%s)",
                       method, path, last_status, last_body[:200])
        return None
    except httpx.HTTPError as exc:
        logger.warning("FinalScout %s %s error: %s", method, path, exc)
        return None


# ─── Single-find endpoints ────────────────────────────────────

async def find_by_linkedin(
    linkedin_url: str, *,
    enable_personal_email: bool = False,
    enable_generic_email: bool = False,
    related_job_id: Optional[str] = None,
    byok_api_key: Optional[str] = None,
) -> Optional[Contact]:
    """LinkedIn URL → verified work email. (1 credit per call)"""
    api_key = _resolve_key(byok_api_key)
    linkedin_url = normalize_linkedin_url(linkedin_url)
    if not api_key or not linkedin_url:
        return None
    payload = await _request("POST", "/find/linkedin/single", api_key=api_key, json={
        "person": {"linkedin_url": linkedin_url},
        "enable_personal_email": enable_personal_email,
        "enable_generic_email": enable_generic_email,
    })
    if not payload:
        return None
    data = _unwrap_result(payload)
    if isinstance(data, dict):
        data["_endpoint"] = "find/linkedin/single"
    return _result_to_contact(data, related_job_id=related_job_id)


async def find_by_professional(
    *, first_name: str, last_name: str, company: str,
    company_domain: Optional[str] = None,
    enable_personal_email: bool = False,
    enable_generic_email: bool = False,
    related_job_id: Optional[str] = None,
    byok_api_key: Optional[str] = None,
) -> Optional[Contact]:
    """Name + company → verified work email. (1 credit per call)"""
    api_key = _resolve_key(byok_api_key)
    if not api_key or not first_name or not last_name or not (company or company_domain):
        return None
    person = {
        "first_name": first_name.strip(),
        "last_name": last_name.strip(),
    }
    if company_domain: person["domain"] = company_domain
    if company: person["company_name"] = company
    body = {
        "person": person,
        "enable_personal_email": enable_personal_email,
        "enable_generic_email": enable_generic_email,
    }
    payload = await _request("POST", "/find/professional/single", api_key=api_key, json=body)
    if not payload:
        return None
    data = _unwrap_result(payload)
    if isinstance(data, dict):
        data["_endpoint"] = "find/professional/single"
    return _result_to_contact(data, related_job_id=related_job_id)


# ─── Bulk-find endpoints ─────────────────────────────────────

async def submit_linkedin_bulk(
    linkedin_urls: list[str], *,
    name: str = "PlaceUp bulk linkedin lookup",
    duplicate: str = "skip_duplicates",
    tags: Optional[list[str]] = None,
    enable_personal_email: bool = False,
    enable_generic_email: bool = False,
    webhook_url: Optional[str] = None,
    webhook_subscribe_events: Optional[list[str]] = None,
    byok_api_key: Optional[str] = None,
) -> Optional[str]:
    """Submit a bulk LinkedIn-URL job. Returns the task_id (string) or None."""
    api_key = _resolve_key(byok_api_key)
    if not api_key or not linkedin_urls:
        return None
    body = {
        "name": name,
        "duplicate": duplicate,
        "persons": [{"linkedin": u} for u in (normalize_linkedin_url(u) for u in linkedin_urls) if u],
        "enable_personal_email": enable_personal_email,
        "enable_generic_email": enable_generic_email,
    }
    if tags: body["tags"] = tags
    if webhook_url:
        body["webhook_url"] = webhook_url
        if webhook_subscribe_events:
            body["webhook_subscribe_events"] = webhook_subscribe_events
    payload = await _request("POST", "/find/linkedin/bulk", api_key=api_key, json=body)
    if not payload:
        return None
    return (payload.get("data") or payload).get("id") or (payload.get("data") or payload).get("task_id")


async def submit_professional_bulk(
    persons: list[dict], *,
    name: str = "PlaceUp bulk professional lookup",
    duplicate: str = "skip_duplicates",
    tags: Optional[list[str]] = None,
    enable_personal_email: bool = False,
    enable_generic_email: bool = False,
    webhook_url: Optional[str] = None,
    webhook_subscribe_events: Optional[list[str]] = None,
    byok_api_key: Optional[str] = None,
) -> Optional[str]:
    """Submit a bulk professional (name+company) lookup job.
    persons = [{"first_name": "Jane", "last_name": "Doe", "company": "Stripe"}, ...]
    """
    api_key = _resolve_key(byok_api_key)
    if not api_key or not persons:
        return None
    body = {
        "name": name,
        "duplicate": duplicate,
        "persons": persons,
        "enable_personal_email": enable_personal_email,
        "enable_generic_email": enable_generic_email,
    }
    if tags: body["tags"] = tags
    if webhook_url:
        body["webhook_url"] = webhook_url
        if webhook_subscribe_events:
            body["webhook_subscribe_events"] = webhook_subscribe_events
    payload = await _request("POST", "/find/professional/bulk", api_key=api_key, json=body)
    if not payload:
        return None
    return (payload.get("data") or payload).get("id") or (payload.get("data") or payload).get("task_id")


async def get_bulk_status(task_id: str, *, byok_api_key: Optional[str] = None) -> Optional[dict]:
    """Check bulk-task status (Pending / Running / Completed)."""
    api_key = _resolve_key(byok_api_key)
    if not api_key or not task_id:
        return None
    return await _request("GET", "/find/bulk/status", api_key=api_key, params={"id": task_id})


async def dump_bulk_results(
    task_id: str, *,
    page: int = 1, page_size: int = 100,
    byok_api_key: Optional[str] = None,
) -> Optional[list[dict]]:
    """Stream partial results from a bulk task."""
    api_key = _resolve_key(byok_api_key)
    if not api_key or not task_id:
        return None
    payload = await _request("GET", "/find/bulk/dump", api_key=api_key,
                              params={"id": task_id, "page": page, "page_size": page_size})
    if not payload:
        return None
    data = payload.get("data") or payload.get("contacts") or payload
    if isinstance(data, dict):
        data = data.get("contacts") or data.get("items") or []
    return data if isinstance(data, list) else None


async def export_bulk_results(task_id: str, *, byok_api_key: Optional[str] = None) -> Optional[dict]:
    """Get a download URL / full export for a completed bulk task."""
    api_key = _resolve_key(byok_api_key)
    if not api_key or not task_id:
        return None
    return await _request("GET", "/find/bulk/export", api_key=api_key, params={"id": task_id})


async def wait_for_bulk_completion(
    task_id: str, *,
    poll_interval: float = 5.0,
    max_wait_seconds: int = 1800,
    byok_api_key: Optional[str] = None,
) -> Optional[dict]:
    """Poll bulk-status until status=Completed or max_wait elapses.
    Returns the final status payload, or None on timeout/error.
    """
    elapsed = 0.0
    while elapsed < max_wait_seconds:
        status = await get_bulk_status(task_id, byok_api_key=byok_api_key)
        if status:
            payload = status.get("data") or status
            current = (payload.get("status") or "").lower()
            logger.info("FinalScout task %s: %s (%s/%s)",
                        task_id, current, payload.get("finished"), payload.get("total"))
            if current in {"completed", "finished", "done", "success"}:
                return status
            if current in {"failed", "error", "cancelled"}:
                logger.warning("FinalScout task %s ended with status=%s", task_id, current)
                return status
        await asyncio.sleep(poll_interval)
        elapsed += poll_interval
    logger.warning("FinalScout task %s: still running after %ss", task_id, max_wait_seconds)
    return None

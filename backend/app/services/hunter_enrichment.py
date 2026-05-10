"""
Hunter.io Enrichment Client (Full v2 API coverage)

Wired endpoints:
  domain-search       - emails for a domain
  email-finder        - construct + verify email for a known person
  email-verifier      - check if a given email is deliverable
  person-enrichment   - profile data for a known email (name, company, role)
  company-enrichment  - org info for a domain (industry, size, tech stack)
  combined-enrichment - person + company in one call
  discover            - find companies that match criteria

Free tier: 25 searches/month + 50 verifications/month.
Each PlaceUp user can BYOK their own free quota; PlaceUp pays $0.

Docs: https://hunter.io/api-documentation/v2
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime
from typing import Any, Optional

import httpx

from app.config import settings
from app.models.contact import (
    Contact, ContactConfidence, ContactRole, ContactSource,
)

logger = logging.getLogger(__name__)

HUNTER_BASE = "https://api.hunter.io/v2"


def _classify_role(position: Optional[str], department: Optional[str] = None) -> ContactRole:
    text = " ".join(s for s in (position, department) if s).lower()
    if not text:
        return ContactRole.OTHER
    if "talent acquisition" in text or "tech recruit" in text:
        return ContactRole.TALENT_ACQUISITION
    if "recruit" in text:
        return ContactRole.RECRUITER
    if "head of people" in text or "vp people" in text or "chief people" in text:
        return ContactRole.HEAD_OF_PEOPLE
    if "engineering manager" in text or "eng manager" in text:
        return ContactRole.ENGINEERING_MANAGER
    if "team lead" in text or "tech lead" in text:
        return ContactRole.TEAM_LEAD
    if "hiring manager" in text:
        return ContactRole.HIRING_MANAGER
    if "human resources" in text or department == "hr":
        return ContactRole.TALENT_ACQUISITION
    return ContactRole.OTHER


def _hunter_confidence(score: Optional[int], verification: Optional[dict]) -> ContactConfidence:
    if verification:
        result = (verification.get("result") or verification.get("status") or "").lower()
        if result == "deliverable":
            return ContactConfidence.VERIFIED
        if result in ("risky", "unknown", "accept_all"):
            return ContactConfidence.PATTERN
        if result == "undeliverable":
            return ContactConfidence.GUESSED
    if score is not None:
        if score >= 90:
            return ContactConfidence.VERIFIED
        if score >= 60:
            return ContactConfidence.PATTERN
        return ContactConfidence.GUESSED
    return ContactConfidence.UNKNOWN


def _contact_id(company: str, email: Optional[str], name: Optional[str]) -> str:
    raw = f"hunter|{company.lower()}|{(email or '').lower()}|{(name or '').lower()}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _resolve_key(byok: Optional[str]) -> str:
    return (byok or settings.hunter_api_key or "").strip()


async def _get(endpoint: str, params: dict, *, api_key: str, hard_timeout: float = 12.0) -> Optional[dict]:
    """Shared GET caller. Hard timeout (default 12s) prevents hangs that kill the run."""
    import asyncio
    if not api_key:
        return None
    url = f"{HUNTER_BASE}/{endpoint}"
    p = {**params, "api_key": api_key}

    async def _do():
        async with httpx.AsyncClient(timeout=httpx.Timeout(connect=5.0, read=10.0, write=5.0, pool=5.0)) as client:
            r = await client.get(url, params=p)
            if r.status_code in (401, 403):
                logger.warning("Hunter %s: %s — check API key", endpoint, r.status_code)
                return None
            if r.status_code == 429:
                logger.warning("Hunter %s: rate limited (429)", endpoint)
                return None
            if r.status_code == 400:
                # Often "domain not in our database" -- not worth retrying
                return None
            r.raise_for_status()
            return r.json()

    try:
        return await asyncio.wait_for(_do(), timeout=hard_timeout)
    except asyncio.TimeoutError:
        logger.warning("Hunter %s: hard timeout (%ss) — skipping", endpoint, hard_timeout)
        return None
    except httpx.HTTPError as exc:
        logger.warning("Hunter %s error: %s", endpoint, exc)
        return None
    except Exception as exc:
        logger.warning("Hunter %s unexpected: %s", endpoint, exc)
        return None


# ─── Endpoint 1: Domain Search ───────────────────────────────

async def domain_search(
    domain: str, *, company: Optional[str] = None, limit: int = 10,
    department: Optional[str] = None, related_job_id: Optional[str] = None,
    byok_api_key: Optional[str] = None,
) -> list[Contact]:
    """Public emails Hunter has on file for a domain (1 search credit)."""
    api_key = _resolve_key(byok_api_key)
    domain = (domain or "").strip().lower()
    if not api_key or not domain:
        return []
    params = {"domain": domain, "limit": min(limit, 100)}
    if department:
        params["department"] = department
    payload = await _get("domain-search", params, api_key=api_key)
    if not payload:
        return []
    data = payload.get("data") or {}
    emails = data.get("emails") or []
    pattern = (data.get("pattern") or "").lower() or None
    org_name = company or (data.get("organization") or domain)

    contacts = []
    for item in emails[:limit]:
        try:
            full_name = " ".join(p for p in (item.get("first_name"), item.get("last_name")) if p).strip() or None
            email = (item.get("value") or "").strip().lower() or None
            position = item.get("position")
            confidence = _hunter_confidence(item.get("confidence"), item.get("verification"))
            contacts.append(Contact(
                id=_contact_id(org_name, email, full_name),
                full_name=full_name, first_name=item.get("first_name"), last_name=item.get("last_name"),
                title=position, role=_classify_role(position, item.get("department")),
                company=org_name, company_domain=domain,
                email=email, linkedin_url=item.get("linkedin"),
                source=ContactSource.HUNTER, confidence=confidence,
                source_payload={"endpoint": "domain-search", "type": item.get("type"),
                                "department": item.get("department"), "seniority": item.get("seniority"),
                                "confidence": item.get("confidence"), "pattern": pattern,
                                "twitter": item.get("twitter")},
                related_job_id=related_job_id, discovered_at=datetime.utcnow(),
            ))
        except Exception as exc:
            logger.debug("Hunter domain-search: skip: %s", exc)

    logger.info("Hunter domain-search %s: %s emails (pattern=%s)", domain, len(contacts), pattern)
    return contacts


# ─── Endpoint 2: Email Finder ────────────────────────────────

async def email_finder(
    *, domain: str, first_name: str, last_name: str,
    company: Optional[str] = None, related_job_id: Optional[str] = None,
    byok_api_key: Optional[str] = None,
) -> Optional[Contact]:
    """Construct + verify email for a known person (1 search credit)."""
    api_key = _resolve_key(byok_api_key)
    if not api_key or not domain or not first_name or not last_name:
        return None
    payload = await _get("email-finder",
                         {"domain": domain, "first_name": first_name, "last_name": last_name},
                         api_key=api_key)
    if not payload:
        return None
    data = payload.get("data") or {}
    email = (data.get("email") or "").strip().lower() or None
    if not email:
        return None
    confidence = _hunter_confidence(data.get("score"), data.get("verification"))
    return Contact(
        id=_contact_id(company or domain, email, f"{first_name} {last_name}"),
        full_name=f"{first_name.strip()} {last_name.strip()}",
        first_name=first_name.strip(), last_name=last_name.strip(),
        title=data.get("position"), role=_classify_role(data.get("position")),
        company=company or data.get("company") or domain, company_domain=domain,
        email=email, linkedin_url=data.get("linkedin_url"),
        source=ContactSource.HUNTER, confidence=confidence,
        source_payload={"endpoint": "email-finder", "score": data.get("score"),
                        "sources": (data.get("sources") or [])[:3]},
        related_job_id=related_job_id, discovered_at=datetime.utcnow(),
        last_verified_at=datetime.utcnow() if confidence == ContactConfidence.VERIFIED else None,
    )


# ─── Endpoint 3: Email Verifier ──────────────────────────────

async def email_verifier(email: str, *, byok_api_key: Optional[str] = None) -> dict:
    """Check if an email is deliverable (1 verification credit, separate quota)."""
    api_key = _resolve_key(byok_api_key)
    if not api_key or not email:
        return {"email": email, "result": "unknown", "score": 0}
    payload = await _get("email-verifier", {"email": email.lower().strip()}, api_key=api_key)
    if not payload:
        return {"email": email, "result": "unknown", "score": 0}
    d = payload.get("data") or {}
    return {
        "email": email,
        "result": d.get("status") or d.get("result"),
        "score": d.get("score"),
        "regexp": d.get("regexp"), "gibberish": d.get("gibberish"),
        "disposable": d.get("disposable"), "webmail": d.get("webmail"),
        "mx_records": d.get("mx_records"), "smtp_server": d.get("smtp_server"),
        "smtp_check": d.get("smtp_check"), "accept_all": d.get("accept_all"),
        "block": d.get("block"), "sources": (d.get("sources") or [])[:3],
    }


# ─── Endpoint 4: Person Enrichment ───────────────────────────

async def person_enrichment(email: str, *, byok_api_key: Optional[str] = None) -> Optional[Contact]:
    """Profile data for a known email — name, company, role, social links."""
    api_key = _resolve_key(byok_api_key)
    if not api_key or not email:
        return None
    payload = await _get("people/find", {"email": email.lower().strip()}, api_key=api_key)
    if not payload:
        return None
    d = payload.get("data") or {}
    name_obj = d.get("name") or {}
    full_name = name_obj.get("fullName") or " ".join(p for p in (name_obj.get("givenName"), name_obj.get("familyName")) if p).strip() or None
    employment = d.get("employment") or {}
    company_name = employment.get("name") or "Unknown"
    domain = employment.get("domain") or (email.split("@", 1)[1] if "@" in email else "")
    title = employment.get("title")
    return Contact(
        id=_contact_id(company_name, email, full_name),
        full_name=full_name, first_name=name_obj.get("givenName"), last_name=name_obj.get("familyName"),
        title=title, role=_classify_role(title),
        company=company_name, company_domain=domain,
        email=email.lower(),
        linkedin_url=(d.get("linkedin") or {}).get("handle") and f"https://linkedin.com/in/{(d.get('linkedin') or {}).get('handle')}" or None,
        source=ContactSource.HUNTER, confidence=ContactConfidence.VERIFIED,
        source_payload={"endpoint": "person-enrichment", "seniority": employment.get("seniority"),
                        "role": employment.get("role"), "geo": d.get("geo"),
                        "twitter": (d.get("twitter") or {}).get("handle"),
                        "github": (d.get("github") or {}).get("handle")},
        discovered_at=datetime.utcnow(), last_verified_at=datetime.utcnow(),
    )


# ─── Endpoint 5: Company Enrichment ──────────────────────────

async def company_enrichment(domain: str, *, byok_api_key: Optional[str] = None) -> dict:
    """Org info for a domain: industry, size, tech stack, social profiles."""
    api_key = _resolve_key(byok_api_key)
    if not api_key or not domain:
        return {}
    payload = await _get("companies/find", {"domain": domain.lower().strip()}, api_key=api_key)
    if not payload:
        return {}
    d = payload.get("data") or {}
    return {
        "name": d.get("name"), "domain": d.get("domain"),
        "description": d.get("description"), "founded": d.get("foundedYear"),
        "industry": (d.get("category") or {}).get("industry"),
        "sector": (d.get("category") or {}).get("sector"),
        "employees": (d.get("metrics") or {}).get("employees"),
        "estimated_annual_revenue": (d.get("metrics") or {}).get("estimatedAnnualRevenue"),
        "linkedin_handle": (d.get("linkedin") or {}).get("handle"),
        "twitter_handle": (d.get("twitter") or {}).get("handle"),
        "tech": d.get("tech") or [],
        "tags": d.get("tags") or [],
        "city": (d.get("geo") or {}).get("city"),
        "state": (d.get("geo") or {}).get("state"),
        "country": (d.get("geo") or {}).get("country"),
    }


# ─── Endpoint 6: Combined Enrichment ─────────────────────────

async def combined_enrichment(email: str, *, byok_api_key: Optional[str] = None) -> dict:
    """Person + company in one call (cheaper than two separate calls)."""
    api_key = _resolve_key(byok_api_key)
    if not api_key or not email:
        return {}
    payload = await _get("combined/find", {"email": email.lower().strip()}, api_key=api_key)
    if not payload:
        return {}
    d = payload.get("data") or {}
    return {
        "person": d.get("person") or {},
        "company": d.get("company") or {},
    }


# ─── Endpoint 7: Discover ────────────────────────────────────

async def discover_companies(
    *, query: Optional[str] = None, industry: Optional[str] = None,
    company_size: Optional[str] = None, country: Optional[str] = None,
    technology: Optional[str] = None, limit: int = 25,
    byok_api_key: Optional[str] = None,
) -> list[dict]:
    """Find companies matching criteria (industry, size, tech stack, location).

    POST /v2/discover. 1 credit per page returned.
    """
    api_key = _resolve_key(byok_api_key)
    if not api_key:
        return []
    body = {"limit": min(limit, 25)}
    filters = {}
    if query:
        filters["query"] = query
    if industry:
        filters["industry"] = industry
    if company_size:
        filters["company_size"] = company_size
    if country:
        filters["country"] = country
    if technology:
        filters["technology"] = technology
    if filters:
        body["filters"] = filters

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.post(f"{HUNTER_BASE}/discover", json=body, params={"api_key": api_key})
            if r.status_code in (401, 403, 429):
                logger.warning("Hunter discover: %s", r.status_code)
                return []
            r.raise_for_status()
            payload = r.json()
    except httpx.HTTPError as exc:
        logger.warning("Hunter discover error: %s", exc)
        return []

    results = (payload.get("data") or {}).get("results") or payload.get("data") or []
    return results if isinstance(results, list) else []

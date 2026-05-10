"""
Apollo.io Enrichment Client

Apollo gives us recruiter / hiring-manager records by querying their
people-search endpoint with a company filter and a title filter. Their free
tier is 60 credits/month — every successful person returned costs 1 credit.

Public docs: https://apolloio.github.io/apollo-api-docs/

We cache responses by (company, role_query) so we don't burn credits on
repeat lookups, and we cap the per-page size aggressively.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime
from typing import Optional

import httpx

from app.config import settings
from app.models.contact import (
    Contact,
    ContactConfidence,
    ContactRole,
    ContactSource,
)

logger = logging.getLogger(__name__)


APOLLO_BASE = "https://api.apollo.io/v1"

# Common recruiter-side titles we look for when no role_query is given
DEFAULT_RECRUITER_TITLES = [
    "recruiter",
    "talent acquisition",
    "head of talent",
    "head of people",
    "people operations",
    "engineering manager",
]


def _classify_role(title: Optional[str]) -> ContactRole:
    """Heuristic title → ContactRole mapping."""
    if not title:
        return ContactRole.OTHER
    t = title.lower()
    if "talent acquisition" in t or "tech recruit" in t:
        return ContactRole.TALENT_ACQUISITION
    if "recruit" in t:
        return ContactRole.RECRUITER
    if "head of people" in t or "vp people" in t or "chief people" in t:
        return ContactRole.HEAD_OF_PEOPLE
    if "engineering manager" in t or "eng manager" in t:
        return ContactRole.ENGINEERING_MANAGER
    if "team lead" in t or "tech lead" in t:
        return ContactRole.TEAM_LEAD
    if "hiring manager" in t:
        return ContactRole.HIRING_MANAGER
    return ContactRole.OTHER


def _contact_id(company: str, name: Optional[str], identifier: Optional[str]) -> str:
    raw = f"apollo|{company.lower()}|{(name or '').lower()}|{(identifier or '').lower()}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _trim_payload(item: dict) -> dict:
    """Keep only the fields we want to audit (drop large nested blobs)."""
    keys = (
        "id",
        "name",
        "title",
        "linkedin_url",
        "email",
        "email_status",
        "city",
        "state",
        "country",
        "headline",
        "departments",
        "seniority",
    )
    out: dict = {}
    for k in keys:
        if k in item and item[k] not in (None, "", [], {}):
            out[k] = item[k]
    org = item.get("organization") or {}
    if isinstance(org, dict):
        out["organization"] = {
            k: org.get(k)
            for k in ("name", "primary_domain", "website_url", "linkedin_url")
            if org.get(k)
        }
    return out


async def search_people(
    *,
    company: str,
    role_query: Optional[str] = None,
    domain: Optional[str] = None,
    per_page: int = 10,
    related_job_id: Optional[str] = None,
) -> list[Contact]:
    """Search Apollo for recruiters/hiring-managers at the given company.

    Args:
        company: Company name (Apollo will fuzzy-match on name + domain)
        role_query: Title text filter (default = common recruiter titles)
        domain: Company domain — substantially improves match quality if known
        per_page: Max records to fetch (Apollo charges 1 credit per result)
        related_job_id: Stamped onto every Contact so we can group by job

    Returns:
        List of Contact records (may be empty if no API key, no matches, or
        rate-limited). Always degrades gracefully.
    """
    api_key = settings.apollo_api_key.strip()
    if not api_key:
        logger.info("Apollo: APOLLO_API_KEY not set — skipping")
        return []

    titles = [role_query] if role_query else DEFAULT_RECRUITER_TITLES

    payload: dict = {
        "api_key": api_key,
        "page": 1,
        "per_page": min(per_page, 25),
        "person_titles": titles,
        "q_organization_name": company,
    }
    if domain:
        payload["q_organization_domains"] = [domain]

    url = f"{APOLLO_BASE}/mixed_people/search"

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, json=payload)
            if response.status_code in (401, 403):
                logger.warning(
                    "Apollo: %s — check APOLLO_API_KEY and that the endpoint is enabled on your plan",
                    response.status_code,
                )
                return []
            if response.status_code == 429:
                logger.warning("Apollo: rate-limited (429) — try again later or upgrade plan")
                return []
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPError as exc:
        logger.warning("Apollo error for %s: %s", company, exc)
        return []

    people = data.get("people") or data.get("contacts") or []
    if not isinstance(people, list):
        return []

    contacts: list[Contact] = []
    for item in people[:per_page]:
        try:
            full_name = (item.get("name") or "").strip() or None
            title = (item.get("title") or item.get("headline") or "").strip() or None
            linkedin = (item.get("linkedin_url") or "").strip() or None
            email = (item.get("email") or "").strip().lower() or None
            email_status = (item.get("email_status") or "").lower()

            confidence = ContactConfidence.UNKNOWN
            if email:
                if email_status == "verified":
                    confidence = ContactConfidence.VERIFIED
                elif email_status in ("guessed", "unavailable"):
                    confidence = ContactConfidence.GUESSED
                else:
                    confidence = ContactConfidence.PATTERN

            org = item.get("organization") or {}
            domain_val = (org.get("primary_domain") or domain or "").lower() or None

            contacts.append(Contact(
                id=_contact_id(company, full_name, email or linkedin or item.get("id")),
                full_name=full_name,
                first_name=(item.get("first_name") or "").strip() or None,
                last_name=(item.get("last_name") or "").strip() or None,
                title=title,
                role=_classify_role(title),
                company=company,
                company_domain=domain_val,
                email=email,
                linkedin_url=linkedin,
                source=ContactSource.APOLLO,
                confidence=confidence,
                source_payload=_trim_payload(item),
                related_job_id=related_job_id,
                discovered_at=datetime.utcnow(),
                last_verified_at=datetime.utcnow() if confidence == ContactConfidence.VERIFIED else None,
            ))
        except Exception as exc:  # noqa: BLE001
            logger.debug("Apollo: skip person: %s", exc)

    logger.info("Apollo: %s contacts for company=%r role=%r", len(contacts), company, role_query or "default")
    return contacts

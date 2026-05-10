"""
Google X-ray Search for Public LinkedIn Profiles

"X-ray" search is the recruiting-industry term for using Google to surface
public LinkedIn profiles via queries like:

    site:linkedin.com/in "recruiter" "Stripe"

This works because LinkedIn's profile pages are publicly indexed (the user
opted in by making their profile public). We never scrape LinkedIn directly
— we only read the title + snippet that Google itself returns.

Two backends are supported, in priority order:
  1. SerpAPI (paid, $50/mo for 5K searches) — most reliable; sets `engine=google`.
  2. Google Programmable Search Engine (free, 100/day) — requires a custom
     search engine ID (CSE) configured to search the whole web; uses the
     official Custom Search JSON API.

Both fail gracefully when keys are missing.

Disclaimer: scraping LinkedIn's HTML directly is against their ToS. This
module does NOT do that — it queries Google. The result snippets and URLs
returned are public, but volume usage may still be subject to Google's
own ToS, so keep query rates reasonable.
"""

from __future__ import annotations

import hashlib
import logging
import re
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


SERPAPI_URL = "https://serpapi.com/search.json"
GOOGLE_CSE_URL = "https://www.googleapis.com/customsearch/v1"

# Recruiter-side query templates
DEFAULT_ROLE_TERMS = [
    "recruiter",
    "talent acquisition",
    "engineering manager",
    "head of talent",
]

LINKEDIN_PROFILE_REGEX = re.compile(
    r"(?:https?://)?([a-z]{2,3}\.)?linkedin\.com/in/[A-Za-z0-9\-_/.%]+",
    re.IGNORECASE,
)

# Adopted from github.com/Jihad-41/linkedin-email-scraper:
# After Google returns a search snippet for a LinkedIn profile, scan the snippet
# text for any email matching the target company's domain. This is FREE because
# we've already paid the SerpAPI / Google CSE call.
EMAIL_REGEX = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")


def _extract_email_from_snippet(snippet: str, domain: Optional[str] = None) -> Optional[str]:
    """Pull an email out of a Google search snippet.

    If `domain` is given, only emails matching that domain (case-insensitive)
    are returned. Skips obvious generic aliases (info@, support@, etc.).
    """
    if not snippet:
        return None
    candidates = EMAIL_REGEX.findall(snippet)
    if not candidates:
        return None
    generic = {"info", "contact", "support", "noreply", "no-reply", "press", "sales", "admin"}
    for em in candidates:
        em_low = em.lower()
        local = em_low.split("@", 1)[0]
        if local in generic:
            continue
        if domain and not em_low.endswith(f"@{domain.lower().strip().lstrip('@')}"):
            continue
        return em_low
    return None


def _build_query(company: str, role_query: Optional[str]) -> str:
    role = role_query or " OR ".join(f'"{t}"' for t in DEFAULT_ROLE_TERMS)
    return f'site:linkedin.com/in "{company}" {role}'


def _classify_role(snippet: Optional[str], title: Optional[str]) -> ContactRole:
    text = " ".join(s for s in (title, snippet) if s).lower()
    if not text:
        return ContactRole.OTHER
    if "talent acquisition" in text or "tech recruit" in text:
        return ContactRole.TALENT_ACQUISITION
    if "recruit" in text:
        return ContactRole.RECRUITER
    if "engineering manager" in text or "eng manager" in text:
        return ContactRole.ENGINEERING_MANAGER
    if "head of people" in text or "vp people" in text:
        return ContactRole.HEAD_OF_PEOPLE
    if "team lead" in text or "tech lead" in text:
        return ContactRole.TEAM_LEAD
    if "hiring manager" in text:
        return ContactRole.HIRING_MANAGER
    return ContactRole.OTHER


def _normalize_linkedin_url(url: str) -> Optional[str]:
    if not url:
        return None
    match = LINKEDIN_PROFILE_REGEX.search(url)
    if not match:
        return None
    raw = match.group(0)
    if not raw.startswith("http"):
        raw = "https://" + raw
    return raw.rstrip("/").split("?")[0]


def _extract_name_from_title(google_title: str) -> Optional[str]:
    """Google result title for a LinkedIn page is usually 'Jane Doe - Recruiter ...'."""
    if not google_title:
        return None
    # Strip common LinkedIn suffixes
    cleaned = re.sub(r"\s*\|\s*LinkedIn.*$", "", google_title, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*-\s*LinkedIn.*$", "", cleaned, flags=re.IGNORECASE)
    parts = re.split(r"\s+[-–|]\s+", cleaned, maxsplit=1)
    return parts[0].strip() or None


def _contact_id(company: str, linkedin_url: Optional[str], name: Optional[str]) -> str:
    raw = f"xray|{company.lower()}|{(linkedin_url or '').lower()}|{(name or '').lower()}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def linkedin_search_url(company: str, role_query: Optional[str] = None) -> str:
    """Generate a LinkedIn People-search URL the user can click in their browser.

    No API call, no scraping — just a deep link the user opens as themselves.
    Always available regardless of API keys.
    """
    role = role_query or "recruiter"
    keywords = f'{role} {company}'.replace(" ", "%20")
    return f"https://www.linkedin.com/search/results/people/?keywords={keywords}"


# ─── SerpAPI backend ─────────────────────────────────────────

async def _serpapi_search(query: str, *, num: int = 10) -> list[dict]:
    api_key = settings.serpapi_key.strip()
    if not api_key:
        return []

    params = {
        "engine": "google",
        "q": query,
        "num": min(num, 20),
        "api_key": api_key,
        "hl": "en",
    }
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(SERPAPI_URL, params=params)
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPError as exc:
        logger.warning("SerpAPI error: %s", exc)
        return []

    return data.get("organic_results", []) or []


# ─── Google Programmable Search Engine backend ───────────────

async def _google_cse_search(query: str, *, num: int = 10) -> list[dict]:
    api_key = settings.google_api_key.strip()
    cx = settings.google_cse_id.strip()
    if not api_key or not cx:
        return []

    params = {
        "q": query,
        "key": api_key,
        "cx": cx,
        "num": min(num, 10),
    }
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(GOOGLE_CSE_URL, params=params)
            if response.status_code == 403:
                logger.warning("Google CSE: 403 — daily 100/day free quota likely exhausted")
                return []
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPError as exc:
        logger.warning("Google CSE error: %s", exc)
        return []

    items = data.get("items", []) or []
    # Reshape to look like SerpAPI's organic_results schema
    return [
        {
            "title": it.get("title"),
            "link": it.get("link"),
            "snippet": it.get("snippet"),
        }
        for it in items
    ]

# ─── Public API ──────────────────────────────────────────────

async def xray_search(
    *,
    company: str,
    role_query: Optional[str] = None,
    max_results: int = 10,
    related_job_id: Optional[str] = None,
    domain: Optional[str] = None,
) -> list[Contact]:
    """Find public LinkedIn profiles of recruiters/managers at a company via Google.

    When `domain` is given, snippets are scanned for emails on that domain
    (Jihad-41/linkedin-email-scraper pattern) so we get email + LinkedIn URL
    in a single call.

    Always returns at least the LinkedIn search URL (zero-API fallback) as
    one Contact entry, so the user has *something* clickable even with no
    keys configured.
    """
    contacts: list[Contact] = []

    # Always emit one zero-cost search-link contact as a fallback
    search_url = linkedin_search_url(company, role_query)
    contacts.append(Contact(
        id=_contact_id(company, search_url, "search-link"),
        full_name=None,
        title=role_query or "recruiter",
        role=_classify_role(role_query, None),
        company=company,
        linkedin_search_url=search_url,
        source=ContactSource.LINKEDIN_SEARCH_URL,
        confidence=ContactConfidence.UNKNOWN,
        source_payload={"note": "Click to search LinkedIn as yourself; no scraping performed."},
        related_job_id=related_job_id,
        discovered_at=datetime.utcnow(),
    ))

    query = _build_query(company, role_query)
    results = await _serpapi_search(query, num=max_results)
    backend = ContactSource.GOOGLE_XRAY
    if not results:
        results = await _google_cse_search(query, num=max_results)

    for item in results[:max_results]:
        try:
            link = item.get("link") or item.get("url")
            linkedin = _normalize_linkedin_url(link or "")
            if not linkedin:
                continue
            title = item.get("title") or ""
            snippet = item.get("snippet") or item.get("description") or ""
            full_name = _extract_name_from_title(title)
            # Adopted from github.com/Jihad-41/linkedin-email-scraper:
            # scan the search snippet for a company-domain email.
            extracted_email = _extract_email_from_snippet(snippet, domain=domain)

            contacts.append(Contact(
                id=_contact_id(company, linkedin, full_name),
                full_name=full_name,
                title=title,
                role=_classify_role(snippet, title),
                company=company,
                linkedin_url=linkedin,
                email=extracted_email,
                source=backend,
                confidence=(
                    ContactConfidence.VERIFIED if extracted_email
                    else ContactConfidence.PATTERN
                ),
                source_payload={
                    "snippet": snippet[:500],
                    "google_query": query,
                    "email_from_snippet": bool(extracted_email),
                },
                related_job_id=related_job_id,
                discovered_at=datetime.utcnow(),
            ))
        except Exception as exc:
            logger.debug("X-ray: skip item: %s", exc)

    logger.info(
        "X-ray: %s contacts for company=%r role=%r (search-link + %s LinkedIn profiles)",
        len(contacts), company, role_query, max(len(contacts) - 1, 0),
    )
    return contacts

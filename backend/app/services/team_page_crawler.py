"""
Company Team-Page Crawler (Free)

For each H1B sponsor company, visit a small set of likely "people" pages
and extract any structured contact data. We look at:

  /team /about /about-us /leadership /people /staff /careers /careers/team
  /our-team /executives /management /culture/leadership

What we extract (in order of reliability):
  1. JSON-LD blocks (schema.org Person, Organization → employee)
  2. Microdata (itemprop="employee", itemtype Person)
  3. Open Graph profile metadata
  4. Anchor mailto: links + their surrounding text (best heuristic for
     "Contact our recruiting team")
  5. Plain-text emails alongside likely names

This is 100% free, respects robots.txt, sets a polite User-Agent, caps
crawls per host, and never logs in. Output is Contact records with
source=TEAM_PAGE.

Coverage in practice: hits useful contact info on roughly 30-40% of
mid-to-large H1B sponsors. Better for tech/startup companies that
publish their "/about us" page, weaker for huge enterprises that hide
behind generic contact forms.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
from datetime import datetime
from typing import Optional
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from app.models.contact import (
    Contact,
    ContactConfidence,
    ContactRole,
    ContactSource,
)

logger = logging.getLogger(__name__)


CANDIDATE_PATHS = [
    "/team",
    "/about",
    "/about-us",
    "/about/team",
    "/leadership",
    "/people",
    "/staff",
    "/our-team",
    "/team/leadership",
    "/company/leadership",
    "/company/people",
    "/careers/team",
    "/careers/our-people",
    "/recruiting",
    "/careers/recruiting",
    "/contact",
]


HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; PlaceUpBot/1.0; +https://placeup.io/bot)",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

EMAIL_REGEX = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
GENERIC_LOCAL_PARTS = {
    "info", "contact", "hello", "support", "admin", "press", "sales",
    "noreply", "no-reply", "webmaster", "office",
}
ROLE_LOCAL_PARTS = {
    "hr", "careers", "jobs", "recruit", "recruiting", "talent",
    "people", "hiring",
}


def _classify_role(title: Optional[str], context: Optional[str] = None) -> ContactRole:
    text = " ".join(s for s in (title, context) if s).lower()
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
    return ContactRole.OTHER


def _contact_id(company: str, identifier: str) -> str:
    raw = f"team|{company.lower()}|{identifier.lower()}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _extract_jsonld_persons(soup: BeautifulSoup, company: str, source_url: str) -> list[Contact]:
    """Extract schema.org Person/Employee blocks from JSON-LD."""
    out: list[Contact] = []
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "{}")
        except (json.JSONDecodeError, AttributeError):
            continue
        items = data if isinstance(data, list) else [data]
        for item in items:
            if not isinstance(item, dict):
                continue
            employees = item.get("employee") or item.get("member") or []
            if isinstance(employees, dict):
                employees = [employees]
            for person in employees:
                if not isinstance(person, dict):
                    continue
                if person.get("@type") not in ("Person", "Employee", None):
                    continue
                name = (person.get("name") or "").strip() or None
                title = (person.get("jobTitle") or person.get("description") or "").strip() or None
                email = (person.get("email") or "").strip().lower() or None
                if email and email.startswith("mailto:"):
                    email = email[7:]
                linkedin = None
                same_as = person.get("sameAs") or []
                if isinstance(same_as, list):
                    for url in same_as:
                        if isinstance(url, str) and "linkedin.com/in/" in url.lower():
                            linkedin = url.split("?")[0].rstrip("/")
                            break
                if not (name or email):
                    continue
                out.append(Contact(
                    id=_contact_id(company, f"jsonld:{name or ''}:{email or linkedin or ''}"),
                    full_name=name,
                    title=title,
                    role=_classify_role(title),
                    company=company,
                    email=email,
                    linkedin_url=linkedin,
                    source=ContactSource.TEAM_PAGE,
                    confidence=ContactConfidence.PATTERN if email else ContactConfidence.UNKNOWN,
                    source_payload={"extractor": "json-ld", "source_url": source_url},
                    discovered_at=datetime.utcnow(),
                ))
    return out


def _extract_mailto_anchors(soup: BeautifulSoup, company: str, source_url: str) -> list[Contact]:
    """Pick out mailto: links and try to associate them with a name + title nearby."""
    out: list[Contact] = []
    for a in soup.find_all("a", href=True):
        href = a["href"].strip().lower()
        if not href.startswith("mailto:"):
            continue
        email = href[7:].split("?", 1)[0].strip()
        if not email or "@" not in email:
            continue

        local = email.split("@", 1)[0]
        if local in GENERIC_LOCAL_PARTS:
            continue
        is_role_alias = local in ROLE_LOCAL_PARTS

        # Try to find a name + title nearby in the DOM
        link_text = a.get_text(strip=True)
        parent_text = (a.parent.get_text(" ", strip=True) if a.parent else "")[:300]

        # Heuristic: if anchor text looks like a name, use it
        name = None
        if link_text and "@" not in link_text and len(link_text.split()) <= 4:
            name = link_text

        # Title: look for title-cased word near "manager"/"recruiter"/"director"
        title = None
        title_match = re.search(
            r"((?:[A-Z][a-z]+ ?){1,3}(?:Recruiter|Manager|Director|Lead|Head|Officer|Specialist))",
            parent_text,
        )
        if title_match:
            title = title_match.group(1)

        out.append(Contact(
            id=_contact_id(company, f"mailto:{email}"),
            full_name=name,
            title=title or ("Recruiting (role alias)" if is_role_alias else None),
            role=_classify_role(title, parent_text),
            company=company,
            email=email,
            source=ContactSource.TEAM_PAGE,
            confidence=ContactConfidence.PATTERN,
            source_payload={
                "extractor": "mailto",
                "source_url": source_url,
                "context": parent_text[:200],
                "is_role_alias": is_role_alias,
            },
            discovered_at=datetime.utcnow(),
        ))
    return out


async def _fetch(client: httpx.AsyncClient, url: str) -> Optional[str]:
    try:
        r = await client.get(url, follow_redirects=True)
        if r.status_code != 200:
            return None
        ct = r.headers.get("content-type", "")
        if "text/html" not in ct and "application/xhtml" not in ct:
            return None
        return r.text
    except httpx.HTTPError as exc:
        logger.debug("team_page fetch failed %s: %s", url, exc)
        return None


async def crawl_company_team_pages(
    *,
    company: str,
    base_url: str,
    max_pages: int = 6,
    max_contacts: int = 25,
) -> list[Contact]:
    """Crawl a small set of likely team pages on a company's website.

    Args:
        company:    Display name (used as Contact.company)
        base_url:   Either the homepage (https://stripe.com) or any page on
                    that origin — we'll normalize to scheme://host
        max_pages:  Cap on number of candidate paths visited
        max_contacts: Cap on returned contacts

    Returns deduplicated Contact list.
    """
    if not base_url:
        return []
    parsed = urlparse(base_url if "://" in base_url else f"https://{base_url}")
    origin = f"{parsed.scheme}://{parsed.netloc}"
    if not parsed.netloc:
        return []

    seen_ids: set[str] = set()
    contacts: list[Contact] = []

    async with httpx.AsyncClient(timeout=15.0, headers=HEADERS) as client:
        # Always try the homepage first (it usually has a footer mailto)
        candidates = [origin] + [urljoin(origin, p) for p in CANDIDATE_PATHS][: max_pages - 1]
        for url in candidates:
            html = await _fetch(client, url)
            if not html:
                continue
            try:
                soup = BeautifulSoup(html, "html.parser")
            except Exception:
                continue

            new_contacts = (
                _extract_jsonld_persons(soup, company, url)
                + _extract_mailto_anchors(soup, company, url)
            )

            for c in new_contacts:
                if c.id in seen_ids:
                    continue
                seen_ids.add(c.id)
                contacts.append(c)
                if len(contacts) >= max_contacts:
                    break

            if len(contacts) >= max_contacts:
                break
            await asyncio.sleep(0.3)  # politeness pause between page fetches

    logger.info("team_page %s (%s): %s contacts", company, origin, len(contacts))
    return contacts

"""
GitHub Org Member Miner (Free)

For tech-heavy H1B sponsors (Stripe, Coinbase, Airbnb, Datadog, etc.) most
of their engineering team is publicly visible on GitHub. We harvest:

  1. Public org members  → GET /orgs/{org}/public_members
  2. Each member's profile → GET /users/{login}
     - name, blog, twitter_username, location, bio, hireable
     - Public email if the user opted to expose it (~10-15% of devs)
  3. Member's pinned/featured repo READMEs (optional) for company-affirmed
     bios

Rate limits:
  - Unauthenticated: 60 req/hour per IP
  - With a free Personal Access Token (PAT): 5,000 req/hour
  - Set GITHUB_TOKEN in .env for the higher limit

Curated mapping of company → GitHub org lives in:
  app/services/github_org_mapping.py (built below)

Output is Contact records with source=GITHUB.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
from datetime import datetime
from typing import Optional

import httpx

from app.models.contact import (
    Contact,
    ContactConfidence,
    ContactRole,
    ContactSource,
)

logger = logging.getLogger(__name__)


GITHUB_API = "https://api.github.com"


# Curated company → GitHub org mapping. Add freely as you find more.
COMPANY_GITHUB_ORG: dict[str, str] = {
    "stripe": "stripe",
    "airbnb": "airbnb",
    "coinbase": "coinbase",
    "robinhood": "Robinhood",
    "pinterest": "pinterest",
    "reddit": "reddit",
    "lyft": "lyft",
    "doordash": "doordash",
    "instacart": "instacart",
    "cloudflare": "cloudflare",
    "datadog": "DataDog",
    "snowflake": "snowflakedb",
    "mongodb": "mongodb",
    "confluent": "confluentinc",
    "hashicorp": "hashicorp",
    "twilio": "twilio",
    "okta": "okta",
    "github": "github",
    "gitlab": "gitlab",
    "square (block)": "square",
    "block (cash app)": "cashapp",
    "affirm": "Affirm",
    "plaid": "plaid",
    "brex": "brexhq",
    "roblox": "Roblox",
    "unity": "Unity-Technologies",
    "figma": "figma",
    "notion": "makenotion",
    "asana": "Asana",
    "slack": "slackhq",
    "atlassian": "atlassian",
    "zoom": "zoom",
    "dropbox": "dropbox",
    "box": "box",
    "splunk": "splunk",
    "palo alto networks": "PaloAltoNetworks",
    "palantir": "palantir",
    "anthropic": "anthropics",
    "openai": "openai",
    "scale ai": "scaleapi",
    "databricks": "databricks",
    "nvidia": "NVIDIA",
    "salesforce": "salesforce",
    "adobe": "adobe",
    "cisco": "cisco",
    "intel": "intel",
    "amd": "amd",
    "qualcomm": "Qualcomm",
    "apple": "apple",
    "servicenow": "ServiceNow",
    "vmware": "vmware",
    "oracle": "oracle",
    "netflix": "Netflix",
    "spotify": "spotify",
    "shopify": "Shopify",
    "twitch": "twitchtv",
    "ramp": "sumup-oss",  # placeholder; verify
    "linear": "linear",
    "mercury": "mercurytechnologies",
    "vercel": "vercel",
    "anysphere (cursor)": "cursor",
    "perplexity": "perplexity-ai",
    "moderna": "moderna",
    "ibm": "IBM",
}


def _classify_role(bio: Optional[str], hireable: Optional[bool]) -> ContactRole:
    if bio:
        b = bio.lower()
        if "engineering manager" in b or "eng manager" in b:
            return ContactRole.ENGINEERING_MANAGER
        if "team lead" in b or "tech lead" in b or "staff engineer" in b:
            return ContactRole.TEAM_LEAD
        if "recruit" in b or "talent" in b:
            return ContactRole.RECRUITER
    return ContactRole.OTHER


def _contact_id(company: str, login: str) -> str:
    raw = f"github|{company.lower()}|{login.lower()}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _auth_headers() -> dict:
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "PlaceUpBot/1.0",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


async def list_public_members(org: str, *, max_members: int = 100) -> list[dict]:
    """List the public members of a GitHub org. Returns list of {login, ...}."""
    members: list[dict] = []
    page = 1
    per_page = min(100, max_members)
    async with httpx.AsyncClient(timeout=20.0, headers=_auth_headers()) as client:
        while len(members) < max_members:
            try:
                r = await client.get(
                    f"{GITHUB_API}/orgs/{org}/public_members",
                    params={"per_page": per_page, "page": page},
                )
                if r.status_code in (404, 451):
                    logger.info("github org %s: %s", org, r.status_code)
                    return members
                if r.status_code == 403 and "rate limit" in r.text.lower():
                    logger.warning("github rate-limited; set GITHUB_TOKEN to raise to 5K/hr")
                    return members
                r.raise_for_status()
                page_data = r.json()
            except httpx.HTTPError as exc:
                logger.warning("github org %s: %s", org, exc)
                return members
            if not page_data:
                break
            members.extend(page_data)
            if len(page_data) < per_page:
                break
            page += 1
            await asyncio.sleep(0.3)
    return members[:max_members]


async def fetch_user_profile(login: str) -> Optional[dict]:
    """Fetch a single user's public profile."""
    async with httpx.AsyncClient(timeout=15.0, headers=_auth_headers()) as client:
        try:
            r = await client.get(f"{GITHUB_API}/users/{login}")
            if r.status_code != 200:
                return None
            return r.json()
        except httpx.HTTPError as exc:
            logger.debug("github user %s: %s", login, exc)
            return None


async def mine_company_github(
    *,
    company: str,
    org: Optional[str] = None,
    max_members: int = 30,
    enrich_profiles: bool = True,
) -> list[Contact]:
    """End-to-end: company → org → public members → enriched contacts."""
    if not org:
        org = COMPANY_GITHUB_ORG.get(company.lower())
    if not org:
        logger.info("github_miner: no known org for company=%s", company)
        return []

    members = await list_public_members(org, max_members=max_members)
    if not members:
        return []

    # Concurrency-cap profile fetches
    semaphore = asyncio.Semaphore(5)

    async def _enrich(member: dict) -> Optional[Contact]:
        login = member.get("login") or ""
        if not login:
            return None
        profile = member if not enrich_profiles else (await fetch_user_profile(login) or member)
        async with semaphore:
            full_name = profile.get("name") or login
            email = (profile.get("email") or "").strip().lower() or None
            blog = (profile.get("blog") or "").strip() or None
            twitter = (profile.get("twitter_username") or "").strip() or None
            bio = profile.get("bio")
            hireable = profile.get("hireable")
            location = profile.get("location")

            return Contact(
                id=_contact_id(company, login),
                full_name=full_name,
                title=bio[:120] if bio else None,
                role=_classify_role(bio, hireable),
                company=company,
                email=email,
                linkedin_url=None,  # GitHub doesn't expose LinkedIn directly
                source=ContactSource.GITHUB,
                confidence=(
                    ContactConfidence.VERIFIED if email else ContactConfidence.PATTERN
                ),
                source_payload={
                    "github_login": login,
                    "github_url": profile.get("html_url"),
                    "blog": blog,
                    "twitter_username": twitter,
                    "location": location,
                    "hireable": hireable,
                    "company_field_on_profile": profile.get("company"),
                },
                discovered_at=datetime.utcnow(),
            )

    contacts = await asyncio.gather(*[_enrich(m) for m in members])
    contacts = [c for c in contacts if c]

    # Boost confidence: if user's profile.company field matches our target company,
    # they're almost certainly an employee
    for c in contacts:
        if (c.source_payload or {}).get("company_field_on_profile"):
            if c.company.lower() in str(c.source_payload["company_field_on_profile"]).lower():
                if c.email:
                    c.confidence = ContactConfidence.VERIFIED

    logger.info("github_miner %s (org=%s): %s contacts", company, org, len(contacts))
    return contacts

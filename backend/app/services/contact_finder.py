"""Unified Contact Finder Orchestrator (Free-First, Multi-Tenant Sustainable)."""
from __future__ import annotations
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional
from urllib.parse import urlparse

from app.config import settings
from app.models.contact import (
    Contact, ContactConfidence, ContactRole, ContactSource, EnrichmentResult,
)
from app.models.job import JobPost
from app.services.apollo_enrichment import search_people as apollo_search
from app.services.ats_contact_extractor import extract_from_jobpost
from app.services.dol_lca_importer import get_contacts_for_company as dol_get
from app.services.github_miner import COMPANY_GITHUB_ORG, mine_company_github
from app.services.google_xray import xray_search, linkedin_search_url
from app.services.hunter_enrichment import domain_search as hunter_domain_search
from app.services.team_page_crawler import crawl_company_team_pages

logger = logging.getLogger(__name__)

# Global cache TTL — 90 days, shared across all PlaceUp users
CACHE_TTL = timedelta(days=90)

CONFIDENCE_RANK = {
    ContactConfidence.VERIFIED: 4,
    ContactConfidence.PATTERN: 3,
    ContactConfidence.GUESSED: 2,
    ContactConfidence.UNKNOWN: 1,
}

SOURCE_RANK = {
    ContactSource.APOLLO: 9,
    ContactSource.HUNTER: 8,
    ContactSource.FINALSCOUT: 8,
    ContactSource.DOL_LCA: 7,
    ContactSource.CROWDSOURCED: 6,
    ContactSource.GITHUB: 5,
    ContactSource.TEAM_PAGE: 4,
    ContactSource.ATS_METADATA: 3,
    ContactSource.GOOGLE_XRAY: 2,
    ContactSource.LINKEDIN_SEARCH_URL: 1,
    ContactSource.MANUAL: 0,
}


def _dedupe_and_rank(contacts, max_contacts):
    by_key = {}
    for c in contacts:
        key = (
            (c.email and f"e:{c.email.lower()}") or
            (c.linkedin_url and f"l:{c.linkedin_url.lower()}") or
            (c.full_name and f"n:{c.company.lower()}|{c.full_name.lower()}") or
            f"x:{c.id}"
        )
        existing = by_key.get(key)
        if not existing:
            by_key[key] = c
            continue
        rank_new = (CONFIDENCE_RANK[c.confidence], SOURCE_RANK.get(c.source, 0))
        rank_old = (CONFIDENCE_RANK[existing.confidence], SOURCE_RANK.get(existing.source, 0))
        if rank_new > rank_old:
            merged = c.model_copy(update={
                "email": c.email or existing.email,
                "linkedin_url": c.linkedin_url or existing.linkedin_url,
                "linkedin_search_url": c.linkedin_search_url or existing.linkedin_search_url,
                "full_name": c.full_name or existing.full_name,
                "title": c.title or existing.title,
            })
            by_key[key] = merged
        else:
            existing.email = existing.email or c.email
            existing.linkedin_url = existing.linkedin_url or c.linkedin_url
            existing.linkedin_search_url = existing.linkedin_search_url or c.linkedin_search_url
            existing.full_name = existing.full_name or c.full_name
            existing.title = existing.title or c.title

    deduped = list(by_key.values())
    deduped.sort(key=lambda c: (
        CONFIDENCE_RANK[c.confidence], SOURCE_RANK.get(c.source, 0),
        1 if c.email else 0, 1 if c.linkedin_url else 0,
    ), reverse=True)
    return deduped[:max_contacts]


def _fresh_cache_hit(cached):
    if not cached:
        return False
    cutoff = datetime.utcnow() - CACHE_TTL
    for row in cached[:1]:
        ts_raw = row.get("discovered_at")
        if not ts_raw:
            continue
        try:
            ts = datetime.fromisoformat(str(ts_raw).replace("Z", "+00:00").rstrip("+00:00"))
            if ts >= cutoff:
                return True
        except ValueError:
            continue
    return False


def _row_to_contact(row):
    try:
        return Contact(
            id=row.get("id"),
            full_name=row.get("full_name"), first_name=row.get("first_name"),
            last_name=row.get("last_name"), title=row.get("title"),
            role=row.get("role") or "other", company=row.get("company") or "",
            company_domain=row.get("company_domain"),
            email=row.get("email"), linkedin_url=row.get("linkedin_url"),
            linkedin_search_url=row.get("linkedin_search_url"),
            source=row.get("source") or "manual",
            confidence=row.get("confidence") or "unknown",
            source_payload=row.get("source_payload") or {},
            related_job_id=row.get("related_job_id"),
            discovered_at=(datetime.fromisoformat(str(row["discovered_at"])) if row.get("discovered_at") else datetime.utcnow()),
            last_verified_at=(datetime.fromisoformat(str(row["last_verified_at"])) if row.get("last_verified_at") else None),
        )
    except Exception:
        return None


def _resolve_domain(domain, job, company=None):
    """Domain resolution priority:
       1. Explicit `domain` argument
       2. Curated sponsor_domains.best_domain(company)
       3. URL parsed from job.company_url
       4. None — caller should skip Hunter
    """
    if domain:
        return domain.lower().strip()
    if company:
        try:
            from app.services.sponsor_domains import best_domain, is_safe_domain
            d = best_domain(company)
            if d and is_safe_domain(d):
                return d
        except Exception:
            pass
    if job and job.company_url:
        try:
            return urlparse(job.company_url).netloc.lower().lstrip("www.") or None
        except Exception:
            return None
    return None


async def find_contacts(*, company, role_query=None, domain=None, job=None, db=None,
                        use_ats_metadata=True, use_dol_lca=True, use_team_page=True,
                        use_github=True, use_crowdsourced=True,
                        use_apollo=False, use_hunter=False, use_google_xray=False,
                        byok_apollo_key=None, byok_hunter_key=None, byok_serpapi_key=None,
                        byok_finalscout_key=None,
                        max_contacts=10, force_refresh=False):
    started = datetime.utcnow()
    notes = []
    sources_used = []
    credits = {}
    eff_domain = _resolve_domain(domain, job, company=company)

    # 0. Cache check (global, 90d)
    cache_hit = False
    if db is not None and not force_refresh:
        try:
            cached_rows = await db.get_contacts(company=company, limit=max_contacts * 5)
        except Exception:
            cached_rows = []
        if _fresh_cache_hit(cached_rows):
            cached = [c for c in (_row_to_contact(r) for r in cached_rows) if c]
            cache_hit = True
            ranked = _dedupe_and_rank(cached, max_contacts)
            return EnrichmentResult(
                company=company, role_query=role_query, contacts=ranked,
                sources_used=sorted({c.source for c in ranked},
                                    key=lambda s: SOURCE_RANK.get(s, 0), reverse=True),
                cache_hit=True, api_credits_used={},
                duration_seconds=(datetime.utcnow() - started).total_seconds(),
                notes=["Global cache hit (90-day TTL) - $0 cost."],
            )

    # 1. FREE harvesters (parallel)
    free_tasks = []
    free_labels = []
    if use_ats_metadata and job is not None:
        async def _ats(): return extract_from_jobpost(job)
        free_tasks.append(_ats()); free_labels.append("ats_metadata")
    if use_dol_lca and db is not None:
        free_tasks.append(dol_get(employer_name=company, db=db, limit=max_contacts))
        free_labels.append("dol_lca")
    if use_crowdsourced and db is not None:
        async def _crowd():
            rows = await db.get_contacts(company=company, limit=max_contacts * 2)
            return [c for c in (_row_to_contact(r) for r in rows)
                    if c and c.source == ContactSource.CROWDSOURCED]
        free_tasks.append(_crowd()); free_labels.append("crowdsourced")
    if use_team_page and (eff_domain or (job and job.company_url)):
        base_url = job.company_url if job and job.company_url else f"https://{eff_domain}"
        free_tasks.append(crawl_company_team_pages(
            company=company, base_url=base_url, max_contacts=max_contacts))
        free_labels.append("team_page")
    if use_github and company.lower() in COMPANY_GITHUB_ORG:
        free_tasks.append(mine_company_github(
            company=company, max_members=min(max_contacts * 2, 30)))
        free_labels.append("github")

    free_contacts = []
    if free_tasks:
        results = await asyncio.gather(*free_tasks, return_exceptions=True)
        for label, res in zip(free_labels, results):
            if isinstance(res, Exception):
                notes.append(f"{label} failed: {res}")
                continue
            if isinstance(res, list) and res:
                free_contacts.extend(res)
                if res[0].source not in sources_used:
                    sources_used.append(res[0].source)

    # 2. PAID APIs (only if explicitly opted in + key present)
    apollo_key = (byok_apollo_key or settings.apollo_api_key or "").strip()
    hunter_key = (byok_hunter_key or settings.hunter_api_key or "").strip()
    serpapi_key = (byok_serpapi_key or settings.serpapi_key or "").strip()

    paid_tasks = []
    paid_labels = []
    if use_hunter and hunter_key and eff_domain:
        async def _hunter():
            orig = settings.hunter_api_key
            settings.hunter_api_key = hunter_key
            try:
                return await hunter_domain_search(domain=eff_domain, company=company,
                                                   limit=max_contacts,
                                                   related_job_id=(job.id if job else None))
            finally:
                settings.hunter_api_key = orig
        paid_tasks.append(_hunter()); paid_labels.append("hunter")

    if use_apollo and apollo_key:
        async def _apollo():
            orig = settings.apollo_api_key
            settings.apollo_api_key = apollo_key
            try:
                return await apollo_search(company=company, role_query=role_query,
                                            domain=eff_domain, per_page=max_contacts,
                                            related_job_id=(job.id if job else None))
            finally:
                settings.apollo_api_key = orig
        paid_tasks.append(_apollo()); paid_labels.append("apollo")

    if use_google_xray and (serpapi_key or (settings.google_api_key and settings.google_cse_id)):
        async def _xray():
            orig = settings.serpapi_key
            settings.serpapi_key = serpapi_key
            try:
                return await xray_search(company=company, role_query=role_query,
                                         max_results=max_contacts, domain=eff_domain,
                                         related_job_id=(job.id if job else None))
            finally:
                settings.serpapi_key = orig
        paid_tasks.append(_xray()); paid_labels.append("google_xray")

    paid_contacts = []
    if paid_tasks:
        results = await asyncio.gather(*paid_tasks, return_exceptions=True)
        for label, res in zip(paid_labels, results):
            if isinstance(res, Exception):
                notes.append(f"{label} failed: {res}")
                continue
            if isinstance(res, list) and res:
                paid_contacts.extend(res)
                if res[0].source not in sources_used:
                    sources_used.append(res[0].source)
                credits[label] = credits.get(label, 0) + len(res)

    # Always emit MULTIPLE LinkedIn search URLs (one per role type) so users
    # have a clickable shortcut to every kind of contact at this company.
    role_types = [
        ("recruiter", "Recruiter"),
        ("hiring manager", "Hiring Manager"),
        ("talent acquisition", "Talent Acquisition"),
        ("engineering manager", "Engineering Manager"),
        ("technical recruiter", "Technical Recruiter"),
    ]
    fallback_list = []
    for role_keyword, role_label in role_types:
        fallback_list.append(Contact(
            id=f"li:{company.lower()[:16]}:{role_keyword.replace(' ', '_')[:14]}"[:32],
            full_name=None,
            title=f"LinkedIn search: {role_label} @ {company}",
            role=ContactRole.RECRUITER if "recruit" in role_keyword else ContactRole.OTHER,
            company=company,
            linkedin_search_url=linkedin_search_url(company, role_keyword),
            source=ContactSource.LINKEDIN_SEARCH_URL,
            confidence=ContactConfidence.UNKNOWN,
            source_payload={
                "note": "Click to search LinkedIn as yourself; no scraping performed.",
                "role_template": role_keyword,
            },
            related_job_id=(job.id if job else None),
        ))

    ranked = _dedupe_and_rank(free_contacts + paid_contacts + fallback_list, max_contacts)

    if db is not None and ranked:
        try:
            await db.upsert_contacts([c.model_dump(mode="json") for c in ranked])
        except Exception as exc:
            logger.warning("Cache write skipped: %s", exc)

    if not credits:
        notes.append("Free-only enrichment: $0 cost to PlaceUp. Cached for 90 days.")
    if use_apollo and not apollo_key:
        notes.append("Apollo requested but no key (BYOK or platform).")
    if use_hunter and not hunter_key:
        notes.append("Hunter requested but no key (BYOK or platform).")

    return EnrichmentResult(
        company=company, role_query=role_query, contacts=ranked,
        sources_used=sources_used, cache_hit=cache_hit, api_credits_used=credits,
        duration_seconds=(datetime.utcnow() - started).total_seconds(),
        notes=notes,
    )


async def bulk_enrich_jobs(jobs, *, db=None, max_per_job=5, concurrency=4, **kwargs):
    if not jobs:
        return {}
    semaphore = asyncio.Semaphore(concurrency)

    async def _one(job):
        async with semaphore:
            try:
                result = await find_contacts(
                    company=job.company, role_query=job.title, job=job, db=db,
                    max_contacts=max_per_job, **kwargs)
                return job.id, result
            except Exception as exc:
                return job.id, EnrichmentResult(company=job.company, role_query=job.title,
                                                notes=[str(exc)])

    results = await asyncio.gather(*[_one(j) for j in jobs])
    return dict(results)

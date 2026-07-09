"""Apify `fantastic-jobs/career-site-job-listing-feed` connector.

Pulls postings DIRECTLY from company career sites + their ATS APIs (Workday,
Greenhouse, iCIMS, Lever, Ashby, ...) — not from LinkedIn/Indeed aggregators —
so apply links are canonical, descriptions are full text, and duplicates are
rare. Implements Bala's documented collection algorithm:

  * titleSearch (curated role titles), locationSearch, removeAgency=true,
    descriptionType="text", limit.
  * derive the ATS "portal" from the URL host,
  * HARD-EXCLUDE US clearance / citizenship-only roles (they can't sponsor).

Requires APIFY_TOKEN in the environment. If it's missing, the connector is a
no-op so the rest of the scrape pipeline is unaffected.
"""
from __future__ import annotations

import logging
import os
from urllib.parse import urlparse

import httpx

from app.etl.api_sources.schema import NormalizedJob, clean_text, iso_or_none, stable_job_id
from app.services.job_filters import requires_us_clearance

logger = logging.getLogger(__name__)

_ACTOR = "fantastic-jobs~career-site-job-listing-feed"
_APIFY_TOKEN = (os.getenv("APIFY_TOKEN") or os.getenv("APIFY_API_TOKEN") or "").strip()

# ATS portal detection — first matching host signature wins.
_ATS_SIGNATURES: tuple[tuple[str, str], ...] = (
    ("myworkdayjobs.com", "Workday"),
    ("icims.com", "iCIMS"),
    ("workforcenow.adp.com", "ADP"), ("myjobs.adp.com", "ADP"),
    ("greenhouse.io", "Greenhouse"),
    ("oraclecloud.com", "Oracle Cloud HCM"),
    ("taleo.net", "Oracle Taleo"),
    ("paylocity.com", "Paylocity"),
    ("ultipro.com", "UKG / UltiPro"),
    ("ukg.com", "UKG"),
    ("applytojob.com", "JazzHR"),
    ("lever.co", "Lever"),
    ("smartrecruiters.com", "SmartRecruiters"),
    ("bamboohr.com", "BambooHR"),
    ("paycomonline.net", "Paycom"),
    ("workable.com", "Workable"),
    ("ashbyhq.com", "Ashby"),
    ("rippling.com", "Rippling"),
    ("trinethire.com", "TriNet Hire"),
    ("dayforcehcm.com", "Dayforce"),
    ("dayforce.com", "Dayforce"),
    ("zohorecruit.com", "Zoho Recruit"),
    ("jobvite.com", "Jobvite"),
    ("breezy.hr", "BreezyHR"),
    ("recruitingbypaycor.com", "Paycor"),
    ("careerplug.com", "CareerPlug"),
    ("careers-page.com", "Recruitee"), ("careerspage.io", "Recruitee"),
    ("successfactors.com", "SAP SuccessFactors"), ("sapsf.com", "SAP SuccessFactors"),
    ("pinpointhq.com", "Pinpoint"),
    ("polymer.co", "Polymer"),
    ("phenompeople.com", "Phenom"), ("phenom.com", "Phenom"),
    ("app.dover.com", "Dover"),
    ("jobs.gem.com", "Gem"),
    ("join.com", "JOIN"),
    ("hireology.com", "Hireology"),
    ("hibob.com", "HiBob"),
)


def detect_portal(url: str) -> str:
    host = urlparse(url or "").netloc.lower()
    for sig, name in _ATS_SIGNATURES:
        if sig in host:
            return name
    return "Company career site"


def _country_of(item: dict) -> str:
    locs = item.get("locations_derived") or item.get("locations") or []
    text = " ".join(str(x) for x in locs) if isinstance(locs, list) else str(locs)
    low = (text + " " + str(item.get("location") or "")).lower()
    if any(x in low for x in ("united states", "usa", ", us", "u.s.")):
        return "US"
    if "canada" in low:
        return "CA"
    if "united kingdom" in low or "england" in low:
        return "GB"
    if "germany" in low:
        return "DE"
    if "remote" in low:
        return "US"
    return "US"


def _normalize(item: dict) -> NormalizedJob | None:
    title = clean_text(item.get("title"))
    url = clean_text(item.get("url") or item.get("apply_url"))
    company = clean_text(item.get("organization") or item.get("company"))
    if not title or not url:
        return None
    description = clean_text(item.get("description_text") or item.get("description") or "")
    key_skills = item.get("ai_key_skills") or []
    keywords = item.get("ai_keywords") or []
    combined = f"{title} {description} {' '.join(map(str, key_skills))} {' '.join(map(str, keywords))}"
    # Hard-exclude clearance / citizenship-only roles (cannot sponsor a visa).
    if requires_us_clearance(combined):
        return None
    portal = detect_portal(url)
    source_id = clean_text(item.get("id") or item.get("source_job_id") or url)
    tags = [clean_text(t) for t in (list(key_skills) + list(keywords)) if clean_text(t)][:25]
    return NormalizedJob(
        job_id=stable_job_id("career_site_feed", source_id),
        source="career_site_feed",
        source_job_id=source_id,
        title=title,
        company=company or "Unknown",
        location=clean_text(" ".join(str(x) for x in (item.get("locations_derived") or [])) or item.get("location") or "United States"),
        country=_country_of(item),
        remote="remote" in combined.lower(),
        url=url,
        description=description,
        posted_date=iso_or_none(item.get("date_posted")),
        raw_tags=tags + [portal],
        raw=item,
    )


async def fetch(titles: list[str], *, location: str = "United States", limit: int = 400) -> list[NormalizedJob]:
    if not _APIFY_TOKEN:
        logger.info("career_site_feed skipped: APIFY_TOKEN not set")
        return []
    title_list = [t for t in (titles or []) if t][:50] or ["Software Engineer"]
    payload = {
        "titleSearch": title_list,
        "locationSearch": location,
        "removeAgency": True,
        "descriptionType": "text",
        "limit": int(limit),
    }
    url = f"https://api.apify.com/v2/acts/{_ACTOR}/run-sync-get-dataset-items?token={_APIFY_TOKEN}"
    try:
        async with httpx.AsyncClient(timeout=180.0) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            items = resp.json()
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("career_site_feed Apify call failed: %s", exc)
        return []
    if not isinstance(items, list):
        return []
    out: list[NormalizedJob] = []
    for item in items:
        if isinstance(item, dict):
            job = _normalize(item)
            if job:
                out.append(job)
    logger.info("career_site_feed normalized %s/%s items", len(out), len(items))
    return out

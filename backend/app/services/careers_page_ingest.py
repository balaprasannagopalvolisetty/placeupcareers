"""Ingest ALL open positions from a company careers page / ATS board URL.

Give it any of:
    https://jobs.smartrecruiters.com/MicroStrategy1/744000131592379-...
    https://boards.greenhouse.io/duolingo
    https://jobs.lever.co/netflix
    https://www.strategy.com/careers          (generic page -> ATS auto-discovery)

It detects the ATS platform + board token (directly from the URL, or by
fetching the page and finding embedded ATS links), scrapes every open posting
via the structured ATS APIs, and upserts them into the jobs pipeline.

Exposed via POST /api/jobs/ingest/careers-page (internal API key required).
"""

from __future__ import annotations

import logging
import re
from typing import Optional
from urllib.parse import urlparse

import httpx

from app.services.careers_ats import scrape_ats
from app.services.company_career_resolver import _is_probeable_public_domain
from app.services.sponsor_domains import best_domain

logger = logging.getLogger(__name__)

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
}

# (ats_name, regex with one capture group = board token)
_ATS_URL_PATTERNS: tuple[tuple[str, re.Pattern], ...] = (
    ("smartrecruiters", re.compile(r"(?:jobs|careers)\.smartrecruiters\.com/([A-Za-z0-9_-]+)", re.I)),
    ("greenhouse", re.compile(r"boards(?:-api)?\.greenhouse\.io/(?:v1/boards/)?([A-Za-z0-9_-]+)", re.I)),
    ("greenhouse", re.compile(r"job-boards\.greenhouse\.io/([A-Za-z0-9_-]+)", re.I)),
    ("lever", re.compile(r"jobs\.lever\.co/([A-Za-z0-9_-]+)", re.I)),
    ("ashby", re.compile(r"jobs\.ashbyhq\.com/([A-Za-z0-9_-]+)", re.I)),
    ("workable", re.compile(r"apply\.workable\.com/([A-Za-z0-9_-]+)", re.I)),
    ("recruitee", re.compile(r"([A-Za-z0-9-]+)\.recruitee\.com", re.I)),
    ("teamtailor", re.compile(r"([A-Za-z0-9-]+)\.teamtailor\.com", re.I)),
    ("bamboohr", re.compile(r"([A-Za-z0-9-]+)\.bamboohr\.com", re.I)),
)

# Workday: tenant + site live in the URL ({tenant}.wd5.myworkdayjobs.com/{site}).
_WORKDAY_URL_RE = re.compile(
    r"([a-z0-9-]+)\.(wd\d+)\.(myworkdayjobs|myworkdaysite)\.com/"
    r"(?:[a-z]{2}[-_][A-Za-z]{2}/)?(?:recruiting/[A-Za-z0-9_-]+/)?([A-Za-z0-9_-]+)",
    re.I,
)
# Eightfold AI portals (HP, American Express, ...): apply.{company}.com/careers
# with a public JSON API at /api/apply/v2/jobs.
_EIGHTFOLD_URL_RE = re.compile(r"https?://(apply\.[a-z0-9.-]+)/careers", re.I)


def detect_ats_from_url(url: str) -> Optional[tuple[str, str]]:
    """Recognize an ATS board/posting URL and extract (platform, token)."""
    for ats_name, pattern in _ATS_URL_PATTERNS:
        match = pattern.search(url or "")
        if match:
            token = match.group(1).strip()
            if token and token.lower() not in {"www", "jobs", "careers", "api"}:
                return ats_name, token
    return None


async def discover_ats_from_page(url: str) -> Optional[tuple[str, str]]:
    """Fetch a generic careers page and look for embedded ATS links."""
    host = (urlparse(url or "").hostname or "").strip().lower()
    if not _is_probeable_public_domain(host):
        return None
    try:
        async with httpx.AsyncClient(headers=_HEADERS, timeout=20.0, follow_redirects=True) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            html = resp.text[:2_000_000]
    except Exception as exc:  # noqa: BLE001
        logger.warning("Careers page fetch failed for %s: %s", url, exc)
        return None
    return detect_ats_from_url(html)


async def scrape_eightfold(apply_host: str, *, max_jobs: int = 1000) -> list:
    """Scrape an Eightfold AI careers portal (e.g. apply.hp.com) via its
    public JSON API. Returns JobPost objects like the careers_ats scrapers."""
    from datetime import datetime

    from app.models.job import JobCategory, JobPost, JobSource
    from app.utils.deduplication import generate_content_hash, generate_job_id

    company_guess = apply_host.replace("apply.", "").split(".")[0].upper()
    postings: list = []
    start = 0
    async with httpx.AsyncClient(headers={**_HEADERS, "Accept": "application/json"}, timeout=25.0, follow_redirects=True) as client:
        while start < max_jobs:
            try:
                resp = await client.get(
                    f"https://{apply_host}/api/apply/v2/jobs",
                    params={"start": start, "num": 100, "sort_by": "timestamp"},
                )
                resp.raise_for_status()
                payload = resp.json()
            except Exception as exc:  # noqa: BLE001
                logger.debug("Eightfold fetch failed for %s: %s", apply_host, exc)
                break
            positions = payload.get("positions") or []
            if not positions:
                break
            for item in positions:
                title = str(item.get("name") or "").strip()
                if not title:
                    continue
                pid = str(item.get("id") or item.get("display_job_id") or "")
                location = str(item.get("location") or (item.get("locations") or [""])[0] or "")
                company = str(item.get("business_unit") or company_guess or "").strip() or company_guess
                job_url = f"https://{apply_host}/careers?pid={pid}" if pid else f"https://{apply_host}/careers"
                description = str(item.get("job_description") or "").strip()
                job_id = generate_job_id(title, company, location)
                postings.append(JobPost(
                    id=job_id,
                    title=title,
                    company=company,
                    location=location,
                    description=description,
                    job_url=job_url,
                    category=JobCategory.OTHER,
                    source=JobSource.SCRAPLING_DISCOVERY,
                    source_job_id=pid,
                    posted_at=None,
                    scraped_at=datetime.utcnow(),
                    content_hash=generate_content_hash(title, company, location),
                    extra_metadata={"ats": "eightfold", "apply_host": apply_host},
                ))
            start += 100
            if len(positions) < 100:
                break
    return postings[:max_jobs]


# Search throttling: every harvested company triggers a lookup, so without a
# cache + pacing the search engine would rate-limit us within one sweep batch.
_search_cache: "dict[str, tuple[float, Optional[str]]]" = {}
_SEARCH_CACHE_TTL = 24 * 3600
_search_semaphore = __import__("asyncio").Semaphore(2)
_SEARCH_SPACING_SECONDS = 1.2
_last_search_at = 0.0

_DOMAIN_CAREERS_PATHS = (
    "/careers",
    "/careers/",
    "/jobs",
    "/jobs/",
    "/en/careers",
    "/en_us/careers",
    "/company/careers",
    "/join-us",
    "/work-with-us",
)


def _domain_career_candidates(company: str) -> list[str]:
    domain = best_domain(company)
    if not domain or not _is_probeable_public_domain(domain):
        return []
    return [f"https://{domain}{path}" for path in _DOMAIN_CAREERS_PATHS]


async def search_careers_page(company: str) -> Optional[str]:
    """Find a company's official careers page by web search (no API key:
    DuckDuckGo HTML endpoint). Cached 24h per company; max 2 concurrent
    lookups spaced >=1.2s apart so bulk sweeps don't get rate-limited."""
    import asyncio as _asyncio
    import time as _time
    global _last_search_at

    company = (company or "").strip()
    if len(company) < 2:
        return None
    cache_key = company.lower()
    cached = _search_cache.get(cache_key)
    if cached and _time.monotonic() - cached[0] < _SEARCH_CACHE_TTL:
        return cached[1]

    async with _search_semaphore:
        wait = _SEARCH_SPACING_SECONDS - (_time.monotonic() - _last_search_at)
        if wait > 0:
            await _asyncio.sleep(wait)
        _last_search_at = _time.monotonic()
        try:
            async with httpx.AsyncClient(headers=_HEADERS, timeout=15.0, follow_redirects=True) as client:
                resp = await client.post(
                    "https://html.duckduckgo.com/html/",
                    data={"q": f"{company} careers jobs official site"},
                )
                resp.raise_for_status()
                html = resp.text
        except Exception as exc:  # noqa: BLE001
            logger.debug("Careers search failed for %r: %s", company, exc)
            if len(_search_cache) > 5000:
                _search_cache.clear()
            _search_cache[cache_key] = (_time.monotonic(), None)
            return None

    from urllib.parse import parse_qs, unquote, urlparse as _urlparse

    urls: list[str] = []
    for href in re.findall(r'href="([^"]+)"', html):
        if "duckduckgo.com/l/" in href:  # redirect wrapper
            qs = parse_qs(_urlparse(href).query)
            target = unquote((qs.get("uddg") or [""])[0])
            if target.startswith("http"):
                urls.append(target)
        elif href.startswith("http") and "duckduckgo" not in href:
            urls.append(href)

    token = re.sub(r"[^a-z0-9]", "", company.lower())[:12]
    blocked = ("linkedin.", "indeed.", "glassdoor.", "wikipedia.", "facebook.", "youtube.",
               "instagram.", "x.com", "twitter.", "reddit.", "crunchbase.", "ambitionbox.",
               "ziprecruiter.", "monster.", "simplyhired.", "jooble.")
    best: Optional[str] = None
    best_score = 0
    for url in urls[:25]:
        host = (_urlparse(url).hostname or "").lower()
        if not host or any(b in host for b in blocked):
            continue
        path = (_urlparse(url).path or "").lower()
        score = 0
        if detect_ats_from_url(url) or _WORKDAY_URL_RE.search(url) or _EIGHTFOLD_URL_RE.search(url):
            score += 6
        if token and token in host.replace("-", "").replace(".", ""):
            score += 3
        if any(k in host for k in ("careers.", "jobs.", "apply.")):
            score += 2
        if any(k in path for k in ("career", "jobs", "join", "opportunit")):
            score += 2
        if score > best_score:
            best, best_score = url, score
    result = best if best_score >= 3 else None
    if len(_search_cache) > 5000:
        _search_cache.clear()
    _search_cache[cache_key] = (_time.monotonic(), result)
    return result


async def collect_postings_from_url(url: str) -> tuple[Optional[dict], list]:
    """Resolve a careers/ATS URL to its platform and return all postings."""
    wd = _WORKDAY_URL_RE.search(url or "")
    if wd:
        tenant, wd_host, wd_domain, site = wd.group(1), wd.group(2), wd.group(3), wd.group(4)
        postings = await scrape_ats("workday", (tenant, site), base_host=f"{wd_host}.{wd_domain}.com")
        return ({"ats": "workday", "token": f"{tenant}/{site}"}, postings)
    ef = _EIGHTFOLD_URL_RE.search(url or "")
    if ef:
        postings = await scrape_eightfold(ef.group(1).lower())
        return ({"ats": "eightfold", "token": ef.group(1).lower()}, postings)

    detected = detect_ats_from_url(url)
    discovery = "url"
    if not detected:
        detected = await discover_ats_from_page(url)
        discovery = "page_scan"
        if not detected:
            # The page itself may embed Workday/Eightfold links.
            host = (urlparse(url or "").hostname or "").strip().lower()
            if _is_probeable_public_domain(host):
                try:
                    async with httpx.AsyncClient(headers=_HEADERS, timeout=20.0, follow_redirects=True) as client:
                        resp = await client.get(url)
                        html = resp.text[:2_000_000]
                    wd = _WORKDAY_URL_RE.search(html)
                    if wd:
                        postings = await scrape_ats("workday", (wd.group(1), wd.group(4)), base_host=f"{wd.group(2)}.{wd.group(3)}.com")
                        return ({"ats": "workday", "token": f"{wd.group(1)}/{wd.group(4)}", "discovered_via": "page_scan"}, postings)
                    ef = _EIGHTFOLD_URL_RE.search(html)
                    if ef:
                        postings = await scrape_eightfold(ef.group(1).lower())
                        return ({"ats": "eightfold", "token": ef.group(1).lower(), "discovered_via": "page_scan"}, postings)
                except Exception:  # noqa: BLE001
                    pass
            return (None, [])
    ats_name, token = detected
    postings = await scrape_ats(ats_name, token, max_jobs=2000)
    return ({"ats": ats_name, "token": token, "discovered_via": discovery}, postings)


async def collect_postings_for_company(company: str) -> tuple[Optional[dict], list]:
    """Company name -> web-search its careers page -> harvest whatever
    platform it runs. The fallback path for employers (like HP) whose portals
    aren't guessable from the company-name slug."""
    urls: list[str] = []
    for candidate in _domain_career_candidates(company):
        if candidate not in urls:
            urls.append(candidate)
    searched = await search_careers_page(company)
    if searched and searched not in urls:
        urls.append(searched)

    last_meta: Optional[dict] = None
    for url in urls:
        meta, postings = await collect_postings_from_url(url)
        if meta is not None:
            meta = {**meta, "careers_url": url, "company": company}
            last_meta = meta
        if postings:
            return (meta, postings)
    return (last_meta, [])


async def ingest_careers_url(url: str, db) -> dict:
    """Scrape every open posting behind a careers/ATS URL into the database."""
    url = (url or "").strip()
    if not url.startswith("http"):
        return {"ok": False, "error": "Provide a full https:// careers or ATS URL."}

    meta, postings = await collect_postings_from_url(url)
    if meta is None:
        return {
            "ok": False,
            "error": "No supported careers platform found at this URL. Supported: "
                     "SmartRecruiters, Greenhouse, Lever, Ashby, Workable, Recruitee, "
                     "Teamtailor, BambooHR, Workday, Eightfold.",
            "url": url,
        }
    ats_name = meta.get("ats")
    token = meta.get("token")
    discovery = meta.get("discovered_via", "url")
    if not postings:
        return {"ok": False, "error": f"Careers platform {ats_name}/{token} returned no open postings.", "ats": ats_name, "token": token}

    payloads = []
    for posting in postings:
        try:
            payloads.append(posting.model_dump(mode="python"))
        except Exception:  # noqa: BLE001
            continue

    inserted = await db.upsert_jobs_batch(payloads)

    # Sync into master_jobs so the new roles are immediately user-visible.
    rebuilt = 0
    try:
        from app.etl.master_jobs import rebuild_master_jobs
        rebuilt = rebuild_master_jobs()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Master rebuild after careers ingest failed: %s", exc)

    logger.info(
        "Careers ingest: %s/%s via %s -> %s postings scraped, %s loaded, master rebuilt %s",
        ats_name, token, discovery, len(postings), inserted, rebuilt,
    )
    return {
        "ok": True,
        "ats": ats_name,
        "board_token": token,
        "discovered_via": discovery,
        "postings_found": len(postings),
        "loaded": inserted,
        "master_rows_synced": rebuilt,
    }

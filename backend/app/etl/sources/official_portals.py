"""
Official government job-portal connectors.

These connectors are deliberately conservative:
- process only HTTP 200 responses through safe_get_json/safe_get_text;
- skip silently when an official API requires credentials that are not present;
- keep one bad source from aborting the scrape cycle.
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
from datetime import datetime
from typing import Any, Optional
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

from app.models.job import JobCategory, JobPost, JobSource
from app.utils.deduplication import generate_content_hash, generate_job_id
from app.etl.sources.source_base import safe_get_json, safe_get_text, is_probably_english

logger = logging.getLogger(__name__)

DETAIL_CONCURRENCY = 6


def _s(v: Any) -> str:
    return "" if v is None else str(v).strip()


def _clean_html(value: Any) -> str:
    if not value:
        return ""
    return BeautifulSoup(str(value), "html.parser").get_text(" ", strip=True)


def _main_text_from_html(html_text: str) -> str:
    soup = BeautifulSoup(html_text or "", "html.parser")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()
    main = (
        soup.find("main")
        or soup.find(attrs={"role": "main"})
        or soup.find("article")
        or soup.body
        or soup
    )
    return " ".join(main.get_text(" ", strip=True).split())


async def _detail_text(client: Optional[httpx.AsyncClient], url: str, *, min_chars: int = 450) -> str:
    if not url:
        return ""
    normalized_url = url.rstrip("/")
    if normalized_url in {
        "https://www.arbeitsagentur.de/jobsuche",
        "https://findajob.dwp.gov.uk/search",
        "https://www.jobbank.gc.ca/jobsearch/jobsearch",
    }:
        return ""
    own_client = client is None
    client = client or httpx.AsyncClient(timeout=12.0, follow_redirects=True)
    try:
        resp = await client.get(url)
        if resp.status_code != 200:
            return ""
        text = resp.text
    except (httpx.TimeoutException, httpx.TransportError):
        return ""
    finally:
        if own_client:
            await client.aclose()
    cleaned = _main_text_from_html(text)
    return cleaned if len(cleaned) >= min_chars else ""


async def _hydrate_detail_texts(
    jobs: list[JobPost],
    *,
    client: Optional[httpx.AsyncClient],
    min_chars: int = 450,
) -> list[JobPost]:
    semaphore = asyncio.Semaphore(DETAIL_CONCURRENCY)

    async def _one(job: JobPost) -> JobPost:
        if len(job.description or "") >= min_chars:
            return job
        async with semaphore:
            detail = await _detail_text(client, job.job_url, min_chars=min_chars)
        if detail and len(detail) > len(job.description or ""):
            job.description = detail
        return job

    return await asyncio.gather(*[_one(job) for job in jobs])


def _parse_iso(value: Any) -> Optional[datetime]:
    if not value or not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _parse_date(value: str) -> Optional[datetime]:
    value = _s(value)
    if not value:
        return None
    for fmt in ("%Y-%m-%d", "%d %B %Y", "%d %b %Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return _parse_iso(value)


def _build_official(
    *,
    title: str,
    company: str,
    location: str,
    description: str,
    job_url: str,
    source: JobSource,
    source_job_id: str,
    posted_at: Optional[datetime],
    country: str,
    is_remote: bool = False,
    extra: Optional[dict] = None,
) -> Optional[JobPost]:
    title = _s(title)
    company = _s(company) or "Official job portal"
    location = _s(location) or country
    if not title:
        return None
    meta = {
        "english_friendly": is_probably_english(f"{title} {description} {location}") or country in {"GB", "CA", "SG", "IE"},
        "visa_country": country,
        "board": source.value,
        "official_portal": True,
    }
    if extra:
        meta.update({k: v for k, v in extra.items() if v not in (None, "", [], {})})
    return JobPost(
        id=generate_job_id(title, company, location, visa_country=country),
        title=title,
        company=company,
        location=location,
        description=_clean_html(description),
        job_url=_s(job_url),
        category=JobCategory.OTHER,
        source=source,
        source_job_id=_s(source_job_id) or _s(job_url) or generate_content_hash(title, company, location),
        posted_at=posted_at,
        is_remote=is_remote,
        content_hash=generate_content_hash(title, company, location, visa_country=country),
        scraped_at=datetime.utcnow(),
        extra_metadata=meta,
    )


# Sweden - JobTech Dev / Platsbanken

JOBTECH_URL = "https://jobsearch.api.jobtechdev.se/search"


def jobtech_hit_to_jobpost(hit: dict) -> Optional[JobPost]:
    if not isinstance(hit, dict):
        return None
    employer = hit.get("employer") or {}
    addr = hit.get("workplace_address") or {}
    city = _s(addr.get("city") or addr.get("municipality"))
    location = ", ".join(p for p in (city, "Sweden") if p) or "Sweden"
    desc_obj = hit.get("description") or {}
    return _build_official(
        title=hit.get("headline"),
        company=employer.get("name") or employer.get("workplace"),
        location=location,
        description=desc_obj.get("text"),
        job_url=hit.get("webpage_url"),
        source=JobSource.JOBTECH,
        source_job_id=hit.get("id"),
        posted_at=_parse_iso(hit.get("publication_date")),
        country="SE",
        extra={
            "occupation_field": (hit.get("occupation_field") or {}).get("label"),
            "vacancies": hit.get("number_of_vacancies"),
            "deadline": hit.get("application_deadline"),
        },
    )


async def scrape_jobtech(*, client: Optional[httpx.AsyncClient] = None, max_jobs: int = 500, query: str = "") -> list[JobPost]:
    out: list[JobPost] = []
    page_size = min(100, max_jobs)
    offset = 0
    while len(out) < max_jobs:
        params = {"limit": page_size, "offset": offset, "sort": "pubdate-desc"}
        if query:
            params["q"] = query
        data = await safe_get_json(JOBTECH_URL, client=client, params=params)
        hits = (data or {}).get("hits") if isinstance(data, dict) else None
        if not hits:
            break
        for hit in hits:
            jp = jobtech_hit_to_jobpost(hit)
            if jp:
                out.append(jp)
        if len(hits) < page_size:
            break
        offset += page_size
    return out[:max_jobs]


# Germany - Bundesagentur fuer Arbeit Jobsuche

BA_JOBS_URL = "https://rest.arbeitsagentur.de/jobboerse/jobsuche-service/pc/v4/jobs"
BA_DETAILS_URL = "https://rest.arbeitsagentur.de/jobboerse/jobsuche-service/pc/v4/jobdetails/{code}"
BA_HEADERS = {"X-API-Key": "jobboerse-jobsuche"}


def ba_item_to_jobpost(item: dict) -> Optional[JobPost]:
    if not isinstance(item, dict):
        return None
    addr = item.get("arbeitsort") or {}
    city = _s(addr.get("ort"))
    region = _s(addr.get("region"))
    location = ", ".join(p for p in (city, region, "Germany") if p)
    ref = _s(item.get("refnr"))
    return _build_official(
        title=item.get("titel") or item.get("beruf"),
        company=item.get("arbeitgeber"),
        location=location,
        description=item.get("beruf") or item.get("titel"),
        job_url=f"https://www.arbeitsagentur.de/jobsuche/jobdetail/{ref}" if ref and "/" not in ref else "https://www.arbeitsagentur.de/jobsuche/",
        source=JobSource.BA_JOBSUCHE,
        source_job_id=ref,
        posted_at=_parse_iso(item.get("aktuelleVeroeffentlichungsdatum") or item.get("modifikationsTimestamp")),
        country="DE",
        extra={"occupation": item.get("beruf"), "entry_date": item.get("eintrittsdatum")},
    )


async def scrape_ba_jobsuche(*, client: Optional[httpx.AsyncClient] = None, max_jobs: int = 500, query: str = "") -> list[JobPost]:
    params = {"size": min(max_jobs, 100), "page": 1}
    if query:
        params["was"] = query
    data = await safe_get_json(
        BA_JOBS_URL,
        client=client,
        params=params,
        headers=BA_HEADERS,
    )
    rows = (data or {}).get("stellenangebote") if isinstance(data, dict) else None
    if not isinstance(rows, list):
        return []
    out = [jp for row in rows for jp in [ba_item_to_jobpost(row)] if jp]
    return await _hydrate_detail_texts(out[:max_jobs], client=client)


# Singapore - MyCareersFuture

MCF_URL = "https://api.mycareersfuture.gov.sg/v2/jobs"


def mcf_item_to_jobpost(item: dict) -> Optional[JobPost]:
    if not isinstance(item, dict):
        return None
    company_obj = item.get("hiringCompany") or item.get("postedCompany") or {}
    address = item.get("address") or {}
    districts = address.get("districts") or []
    district = ", ".join(_s(d.get("location")) for d in districts if isinstance(d, dict) and d.get("location"))
    salary = item.get("salary") or {}
    meta = item.get("metadata") or {}
    url = meta.get("jobDetailsUrl") or (item.get("_links") or {}).get("self", {}).get("href")
    if url and str(url).startswith("/"):
        url = urljoin("https://www.mycareersfuture.gov.sg", str(url))
    return _build_official(
        title=item.get("title"),
        company=company_obj.get("name"),
        location=district or "Singapore",
        description=item.get("description"),
        job_url=url or "https://www.mycareersfuture.gov.sg/",
        source=JobSource.MYCAREERSFUTURE,
        source_job_id=item.get("uuid") or meta.get("jobPostId"),
        posted_at=_parse_iso(meta.get("newPostingDate") or meta.get("originalPostingDate")),
        country="SG",
        extra={
            "salary_min": salary.get("minimum"),
            "salary_max": salary.get("maximum"),
            "minimum_years_experience": item.get("minimumYearsExperience"),
            "skills": [s.get("skill") for s in item.get("skills") or [] if isinstance(s, dict) and s.get("skill")],
        },
    )


async def scrape_mycareersfuture(*, client: Optional[httpx.AsyncClient] = None, max_jobs: int = 500, query: str = "") -> list[JobPost]:
    params = {"limit": min(max_jobs, 100), "page": 0}
    if query:
        params["search"] = query
    data = await safe_get_json(MCF_URL, client=client, params=params)
    rows = (data or {}).get("results") if isinstance(data, dict) else None
    if not isinstance(rows, list):
        return []
    return [jp for row in rows for jp in [mcf_item_to_jobpost(row)] if jp][:max_jobs]


# France - France Travail API, env-gated OAuth2

FT_TOKEN_URL = "https://entreprise.francetravail.fr/connexion/oauth2/access_token"
FT_SEARCH_URL = "https://api.francetravail.io/partenaire/offresdemploi/v2/offres/search"


async def scrape_france_travail(*, client: Optional[httpx.AsyncClient] = None, max_jobs: int = 500, query: str = "") -> list[JobPost]:
    client_id = os.getenv("FRANCE_TRAVAIL_CLIENT_ID", "").strip()
    client_secret = os.getenv("FRANCE_TRAVAIL_CLIENT_SECRET", "").strip()
    if not client_id or not client_secret:
        logger.info("France Travail skipped: FRANCE_TRAVAIL_CLIENT_ID/SECRET not configured")
        return []
    own_client = client is None
    client = client or httpx.AsyncClient(timeout=20.0, follow_redirects=True)
    try:
        token_resp = await client.post(
            FT_TOKEN_URL,
            data={
                "grant_type": "client_credentials",
                "client_id": client_id,
                "client_secret": client_secret,
                "scope": "api_offresdemploiv2 o2dsoffre",
            },
        )
        if token_resp.status_code != 200:
            logger.info("France Travail token skipped: HTTP %s", token_resp.status_code)
            return []
        token = (token_resp.json() or {}).get("access_token")
        if not token:
            return []
        resp = await client.get(
            FT_SEARCH_URL,
            params={**({"motsCles": query} if query else {}), "range": f"0-{min(max_jobs, 149) - 1}"},
            headers={"Authorization": f"Bearer {token}"},
        )
        if resp.status_code != 200:
            logger.info("France Travail search skipped: HTTP %s", resp.status_code)
            return []
        rows = (resp.json() or {}).get("resultats") or []
        out: list[JobPost] = []
        for row in rows:
            company = (row.get("entreprise") or {}).get("nom")
            loc = row.get("lieuTravail") or {}
            out.append(_build_official(
                title=row.get("intitule"),
                company=company,
                location=", ".join(p for p in (_s(loc.get("libelle")), "France") if p),
                description=row.get("description"),
                job_url=row.get("origineOffre", {}).get("urlOrigine") or row.get("id"),
                source=JobSource.FRANCE_TRAVAIL,
                source_job_id=row.get("id"),
                posted_at=_parse_iso(row.get("dateCreation")),
                country="FR",
                extra={"contract": (row.get("typeContratLibelle") or row.get("typeContrat"))},
            ))
        return [j for j in out if j][:max_jobs]
    finally:
        if own_client:
            await client.aclose()


# Official public HTML pages. They are parsed only after safe_get_text confirms 200.

def _parse_nhs_jobs(html: str, *, max_jobs: int) -> list[JobPost]:
    soup = BeautifulSoup(html, "html.parser")
    out: list[JobPost] = []
    for card in soup.select("[data-test='search-result']")[:max_jobs]:
        link = card.select_one("[data-test='search-result-job-title']")
        title = link.get_text(" ", strip=True) if link else ""
        loc = card.select_one("[data-test='search-result-location']")
        emp = card.select_one("[data-test='search-result-employer']")
        out.append(_build_official(
            title=title,
            company=emp.get_text(" ", strip=True) if emp else "NHS",
            location=loc.get_text(" ", strip=True) if loc else "United Kingdom",
            description=card.get_text(" ", strip=True),
            job_url=urljoin("https://www.jobs.nhs.uk", link.get("href") if link else ""),
            source=JobSource.NHS_JOBS,
            source_job_id=(link.get("href") if link else title),
            posted_at=None,
            country="GB",
        ))
    return [j for j in out if j]


async def scrape_nhs_jobs(*, client: Optional[httpx.AsyncClient] = None, max_jobs: int = 500, query: str = "") -> list[JobPost]:
    text = await safe_get_text("https://www.jobs.nhs.uk/candidate/search/results", client=client, params={"keyword": query})
    jobs = _parse_nhs_jobs(text or "", max_jobs=max_jobs) if text else []
    return await _hydrate_detail_texts(jobs, client=client)


def _parse_findajob(html: str, *, max_jobs: int) -> list[JobPost]:
    soup = BeautifulSoup(html, "html.parser")
    out: list[JobPost] = []
    for card in soup.select(".search-result")[:max_jobs]:
        link = card.find("a", href=True)
        details = [li.get_text(" ", strip=True) for li in card.find_all("li")]
        company, location = "Find a Job", "United Kingdom"
        if len(details) > 1 and " - " in details[1]:
            company, location = [p.strip() for p in details[1].split(" - ", 1)]
        out.append(_build_official(
            title=link.get_text(" ", strip=True) if link else "",
            company=company,
            location=location,
            description=card.get_text(" ", strip=True),
            job_url=urljoin("https://findajob.dwp.gov.uk", link.get("href") if link else ""),
            source=JobSource.UK_FIND_A_JOB,
            source_job_id=card.get("data-aid") or (link.get("href") if link else ""),
            posted_at=_parse_date(details[0] if details else ""),
            country="GB",
            is_remote="remote" in card.get_text(" ", strip=True).lower(),
        ))
    return [j for j in out if j]


async def scrape_uk_findajob(*, client: Optional[httpx.AsyncClient] = None, max_jobs: int = 500, query: str = "") -> list[JobPost]:
    params = {"w": "UK"}
    if query:
        params["q"] = query
    text = await safe_get_text("https://findajob.dwp.gov.uk/search", client=client, params=params)
    jobs = _parse_findajob(text or "", max_jobs=max_jobs) if text else []
    return await _hydrate_detail_texts(jobs, client=client)


def _parse_jobbank(html: str, *, max_jobs: int) -> list[JobPost]:
    soup = BeautifulSoup(html, "html.parser")
    out: list[JobPost] = []
    for card in soup.select("article a.resultJobItem")[:max_jobs]:
        title_el = card.select_one(".noctitle")
        title = title_el.get_text(" ", strip=True) if title_el else ""
        text = card.get_text(" ", strip=True)
        company = "Job Bank employer"
        location = "Canada"
        m = re.search(r"Posted on .*?\s+(.+?)\s+Job details", text)
        if m:
            company = m.group(1).strip()
        loc = card.select_one(".location")
        if loc:
            location = loc.get_text(" ", strip=True)
        out.append(_build_official(
            title=title,
            company=company,
            location=location,
            description=text,
            job_url=urljoin("https://www.jobbank.gc.ca", card.get("href") or ""),
            source=JobSource.JOBBANK_CA,
            source_job_id=(card.get("href") or title),
            posted_at=None,
            country="CA",
        ))
    return [j for j in out if j]


async def scrape_jobbank_ca(*, client: Optional[httpx.AsyncClient] = None, max_jobs: int = 500, query: str = "") -> list[JobPost]:
    params = {"locationstring": "Canada"}
    if query:
        params["searchstring"] = query
    text = await safe_get_text("https://www.jobbank.gc.ca/jobsearch/jobsearch", client=client, params=params)
    jobs = _parse_jobbank(text or "", max_jobs=max_jobs) if text else []
    return await _hydrate_detail_texts(jobs, client=client)


def _parse_anchor_cards(html: str, *, source: JobSource, country: str, base_url: str, href_marker: str, max_jobs: int) -> list[JobPost]:
    soup = BeautifulSoup(html, "html.parser")
    out: list[JobPost] = []
    seen: set[str] = set()
    for link in soup.find_all("a", href=True):
        href = link.get("href") or ""
        if href_marker not in href or href in seen:
            continue
        seen.add(href)
        title = link.get_text(" ", strip=True)
        if len(title) < 4:
            continue
        container = link.find_parent(["article", "li", "div"]) or link
        text = container.get_text(" ", strip=True)
        out.append(_build_official(
            title=title,
            company=f"{source.value} employer",
            location=country,
            description=text,
            job_url=urljoin(base_url, href),
            source=source,
            source_job_id=href,
            posted_at=None,
            country=country,
        ))
        if len(out) >= max_jobs:
            break
    return [j for j in out if j]


async def scrape_nav_arbeidsplassen(*, client: Optional[httpx.AsyncClient] = None, max_jobs: int = 500, query: str = "") -> list[JobPost]:
    params = {"q": query} if query else None
    text = await safe_get_text("https://arbeidsplassen.nav.no/stillinger", client=client, params=params)
    return _parse_anchor_cards(text or "", source=JobSource.NAV_ARBEIDSPLASSEN, country="NO", base_url="https://arbeidsplassen.nav.no", href_marker="/stillinger/stilling/", max_jobs=max_jobs) if text else []


async def scrape_tyomarkkinatori(*, client: Optional[httpx.AsyncClient] = None, max_jobs: int = 500, query: str = "") -> list[JobPost]:
    params = {"ae": "NOW", "f": "MAX_3_DAYS", "p": 0, "ps": min(max_jobs, 100)}
    if query:
        params["hakusana"] = query
    text = await safe_get_text("https://tyomarkkinatori.fi/henkiloasiakkaat/avoimet-tyopaikat/", client=client, params=params)
    return _parse_anchor_cards(text or "", source=JobSource.TYOMARKKINATORI, country="FI", base_url="https://tyomarkkinatori.fi", href_marker="/henkiloasiakkaat/avoimet-tyopaikat/", max_jobs=max_jobs) if text else []


async def scrape_eures(*, client: Optional[httpx.AsyncClient] = None, max_jobs: int = 500) -> list[JobPost]:
    # EURES' old direct job-search URL currently 404s. Keep the source wired to
    # its public 200 jobseeker portal and parse cards if the portal exposes them.
    text = await safe_get_text("https://eures.europa.eu/jobseekers_en", client=client)
    return _parse_anchor_cards(text or "", source=JobSource.EURES, country="EU", base_url="https://eures.europa.eu", href_marker="/jobs/", max_jobs=max_jobs) if text else []


OFFICIAL_PORTAL_SOURCES = {
    "jobtech": scrape_jobtech,
    "ba_jobsuche": scrape_ba_jobsuche,
    "mycareersfuture": scrape_mycareersfuture,
    "france_travail": scrape_france_travail,
    "nhs_jobs": scrape_nhs_jobs,
    "uk_findajob": scrape_uk_findajob,
    "jobbank_ca": scrape_jobbank_ca,
    "nav_arbeidsplassen": scrape_nav_arbeidsplassen,
    "tyomarkkinatori": scrape_tyomarkkinatori,
    "eures": scrape_eures,
}

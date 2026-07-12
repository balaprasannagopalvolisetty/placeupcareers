"""
ATS career-board ingestion (structured JSON — no HTML scraping where possible).

Most modern HR / ATS platforms expose a public read-only JSON endpoint that
the company's own careers page consumes. Pulling from those is far more
reliable than scraping the rendered HTML and gives us the same coverage.

Supported ATS platforms (each takes a "board token" — a company-specific
identifier visible in the careers URL):

    Platform           Board token example      Public endpoint pattern
    --------------------------------------------------------------------
    Greenhouse         "duolingo"               boards-api.greenhouse.io/v1/boards/{token}/jobs
    Lever              "netflix"                api.lever.co/v0/postings/{token}?mode=json
    Ashby              "ramp"                   api.ashbyhq.com/posting-api/job-board/{token}
    SmartRecruiters    "Twilio"                 api.smartrecruiters.com/v1/companies/{token}/postings
    Workday            ("nvidia","External")    {tenant}.wd5.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs
    Recruitee          "hello"                  hello.recruitee.com/api/offers/
    Personio           "hubspot"                {token}.jobs.personio.de/xml
    Teamtailor         "hellofresh"             api.teamtailor.com/v1/jobs?filter[company]={token}
    JazzHR             "mycompany"              jazzhr.com/{token}/jobs.json
    Rippling           "stripe"                 ats.rippling.com/api/v1/companies/{token}/jobs
    BreezyHR           "acme"                   {token}.breezy.hr/json
    Pinpoint           "acme"                   {token}.pinpointhq.com/postings.json
    Polymer            "acme"                   jobs.polymer.co/api/v1/postings?job_board_slug={token}
    Jobvite            "acme"                   jobs.jobvite.com/{token} (anchor extraction)
    iCIMS              "acme"                   careers-{token}.icims.com/jobs/search (paginated HTML)
    Oracle Recruiting  ("host","CX_1")          {host}/hcmRestApi/resources/latest/recruitingCEJobRequisitions
    Paylocity          "guid"                   recruiting.paylocity.com/recruiting/v2/api/feed/jobs/{token}
    UKG / UltiPro      "TEN123/JobBoard/guid"   recruiting.ultipro.com/{token}/JobBoardView/LoadSearchResults
    Zoho Recruit       "acme"                   {token}.zohorecruit.com/jobs/Careers (anchor extraction)
    ADP WFN            "cid-guid"               workforcenow.adp.com .../staffing/v1/job-requisitions?cid={token}
    Dover              "acme"                   app.dover.io/api/v1/careers-page/{token}/jobs
    Gem                "acme"                   jobs.gem.com/{token} (anchor extraction)
    SuccessFactors     "https://jobs.acme.com"  {token}/search/?startrow=N (paginated HTML)
    Phenom             "careers.acme.com"       {domain}/api/apply/v2/jobs?domain={domain}
    Dayforce           "acme"                   jobs.dayforcehcm.com (JSON feed, HTML fallback)
    Join.com           "acme"                   join.com/companies/{token} (anchor extraction)
    Hireology          "acme"                   {token}.hireology.com (anchor extraction)

Every function returns a list of normalized JobPost objects compatible with
the rest of the pipeline. All scrapers degrade gracefully on error.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any, Optional

import httpx

from app.models.job import (
    JobCategory,
    JobPost,
    JobSource,
    SalaryRange,
)
from app.utils.deduplication import generate_content_hash, generate_job_id

logger = logging.getLogger(__name__)


# ─── Shared helpers ──────────────────────────────────────────────────────────

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
}


def _parse_dt(value: Any) -> Optional[datetime]:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    try:
        text = str(value).replace("Z", "+00:00")
        return datetime.fromisoformat(text)
    except (ValueError, TypeError):
        try:
            # Some ATS use epoch ms
            return datetime.utcfromtimestamp(int(value) / 1000)
        except (ValueError, TypeError):
            return None


def _location_name(loc: Any) -> str:
    if isinstance(loc, dict):
        return str(
            loc.get("name")
            or loc.get("address")
            or loc.get("locationName")
            or loc.get("city")
            or ""
        ).strip()
    if isinstance(loc, list):
        names = [_location_name(part) for part in loc]
        return ", ".join(n for n in names if n)
    return str(loc or "").strip()


def _safe_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


# ─── Greenhouse ──────────────────────────────────────────────────────────────

async def scrape_greenhouse_board(
    board_token: str,
    *,
    max_jobs: int = 2000,
    include_content: bool = True,
) -> list[JobPost]:
    """Pull open roles from a Greenhouse job board.

    Public endpoint: https://boards-api.greenhouse.io/v1/boards/{token}/jobs
    """
    token = board_token.strip()
    if not token:
        return []

    url = f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs"
    params = {"content": "true" if include_content else "false"}

    try:
        async with httpx.AsyncClient(timeout=45.0, headers=DEFAULT_HEADERS) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            payload = response.json()
    except Exception as exc:
        logger.warning("Greenhouse board %r: %s", token, exc)
        return []

    raw_jobs = payload.get("jobs") if isinstance(payload, dict) else None
    if not isinstance(raw_jobs, list):
        logger.warning("Greenhouse board %r: unexpected payload shape", token)
        return []

    jobs: list[JobPost] = []
    for item in raw_jobs[:max_jobs]:
        try:
            job = _greenhouse_item_to_jobpost(item, board_token=token)
            if job:
                jobs.append(job)
        except Exception as exc:  # noqa: BLE001
            logger.debug("Greenhouse: skip row: %s", exc)

    logger.info("Greenhouse %r: normalized %s jobs", token, len(jobs))
    return jobs


def _greenhouse_item_to_jobpost(item: dict, board_token: str) -> Optional[JobPost]:
    title = _safe_str(item.get("title"))
    company = _safe_str(item.get("company_name") or board_token)
    location = _location_name(item.get("location"))

    if not title:
        return None

    description = _safe_str(item.get("content") or item.get("internal_content"))
    job_url = _safe_str(item.get("absolute_url"))
    source_id = _safe_str(item.get("id") or item.get("internal_job_id"))

    job_id = generate_job_id(title, company, location or job_url or source_id)

    extra: dict[str, Any] = {
        "ats": "greenhouse",
        "board_token": board_token,
        "metadata": item.get("metadata") or [],
        "requisition_id": item.get("requisition_id"),
        "language": item.get("language"),
        "data_compliance": item.get("data_compliance"),
        "updated_at": item.get("updated_at"),
    }

    return JobPost(
        id=job_id,
        title=title,
        company=company,
        location=location,
        description=description,
        job_url=job_url,
        category=JobCategory.OTHER,
        source=JobSource.GREENHOUSE,
        source_job_id=source_id,
        posted_at=_parse_dt(item.get("first_published")),
        content_hash=generate_content_hash(title, company, location or board_token),
        scraped_at=datetime.utcnow(),
        extra_metadata={k: v for k, v in extra.items() if v not in (None, [], {})},
    )


# ─── Lever ───────────────────────────────────────────────────────────────────

async def scrape_lever_board(board_token: str, *, max_jobs: int = 2000) -> list[JobPost]:
    """Pull open roles from a Lever-hosted board.

    Public endpoint: https://api.lever.co/v0/postings/{token}?mode=json
    """
    token = board_token.strip()
    if not token:
        return []

    url = f"https://api.lever.co/v0/postings/{token}"
    params = {"mode": "json", "limit": min(max_jobs, 1000)}

    try:
        async with httpx.AsyncClient(timeout=45.0, headers=DEFAULT_HEADERS) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            payload = response.json()
    except Exception as exc:
        logger.warning("Lever board %r: %s", token, exc)
        return []

    if not isinstance(payload, list):
        return []

    jobs: list[JobPost] = []
    for item in payload[:max_jobs]:
        try:
            jobs.append(_lever_item_to_jobpost(item, board_token=token))
        except Exception as exc:  # noqa: BLE001
            logger.debug("Lever: skip row: %s", exc)

    jobs = [j for j in jobs if j]
    logger.info("Lever %r: normalized %s jobs", token, len(jobs))
    return jobs


def _lever_item_to_jobpost(item: dict, board_token: str) -> Optional[JobPost]:
    title = _safe_str(item.get("text"))
    if not title:
        return None
    categories = item.get("categories") or {}
    company = _safe_str(categories.get("team") or board_token)
    if not company or company == board_token:
        company = board_token

    location = _safe_str(categories.get("location"))
    description_parts = [_safe_str(item.get("description") or item.get("descriptionPlain"))]
    for section in item.get("lists") or []:
        if not isinstance(section, dict):
            continue
        heading = _safe_str(section.get("text"))
        content = _safe_str(section.get("content"))
        if heading or content:
            description_parts.append(f"<h3>{heading}</h3>{content}" if heading else content)
    description_html = "\n".join(part for part in description_parts if part)
    job_url = _safe_str(item.get("hostedUrl") or item.get("applyUrl"))
    source_id = _safe_str(item.get("id"))
    posted = _parse_dt(item.get("createdAt"))

    salary = None
    salary_range = item.get("salaryRange") or {}
    if isinstance(salary_range, dict) and (salary_range.get("min") or salary_range.get("max")):
        try:
            salary = SalaryRange(
                min_salary=float(salary_range.get("min") or 0) or None,
                max_salary=float(salary_range.get("max") or 0) or None,
                currency=_safe_str(salary_range.get("currency")) or "USD",
                period=_safe_str(salary_range.get("interval")).lower() or "yearly",
            )
        except (ValueError, TypeError):
            pass

    extra: dict[str, Any] = {
        "ats": "lever",
        "board_token": board_token,
        "categories": categories,
        "tags": item.get("tags") or [],
        "lists": item.get("lists") or [],
        "country": _safe_str(categories.get("country")),
        "department": _safe_str(categories.get("department")),
        "commitment": _safe_str(categories.get("commitment")),
        "workplace_type": _safe_str(item.get("workplaceType")),
    }

    return JobPost(
        id=generate_job_id(title, board_token, location or source_id),
        title=title,
        company=board_token.replace("-", " ").title() if company == board_token else company,
        location=location,
        description=description_html,
        job_url=job_url,
        category=JobCategory.OTHER,
        job_type=_safe_str(categories.get("commitment")),
        salary=salary,
        source=JobSource.LEVER,
        source_job_id=source_id,
        posted_at=posted,
        is_remote="remote" in location.lower() if location else None,
        content_hash=generate_content_hash(title, board_token, location or board_token),
        scraped_at=datetime.utcnow(),
        extra_metadata={k: v for k, v in extra.items() if v not in (None, "", [], {})},
    )


# ─── Ashby ───────────────────────────────────────────────────────────────────

async def scrape_ashby_board(board_token: str, *, max_jobs: int = 2000) -> list[JobPost]:
    """Pull open roles from an Ashby-hosted board.

    Public endpoint: https://api.ashbyhq.com/posting-api/job-board/{token}
    """
    token = board_token.strip()
    if not token:
        return []

    url = f"https://api.ashbyhq.com/posting-api/job-board/{token}"
    params = {"includeCompensation": "true"}

    try:
        async with httpx.AsyncClient(timeout=45.0, headers=DEFAULT_HEADERS) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            payload = response.json()
    except Exception as exc:
        logger.warning("Ashby board %r: %s", token, exc)
        return []

    raw_jobs = payload.get("jobs") if isinstance(payload, dict) else None
    if not isinstance(raw_jobs, list):
        return []

    jobs: list[JobPost] = []
    for item in raw_jobs[:max_jobs]:
        try:
            jobs.append(_ashby_item_to_jobpost(item, board_token=token))
        except Exception as exc:  # noqa: BLE001
            logger.debug("Ashby: skip row: %s", exc)

    jobs = [j for j in jobs if j]
    logger.info("Ashby %r: normalized %s jobs", token, len(jobs))
    return jobs


def _ashby_item_to_jobpost(item: dict, board_token: str) -> Optional[JobPost]:
    title = _safe_str(item.get("title"))
    if not title:
        return None
    company = board_token.replace("-", " ").title()
    location = _safe_str(item.get("location"))
    secondary_locations = item.get("secondaryLocations") or []
    if isinstance(secondary_locations, list) and secondary_locations and not location:
        location = _location_name(secondary_locations[0])

    description = _safe_str(item.get("descriptionHtml") or item.get("descriptionPlain"))
    job_url = _safe_str(item.get("jobUrl") or item.get("applyUrl"))
    source_id = _safe_str(item.get("id"))
    posted = _parse_dt(item.get("publishedAt") or item.get("updatedAt"))

    comp = item.get("compensation") or {}
    salary = None
    if isinstance(comp, dict) and comp:
        try:
            min_v = comp.get("compensationTierSummary", {}).get("min") or comp.get("min")
            max_v = comp.get("compensationTierSummary", {}).get("max") or comp.get("max")
            if min_v or max_v:
                salary = SalaryRange(
                    min_salary=float(min_v) if min_v else None,
                    max_salary=float(max_v) if max_v else None,
                    currency=_safe_str(comp.get("currency")) or "USD",
                    period="yearly",
                )
        except (ValueError, TypeError):
            pass

    extra: dict[str, Any] = {
        "ats": "ashby",
        "board_token": board_token,
        "department": _safe_str(item.get("department")),
        "team": _safe_str(item.get("team")),
        "employment_type": _safe_str(item.get("employmentType")),
        "is_remote": item.get("isRemote"),
        "address": item.get("address"),
        "secondary_locations": secondary_locations,
    }

    return JobPost(
        id=generate_job_id(title, company, location or source_id),
        title=title,
        company=company,
        location=location,
        description=description,
        job_url=job_url,
        category=JobCategory.OTHER,
        job_type=_safe_str(item.get("employmentType")),
        salary=salary,
        source=JobSource.ASHBY,
        source_job_id=source_id,
        posted_at=posted,
        is_remote=item.get("isRemote"),
        content_hash=generate_content_hash(title, company, location or board_token),
        scraped_at=datetime.utcnow(),
        extra_metadata={k: v for k, v in extra.items() if v not in (None, "", [], {})},
    )


# ─── SmartRecruiters ─────────────────────────────────────────────────────────

async def scrape_smartrecruiters_board(board_token: str, *, max_jobs: int = 2000) -> list[JobPost]:
    """Pull open roles from SmartRecruiters.

    Public endpoint: https://api.smartrecruiters.com/v1/companies/{token}/postings
    """
    token = board_token.strip()
    if not token:
        return []

    url = f"https://api.smartrecruiters.com/v1/companies/{token}/postings"
    jobs: list[JobPost] = []
    page_size = 100
    offset = 0

    try:
        async with httpx.AsyncClient(timeout=45.0, headers=DEFAULT_HEADERS) as client:
            while len(jobs) < max_jobs:
                params = {"limit": page_size, "offset": offset}
                response = await client.get(url, params=params)
                response.raise_for_status()
                payload = response.json()
                items = payload.get("content") or []
                if not items:
                    break
                for item in items:
                    job = _smartrecruiters_item_to_jobpost(item, board_token=token)
                    if job:
                        jobs.append(job)
                got = len(items)
                if got < page_size:
                    break
                offset += got
                await asyncio.sleep(0.3)
    except Exception as exc:
        logger.warning("SmartRecruiters %r: %s", token, exc)

    logger.info("SmartRecruiters %r: normalized %s jobs", token, len(jobs))
    return jobs[:max_jobs]


def _smartrecruiters_item_to_jobpost(item: dict, board_token: str) -> Optional[JobPost]:
    title = _safe_str(item.get("name"))
    if not title:
        return None
    company = _safe_str((item.get("company") or {}).get("name") or board_token)
    location_dict = item.get("location") or {}
    parts = [
        _safe_str(location_dict.get("city")),
        _safe_str(location_dict.get("region")),
        _safe_str(location_dict.get("country")),
    ]
    location = ", ".join(p for p in parts if p)

    job_url = _safe_str(item.get("ref") or (item.get("releasedDate") and item.get("id")))
    posting_url = _safe_str(item.get("applyUrl") or item.get("ref"))
    if not posting_url:
        posting_url = f"https://jobs.smartrecruiters.com/{board_token}/{item.get('id', '')}"

    posted = _parse_dt(item.get("releasedDate") or item.get("createdOn"))
    source_id = _safe_str(item.get("id"))

    extra: dict[str, Any] = {
        "ats": "smartrecruiters",
        "board_token": board_token,
        "industry": _safe_str((item.get("industry") or {}).get("label")),
        "department": _safe_str((item.get("department") or {}).get("label")),
        "function": _safe_str((item.get("function") or {}).get("label")),
        "type_of_employment": _safe_str((item.get("typeOfEmployment") or {}).get("label")),
        "remote": location_dict.get("remote"),
    }

    return JobPost(
        id=generate_job_id(title, company, location or source_id),
        title=title,
        company=company,
        location=location,
        job_url=posting_url,
        category=JobCategory.OTHER,
        job_type=_safe_str((item.get("typeOfEmployment") or {}).get("label")),
        source=JobSource.SMARTRECRUITERS,
        source_job_id=source_id,
        posted_at=posted,
        is_remote=bool(location_dict.get("remote")),
        content_hash=generate_content_hash(title, company, location or board_token),
        scraped_at=datetime.utcnow(),
        extra_metadata={k: v for k, v in extra.items() if v not in (None, "", [], {})},
    )


# ─── Workday ─────────────────────────────────────────────────────────────────

async def scrape_workday_board(
    tenant: str,
    site: str,
    *,
    base_host: str = "wd5.myworkdayjobs.com",
    max_jobs: int = 2000,
    page_size: int = 50,
    search_text: str = "",
) -> list[JobPost]:
    """Pull open roles from a Workday-hosted careers site.

    Workday URLs look like:
        https://nvidia.wd5.myworkdayjobs.com/External
    Where:
        tenant = "nvidia"
        site   = "External"
        base_host = "wd5.myworkdayjobs.com"

    Public endpoint:
        POST https://{tenant}.{base_host}/wday/cxs/{tenant}/{site}/jobs
    """
    if not tenant or not site:
        return []

    url = f"https://{tenant}.{base_host}/wday/cxs/{tenant}/{site}/jobs"
    jobs: list[JobPost] = []
    offset = 0

    payload = {
        "appliedFacets": {},
        "limit": min(page_size, 50),
        "offset": offset,
        "searchText": search_text,
    }

    headers = {
        **DEFAULT_HEADERS,
        "Content-Type": "application/json",
        "Origin": f"https://{tenant}.{base_host}",
        "Referer": f"https://{tenant}.{base_host}/{site}",
    }

    try:
        async with httpx.AsyncClient(timeout=45.0, headers=headers) as client:
            while len(jobs) < max_jobs:
                payload["offset"] = offset
                response = await client.post(url, json=payload)
                if response.status_code in (400, 401, 403, 404, 422):
                    logger.info(
                        "Workday %s/%s unavailable via public CXS endpoint (status=%s)",
                        tenant,
                        site,
                        response.status_code,
                    )
                    return jobs
                response.raise_for_status()
                data = response.json()
                postings = data.get("jobPostings") or []
                if not postings:
                    break
                for posting in postings:
                    job = _workday_posting_to_jobpost(posting, tenant=tenant, site=site, base_host=base_host)
                    if job:
                        jobs.append(job)
                got = len(postings)
                if got < payload["limit"]:
                    break
                offset += got
                await asyncio.sleep(0.4)
    except Exception as exc:
        logger.info("Workday %s/%s unavailable: %s", tenant, site, exc)

    logger.info("Workday %s/%s: normalized %s jobs", tenant, site, len(jobs))
    return jobs[:max_jobs]


def _workday_posting_to_jobpost(
    posting: dict, *, tenant: str, site: str, base_host: str
) -> Optional[JobPost]:
    title = _safe_str(posting.get("title"))
    if not title:
        return None

    company = tenant.replace("-", " ").title()
    location = _safe_str(posting.get("locationsText") or posting.get("primaryLocation"))
    external_path = _safe_str(posting.get("externalPath"))
    job_url = ""
    if external_path:
        job_url = f"https://{tenant}.{base_host}/{site}{external_path}"

    posted = _parse_dt(posting.get("postedOn") or posting.get("startDate"))
    source_id = _safe_str(posting.get("bulletFields", [None])[0] if posting.get("bulletFields") else "")
    if not source_id:
        source_id = _safe_str(posting.get("jobPostingId") or external_path)

    extra: dict[str, Any] = {
        "ats": "workday",
        "tenant": tenant,
        "site": site,
        "bullet_fields": posting.get("bulletFields"),
        "external_path": external_path,
    }

    return JobPost(
        id=generate_job_id(title, company, location or external_path),
        title=title,
        company=company,
        location=location,
        job_url=job_url,
        category=JobCategory.OTHER,
        source=JobSource.WORKDAY,
        source_job_id=source_id,
        posted_at=posted,
        content_hash=generate_content_hash(title, company, location or tenant),
        scraped_at=datetime.utcnow(),
        extra_metadata={k: v for k, v in extra.items() if v not in (None, "", [], {})},
    )


# ─── Recruitee ───────────────────────────────────────────────────────────────

async def scrape_recruitee_board(board_token: str, *, max_jobs: int = 2000) -> list[JobPost]:
    """Pull open roles from a Recruitee-hosted board.

    Public endpoint: https://{token}.recruitee.com/api/offers/
    """
    token = board_token.strip()
    if not token:
        return []

    url = f"https://{token}.recruitee.com/api/offers/"
    try:
        async with httpx.AsyncClient(timeout=45.0, headers=DEFAULT_HEADERS) as client:
            response = await client.get(url)
            response.raise_for_status()
            payload = response.json()
    except Exception as exc:
        logger.warning("Recruitee %r: %s", token, exc)
        return []

    offers = payload.get("offers") if isinstance(payload, dict) else None
    if not isinstance(offers, list):
        return []

    jobs: list[JobPost] = []
    for item in offers[:max_jobs]:
        try:
            jobs.append(_recruitee_item_to_jobpost(item, board_token=token))
        except Exception as exc:  # noqa: BLE001
            logger.debug("Recruitee: skip row: %s", exc)
    jobs = [j for j in jobs if j]
    logger.info("Recruitee %r: normalized %s jobs", token, len(jobs))
    return jobs


def _recruitee_item_to_jobpost(item: dict, board_token: str) -> Optional[JobPost]:
    title = _safe_str(item.get("title"))
    if not title:
        return None
    company = board_token.replace("-", " ").title()
    location = _safe_str(item.get("location") or item.get("city") or item.get("country"))
    description = _safe_str(item.get("description") or item.get("requirements"))
    job_url = _safe_str(item.get("careers_url") or item.get("careers_apply_url"))
    posted = _parse_dt(item.get("created_at"))

    extra: dict[str, Any] = {
        "ats": "recruitee",
        "board_token": board_token,
        "department": _safe_str(item.get("department")),
        "country": _safe_str(item.get("country")),
        "city": _safe_str(item.get("city")),
        "remote": item.get("remote"),
        "tags": item.get("tags") or [],
        "category": _safe_str(item.get("category")),
    }

    return JobPost(
        id=generate_job_id(title, company, location or str(item.get("id"))),
        title=title,
        company=company,
        location=location,
        description=description,
        job_url=job_url,
        category=JobCategory.OTHER,
        job_type=_safe_str(item.get("employment_type")),
        source=JobSource.RECRUITEE,
        source_job_id=_safe_str(item.get("id")),
        posted_at=posted,
        is_remote=bool(item.get("remote")),
        content_hash=generate_content_hash(title, company, location or board_token),
        scraped_at=datetime.utcnow(),
        extra_metadata={k: v for k, v in extra.items() if v not in (None, "", [], {})},
    )


# ─── Personio (XML) ──────────────────────────────────────────────────────────

async def scrape_personio_board(board_token: str, *, max_jobs: int = 2000) -> list[JobPost]:
    """Pull open roles from a Personio-hosted board (XML feed).

    Public endpoint: https://{token}.jobs.personio.de/xml
    """
    token = board_token.strip()
    if not token:
        return []

    url = f"https://{token}.jobs.personio.de/xml"
    try:
        async with httpx.AsyncClient(timeout=45.0, headers=DEFAULT_HEADERS) as client:
            response = await client.get(url)
            response.raise_for_status()
            xml_text = response.text
    except Exception as exc:
        logger.warning("Personio %r: %s", token, exc)
        return []

    try:
        from xml.etree import ElementTree as ET

        root = ET.fromstring(xml_text)
    except Exception as exc:
        logger.warning("Personio %r: XML parse failed: %s", token, exc)
        return []

    jobs: list[JobPost] = []
    for position in root.findall(".//position")[:max_jobs]:
        title = _safe_str(position.findtext("name"))
        if not title:
            continue
        company = board_token.replace("-", " ").title()
        location = _safe_str(position.findtext("office"))
        description = _safe_str(
            (position.findtext("jobDescriptions/jobDescription/value") or "").strip()
        )
        job_url = _safe_str(position.attrib.get("url") or position.findtext("url"))
        source_id = _safe_str(position.findtext("id"))
        posted = _parse_dt(position.findtext("createdAt"))

        extra: dict[str, Any] = {
            "ats": "personio",
            "board_token": board_token,
            "department": _safe_str(position.findtext("department")),
            "subcompany": _safe_str(position.findtext("subcompany")),
            "schedule": _safe_str(position.findtext("schedule")),
            "years_of_experience": _safe_str(position.findtext("yearsOfExperience")),
        }

        jobs.append(JobPost(
            id=generate_job_id(title, company, location or source_id),
            title=title,
            company=company,
            location=location,
            description=description,
            job_url=job_url,
            category=JobCategory.OTHER,
            source=JobSource.PERSONIO,
            source_job_id=source_id,
            posted_at=posted,
            content_hash=generate_content_hash(title, company, location or board_token),
            scraped_at=datetime.utcnow(),
            extra_metadata={k: v for k, v in extra.items() if v not in (None, "", [], {})},
        ))

    logger.info("Personio %r: normalized %s jobs", token, len(jobs))
    return jobs


# ─── Teamtailor ──────────────────────────────────────────────────────────────

async def scrape_teamtailor_board(board_token: str, *, max_jobs: int = 2000) -> list[JobPost]:
    """Pull open roles from a Teamtailor-hosted board.

    Public endpoint: https://{token}.teamtailor.com/jobs.json
    """
    token = board_token.strip()
    if not token:
        return []

    url = f"https://{token}.teamtailor.com/jobs.json"
    try:
        async with httpx.AsyncClient(timeout=45.0, headers=DEFAULT_HEADERS) as client:
            response = await client.get(url)
            response.raise_for_status()
            payload = response.json()
    except Exception as exc:
        logger.warning("Teamtailor %r: %s", token, exc)
        return []

    items = payload if isinstance(payload, list) else payload.get("jobs") or payload.get("data") or []
    jobs: list[JobPost] = []
    for item in items[:max_jobs]:
        try:
            jobs.append(_teamtailor_item_to_jobpost(item, board_token=token))
        except Exception as exc:  # noqa: BLE001
            logger.debug("Teamtailor: skip row: %s", exc)
    jobs = [j for j in jobs if j]
    logger.info("Teamtailor %r: normalized %s jobs", token, len(jobs))
    return jobs


def _teamtailor_item_to_jobpost(item: dict, board_token: str) -> Optional[JobPost]:
    attrs = item.get("attributes") or item
    title = _safe_str(attrs.get("title"))
    if not title:
        return None
    company = board_token.replace("-", " ").title()
    location = _safe_str(attrs.get("location") or attrs.get("city"))
    description = _safe_str(attrs.get("body") or attrs.get("description"))
    job_url = _safe_str(attrs.get("share-link") or attrs.get("careers-page-url") or attrs.get("apply-url"))
    posted = _parse_dt(attrs.get("created-at") or attrs.get("publication-date"))
    source_id = _safe_str(item.get("id") or attrs.get("id"))

    extra: dict[str, Any] = {
        "ats": "teamtailor",
        "board_token": board_token,
        "remote_status": _safe_str(attrs.get("remote-status")),
        "language": _safe_str(attrs.get("language")),
    }

    return JobPost(
        id=generate_job_id(title, company, location or source_id),
        title=title,
        company=company,
        location=location,
        description=description,
        job_url=job_url,
        category=JobCategory.OTHER,
        source=JobSource.TEAMTAILOR,
        source_job_id=source_id,
        posted_at=posted,
        is_remote="remote" in (_safe_str(attrs.get("remote-status")).lower()),
        content_hash=generate_content_hash(title, company, location or board_token),
        scraped_at=datetime.utcnow(),
        extra_metadata={k: v for k, v in extra.items() if v not in (None, "", [], {})},
    )


# ─── JazzHR ──────────────────────────────────────────────────────────────────

async def scrape_jazzhr_board(board_token: str, *, max_jobs: int = 2000) -> list[JobPost]:
    """Pull open roles from a JazzHR-hosted board.

    Public endpoint: https://{token}.applytojob.com/apply/jobs/?ajax=1&search_keywords=
    Alternative: https://www.jazzhr.com/<token>/jobs.json
    """
    token = board_token.strip()
    if not token:
        return []

    url = f"https://{token}.applytojob.com/api/apply/jobs?type=Active"
    try:
        async with httpx.AsyncClient(timeout=45.0, headers=DEFAULT_HEADERS) as client:
            response = await client.get(url)
            response.raise_for_status()
            payload = response.json()
    except Exception as exc:
        logger.warning("JazzHR %r: %s", token, exc)
        return []

    items = payload.get("jobs") if isinstance(payload, dict) else payload
    if not isinstance(items, list):
        return []

    jobs: list[JobPost] = []
    for item in items[:max_jobs]:
        try:
            title = _safe_str(item.get("title") or item.get("position_title"))
            if not title:
                continue
            company = board_token.replace("-", " ").title()
            location = _safe_str(item.get("location") or item.get("city"))
            description = _safe_str(item.get("description"))
            job_url = _safe_str(item.get("apply_url") or item.get("url"))

            jobs.append(JobPost(
                id=generate_job_id(title, company, location or str(item.get("id", ""))),
                title=title,
                company=company,
                location=location,
                description=description,
                job_url=job_url,
                category=JobCategory.OTHER,
                source=JobSource.JAZZHR,
                source_job_id=_safe_str(item.get("id")),
                posted_at=_parse_dt(item.get("create_date") or item.get("created_at")),
                content_hash=generate_content_hash(title, company, location or board_token),
                scraped_at=datetime.utcnow(),
                extra_metadata={"ats": "jazzhr", "board_token": board_token},
            ))
        except Exception as exc:  # noqa: BLE001
            logger.debug("JazzHR: skip row: %s", exc)

    logger.info("JazzHR %r: normalized %s jobs", token, len(jobs))
    return jobs


# ─── Rippling (ATS / RipplingATS) ────────────────────────────────────────────

async def scrape_rippling_board(board_token: str, *, max_jobs: int = 2000) -> list[JobPost]:
    """Pull open roles from a Rippling ATS hosted board.

    Public endpoint: https://ats.rippling.com/api/v1/companies/{token}/jobs
    """
    token = board_token.strip()
    if not token:
        return []

    url = f"https://ats.rippling.com/api/v1/companies/{token}/jobs"
    try:
        async with httpx.AsyncClient(timeout=45.0, headers=DEFAULT_HEADERS) as client:
            response = await client.get(url)
            response.raise_for_status()
            payload = response.json()
    except Exception as exc:
        logger.warning("Rippling %r: %s", token, exc)
        return []

    items = payload if isinstance(payload, list) else payload.get("jobs") or []
    jobs: list[JobPost] = []
    for item in items[:max_jobs]:
        try:
            title = _safe_str(item.get("name") or item.get("title"))
            if not title:
                continue
            company = board_token.replace("-", " ").title()
            location = _safe_str((item.get("workLocation") or {}).get("label") or item.get("location"))
            description = _safe_str(item.get("description"))
            job_url = _safe_str(item.get("url") or item.get("hostedUrl"))

            jobs.append(JobPost(
                id=generate_job_id(title, company, location or str(item.get("id", ""))),
                title=title,
                company=company,
                location=location,
                description=description,
                job_url=job_url,
                category=JobCategory.OTHER,
                source=JobSource.RIPPLING,
                source_job_id=_safe_str(item.get("id")),
                posted_at=_parse_dt(item.get("postedAt")),
                content_hash=generate_content_hash(title, company, location or board_token),
                scraped_at=datetime.utcnow(),
                extra_metadata={"ats": "rippling", "board_token": board_token},
            ))
        except Exception as exc:  # noqa: BLE001
            logger.debug("Rippling: skip row: %s", exc)

    logger.info("Rippling %r: normalized %s jobs", token, len(jobs))
    return jobs


# ─── BambooHR ────────────────────────────────────────────────────────────────

async def scrape_bamboohr_board(board_token: str, *, max_jobs: int = 2000) -> list[JobPost]:
    """Pull open roles from a BambooHR-hosted board.

    Public endpoint: https://{token}.bamboohr.com/careers/list
    Returns simple JSON of openings.
    """
    token = board_token.strip()
    if not token:
        return []

    url = f"https://{token}.bamboohr.com/careers/list"
    try:
        async with httpx.AsyncClient(timeout=45.0, headers=DEFAULT_HEADERS) as client:
            response = await client.get(url)
            response.raise_for_status()
            payload = response.json()
    except Exception as exc:
        logger.warning("BambooHR %r: %s", token, exc)
        return []

    items = payload.get("result") if isinstance(payload, dict) else payload
    if not isinstance(items, list):
        return []

    jobs: list[JobPost] = []
    for item in items[:max_jobs]:
        try:
            title = _safe_str(item.get("jobOpeningName"))
            if not title:
                continue
            company = board_token.replace("-", " ").title()
            location = _safe_str(item.get("location", {}).get("city")) if isinstance(item.get("location"), dict) else _safe_str(item.get("location"))
            job_id_n = _safe_str(item.get("id"))
            job_url = f"https://{token}.bamboohr.com/careers/{job_id_n}" if job_id_n else ""

            jobs.append(JobPost(
                id=generate_job_id(title, company, location or job_id_n),
                title=title,
                company=company,
                location=location,
                job_url=job_url,
                category=JobCategory.OTHER,
                job_type=_safe_str(item.get("employmentStatusLabel")),
                source=JobSource.BAMBOOHR,
                source_job_id=job_id_n,
                posted_at=_parse_dt(item.get("datePosted")),
                content_hash=generate_content_hash(title, company, location or board_token),
                scraped_at=datetime.utcnow(),
                extra_metadata={"ats": "bamboohr", "board_token": board_token, "department": _safe_str(item.get("departmentLabel"))},
            ))
        except Exception as exc:  # noqa: BLE001
            logger.debug("BambooHR: skip row: %s", exc)

    logger.info("BambooHR %r: normalized %s jobs", token, len(jobs))
    return jobs


# ─── Workable ────────────────────────────────────────────────────────────────

async def scrape_workable_board(board_token: str, *, max_jobs: int = 2000) -> list[JobPost]:
    """Pull open roles from a Workable-hosted board.

    Public endpoint: https://apply.workable.com/api/v3/accounts/{token}/jobs?state=published

    Workable paginates with a `nextPage` token. We follow the pagination
    chain up to `max_jobs` rows so boards with thousands of openings
    actually come through fully (27,000+ SMB companies use Workable so
    this is one of the most valuable feeds).
    """
    token = board_token.strip()
    if not token:
        return []

    base_url = f"https://apply.workable.com/api/v3/accounts/{token}/jobs"
    params: dict[str, Any] = {"state": "published", "limit": 100}
    jobs: list[JobPost] = []

    try:
        async with httpx.AsyncClient(timeout=45.0, headers=DEFAULT_HEADERS) as client:
            while len(jobs) < max_jobs:
                response = await client.get(base_url, params=params)
                if response.status_code in (403, 404):
                    # Account doesn't exist or board is private — fail quietly.
                    return jobs
                response.raise_for_status()
                payload = response.json() if response.content else {}
                items = payload.get("results") if isinstance(payload, dict) else None
                if not isinstance(items, list) or not items:
                    break
                for item in items:
                    if len(jobs) >= max_jobs:
                        break
                    parsed = _workable_item_to_jobpost(item, board_token=token)
                    if parsed:
                        jobs.append(parsed)
                # Workable returns nextPage as an opaque token; absent → done.
                next_page = payload.get("nextPage") if isinstance(payload, dict) else None
                if not next_page:
                    break
                params = {"state": "published", "limit": 100, "since_id": next_page}
    except Exception as exc:  # noqa: BLE001
        logger.warning("Workable %r: %s", token, exc)
        return jobs

    logger.info("Workable %r: normalized %s jobs", token, len(jobs))
    return jobs


def _workable_item_to_jobpost(item: dict, board_token: str) -> Optional[JobPost]:
    title = _safe_str(item.get("title"))
    if not title:
        return None
    # Workable's response uses `company` when available, else fall back to
    # the slug-derived display name so the catalog name still wins later.
    company = _safe_str(item.get("company") or board_token.replace("-", " ").title())
    location_obj = item.get("location") or {}
    if isinstance(location_obj, dict):
        location = ", ".join(
            x for x in [
                _safe_str(location_obj.get("city")),
                _safe_str(location_obj.get("region")),
                _safe_str(location_obj.get("country")),
            ] if x
        )
    else:
        location = _safe_str(location_obj)
    description = _safe_str(item.get("description") or item.get("requirements") or "")
    shortcode = _safe_str(item.get("shortcode") or item.get("id"))
    job_url = _safe_str(item.get("url") or item.get("application_url"))
    if not job_url and shortcode:
        job_url = f"https://apply.workable.com/{board_token}/j/{shortcode}/"

    is_remote = bool(item.get("remote") or (isinstance(location_obj, dict) and location_obj.get("workplace") == "remote"))
    return JobPost(
        id=generate_job_id(title, company, location or shortcode),
        title=title,
        company=company,
        location=location,
        description=description,
        job_url=job_url,
        category=JobCategory.OTHER,
        job_type=_safe_str(item.get("employment_type")),
        source=JobSource.WORKABLE,
        source_job_id=shortcode,
        posted_at=_parse_dt(item.get("published") or item.get("created_at")),
        is_remote=is_remote,
        content_hash=generate_content_hash(title, company, location or board_token),
        scraped_at=datetime.utcnow(),
        extra_metadata={
            "ats": "workable",
            "board_token": board_token,
            "department": _safe_str(item.get("department")),
            "function": _safe_str(item.get("function")),
        },
    )


# ─── Extended-coverage helpers ───────────────────────────────────────────────
#
# The scrapers below cover the remaining major ATS platforms. All follow the
# same contract as the originals: public unauthenticated endpoint, JSON first,
# HTML anchor-extraction fallback where a platform has no JSON feed, and
# graceful [] + warning on any failure so one provider never kills a sweep.

import re as _re

_TAG_RE = _re.compile(r"<[^>]+>")
_WS_RE = _re.compile(r"\s+")


def _strip_html(value: Any) -> str:
    import html as _html
    text = _TAG_RE.sub(" ", str(value or ""))
    return _WS_RE.sub(" ", _html.unescape(text)).strip()


async def _http_json(
    url: str,
    *,
    method: str = "GET",
    params: dict | None = None,
    json_body: dict | None = None,
    timeout: float = 45.0,
) -> Any:
    async with httpx.AsyncClient(timeout=timeout, headers=DEFAULT_HEADERS, follow_redirects=True) as client:
        if method == "POST":
            response = await client.post(url, params=params, json=json_body)
        else:
            response = await client.get(url, params=params)
        response.raise_for_status()
        return response.json()


async def _http_text(url: str, *, params: dict | None = None, timeout: float = 45.0) -> str:
    async with httpx.AsyncClient(timeout=timeout, headers=DEFAULT_HEADERS, follow_redirects=True) as client:
        response = await client.get(url, params=params)
        response.raise_for_status()
        return response.text


def _anchor_jobs(page_html: str, href_pattern: str, *, base_url: str = "") -> list[tuple[str, str]]:
    """Extract (absolute_url, anchor_text) pairs whose href matches the pattern.

    Used for ATS platforms without a public JSON feed. Only anchors with a
    non-empty text payload survive, which filters nav/pagination links.
    """
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    anchor_re = _re.compile(
        rf"<a\b[^>]*?href=[\"']({href_pattern})[\"'][^>]*>(.*?)</a>",
        _re.IGNORECASE | _re.DOTALL,
    )
    for match in anchor_re.finditer(page_html or ""):
        href = match.group(1).strip()
        title = _strip_html(match.group(2))
        if not title or len(title) < 3:
            continue
        if href.startswith("/") and base_url:
            href = base_url.rstrip("/") + href
        if href in seen:
            continue
        seen.add(href)
        out.append((href, title))
    return out


def _company_from_token(board_token: str) -> str:
    return str(board_token or "").replace("-", " ").replace("_", " ").strip().title()


def _simple_jobpost(
    *,
    ats: str,
    source: JobSource,
    board_token: str,
    title: str,
    job_url: str,
    location: str = "",
    description: str = "",
    source_job_id: str = "",
    posted_at: Optional[datetime] = None,
    job_type: str = "",
    extra: dict | None = None,
) -> JobPost:
    company = _company_from_token(board_token)
    metadata = {"ats": ats, "board_token": str(board_token)}
    for key, value in (extra or {}).items():
        if value not in (None, "", [], {}):
            metadata[key] = value
    return JobPost(
        id=generate_job_id(title, company, location or source_job_id or job_url),
        title=title,
        company=company,
        location=location,
        description=description,
        job_url=job_url,
        category=JobCategory.OTHER,
        job_type=job_type,
        source=source,
        source_job_id=source_job_id,
        posted_at=posted_at,
        content_hash=generate_content_hash(title, company, location or str(board_token)),
        scraped_at=datetime.utcnow(),
        extra_metadata=metadata,
    )


# ─── BreezyHR ────────────────────────────────────────────────────────────────

async def scrape_breezyhr_board(board_token: str, *, max_jobs: int = 2000) -> list[JobPost]:
    """Public endpoint: https://{token}.breezy.hr/json"""
    token = board_token.strip()
    if not token:
        return []
    try:
        payload = await _http_json(f"https://{token}.breezy.hr/json")
    except Exception as exc:
        logger.warning("BreezyHR %r: %s", token, exc)
        return []
    items = payload if isinstance(payload, list) else []
    jobs: list[JobPost] = []
    for item in items[:max_jobs]:
        try:
            title = _safe_str(item.get("name"))
            if not title:
                continue
            loc = item.get("location") or {}
            location = _location_name(loc)
            country = _safe_str((loc.get("country") or {}).get("name")) if isinstance(loc, dict) else ""
            jobs.append(_simple_jobpost(
                ats="breezyhr", source=JobSource.BREEZYHR, board_token=token,
                title=title,
                job_url=_safe_str(item.get("url")) or f"https://{token}.breezy.hr/p/{_safe_str(item.get('id'))}",
                location=location,
                description=_strip_html(item.get("description")),
                source_job_id=_safe_str(item.get("id")),
                posted_at=_parse_dt(item.get("published_date")),
                job_type=_safe_str((item.get("type") or {}).get("name") if isinstance(item.get("type"), dict) else item.get("type")),
                extra={"department": _safe_str(item.get("department")), "country": country},
            ))
        except Exception as exc:  # noqa: BLE001
            logger.debug("BreezyHR: skip row: %s", exc)
    logger.info("BreezyHR %r: normalized %s jobs", token, len(jobs))
    return jobs


# ─── Pinpoint ────────────────────────────────────────────────────────────────

async def scrape_pinpoint_board(board_token: str, *, max_jobs: int = 2000) -> list[JobPost]:
    """Public endpoint: https://{token}.pinpointhq.com/postings.json"""
    token = board_token.strip()
    if not token:
        return []
    try:
        payload = await _http_json(f"https://{token}.pinpointhq.com/postings.json")
    except Exception as exc:
        logger.warning("Pinpoint %r: %s", token, exc)
        return []
    items = payload.get("data") if isinstance(payload, dict) else payload
    if not isinstance(items, list):
        return []
    jobs: list[JobPost] = []
    for item in items[:max_jobs]:
        try:
            attrs = item.get("attributes") if isinstance(item.get("attributes"), dict) else item
            title = _safe_str(attrs.get("title") or attrs.get("name"))
            if not title:
                continue
            location = _location_name(attrs.get("location")) or _safe_str(attrs.get("location_name"))
            jobs.append(_simple_jobpost(
                ats="pinpoint", source=JobSource.PINPOINT, board_token=token,
                title=title,
                job_url=_safe_str(attrs.get("url") or attrs.get("careers_url"))
                        or f"https://{token}.pinpointhq.com/postings/{_safe_str(item.get('id'))}",
                location=location,
                description=_strip_html(attrs.get("description")),
                source_job_id=_safe_str(item.get("id")),
                posted_at=_parse_dt(attrs.get("created_at") or attrs.get("published_at")),
                job_type=_safe_str(attrs.get("employment_type")),
                extra={"department": _location_name(attrs.get("department")), "workplace_type": _safe_str(attrs.get("workplace_type"))},
            ))
        except Exception as exc:  # noqa: BLE001
            logger.debug("Pinpoint: skip row: %s", exc)
    logger.info("Pinpoint %r: normalized %s jobs", token, len(jobs))
    return jobs


# ─── Polymer ─────────────────────────────────────────────────────────────────

async def scrape_polymer_board(board_token: str, *, max_jobs: int = 2000) -> list[JobPost]:
    """JSON widget API first, HTML board fallback.

    Widget endpoint: https://jobs.polymer.co/api/v1/postings?job_board_slug={token}
    Board page:      https://jobs.polymer.co/{token}
    """
    token = board_token.strip()
    if not token:
        return []
    jobs: list[JobPost] = []
    try:
        payload = await _http_json("https://jobs.polymer.co/api/v1/postings", params={"job_board_slug": token})
        items = payload.get("items") or payload.get("postings") or payload.get("data") if isinstance(payload, dict) else payload
        if isinstance(items, list):
            for item in items[:max_jobs]:
                title = _safe_str(item.get("title") or item.get("name"))
                if not title:
                    continue
                jobs.append(_simple_jobpost(
                    ats="polymer", source=JobSource.POLYMER, board_token=token,
                    title=title,
                    job_url=_safe_str(item.get("url") or item.get("public_url")) or f"https://jobs.polymer.co/{token}/{_safe_str(item.get('id'))}",
                    location=_location_name(item.get("location")),
                    description=_strip_html(item.get("description")),
                    source_job_id=_safe_str(item.get("id")),
                    posted_at=_parse_dt(item.get("created_at") or item.get("published_at")),
                    job_type=_safe_str(item.get("employment_type")),
                ))
    except Exception as exc:
        logger.debug("Polymer JSON %r failed (%s); falling back to HTML", token, exc)
    if not jobs:
        try:
            page = await _http_text(f"https://jobs.polymer.co/{token}")
            for url, title in _anchor_jobs(page, rf"(?:https://jobs\.polymer\.co)?/{_re.escape(token)}/[A-Za-z0-9_-]+", base_url="https://jobs.polymer.co")[:max_jobs]:
                jobs.append(_simple_jobpost(
                    ats="polymer", source=JobSource.POLYMER, board_token=token,
                    title=title, job_url=url, source_job_id=url.rsplit("/", 1)[-1],
                ))
        except Exception as exc:
            logger.warning("Polymer %r: %s", token, exc)
            return []
    logger.info("Polymer %r: normalized %s jobs", token, len(jobs))
    return jobs


# ─── Jobvite ─────────────────────────────────────────────────────────────────

async def scrape_jobvite_board(board_token: str, *, max_jobs: int = 2000) -> list[JobPost]:
    """Jobvite hosted boards render server-side; extract /{token}/job/{id} anchors.

    Board page: https://jobs.jobvite.com/{token}
    """
    token = board_token.strip()
    if not token:
        return []
    jobs: list[JobPost] = []
    try:
        page = await _http_text(f"https://jobs.jobvite.com/{token}/search?c=&q=")
    except Exception:
        try:
            page = await _http_text(f"https://jobs.jobvite.com/{token}")
        except Exception as exc:
            logger.warning("Jobvite %r: %s", token, exc)
            return []
    pairs = _anchor_jobs(
        page,
        rf"(?:https://jobs\.jobvite\.com)?/{_re.escape(token)}/job/[A-Za-z0-9_-]+",
        base_url="https://jobs.jobvite.com",
    )
    for url, title in pairs[:max_jobs]:
        jobs.append(_simple_jobpost(
            ats="jobvite", source=JobSource.JOBVITE, board_token=token,
            title=title, job_url=url, source_job_id=url.rsplit("/", 1)[-1],
        ))
    logger.info("Jobvite %r: normalized %s jobs", token, len(jobs))
    return jobs


# ─── iCIMS ───────────────────────────────────────────────────────────────────

async def scrape_icims_board(board_token: str, *, max_jobs: int = 2000) -> list[JobPost]:
    """iCIMS hosted career portals paginate server-rendered search results.

    Search page: https://careers-{token}.icims.com/jobs/search?ss=1&in_iframe=1&pr={page}
    """
    token = board_token.strip()
    if not token:
        return []
    base = f"https://careers-{token}.icims.com"
    jobs: list[JobPost] = []
    seen_urls: set[str] = set()
    for page_num in range(0, 40):  # 40 pages ≈ 800+ postings, plenty per portal
        try:
            page = await _http_text(
                f"{base}/jobs/search",
                params={"ss": "1", "in_iframe": "1", "pr": str(page_num)},
            )
        except Exception as exc:
            if page_num == 0:
                logger.warning("iCIMS %r: %s", token, exc)
                return []
            break
        pairs = _anchor_jobs(page, rf"(?:{_re.escape(base)})?/jobs/\d+/[^\"']+/job[^\"']*", base_url=base)
        new = [(u, t) for u, t in pairs if u not in seen_urls]
        if not new:
            break
        for url, title in new:
            seen_urls.add(url)
            id_match = _re.search(r"/jobs/(\d+)/", url)
            jobs.append(_simple_jobpost(
                ats="icims", source=JobSource.ICIMS, board_token=token,
                title=title, job_url=url.split("?")[0],
                source_job_id=id_match.group(1) if id_match else "",
            ))
            if len(jobs) >= max_jobs:
                break
        if len(jobs) >= max_jobs:
            break
    logger.info("iCIMS %r: normalized %s jobs", token, len(jobs))
    return jobs


# ─── Oracle Recruiting Cloud (ORC) ───────────────────────────────────────────

async def scrape_oracle_board(board_token: str | tuple[str, str], *, max_jobs: int = 2000) -> list[JobPost]:
    """Oracle Recruiting Cloud CandidateExperience public REST API.

    board_token: (host, siteNumber) tuple or "host|siteNumber" string,
    e.g. ("acme.fa.us2.oraclecloud.com", "CX_1").
    Endpoint: https://{host}/hcmRestApi/resources/latest/recruitingCEJobRequisitions
    """
    if isinstance(board_token, (tuple, list)):
        host, site = (str(board_token[0]).strip(), str(board_token[1]).strip())
    else:
        parts = str(board_token).replace(",", "|").split("|")
        host = parts[0].strip()
        site = parts[1].strip() if len(parts) > 1 else "CX_1"
    if not host:
        return []
    host = host.replace("https://", "").rstrip("/")
    jobs: list[JobPost] = []
    offset = 0
    page_size = 100
    while len(jobs) < max_jobs:
        finder = (
            f"findReqs;siteNumber={site},limit={page_size},offset={offset},"
            "sortBy=POSTING_DATES_DESC"
        )
        try:
            payload = await _http_json(
                f"https://{host}/hcmRestApi/resources/latest/recruitingCEJobRequisitions",
                params={"onlyData": "true", "finder": finder},
            )
        except Exception as exc:
            if offset == 0:
                logger.warning("Oracle ORC %r: %s", host, exc)
                return []
            break
        items = payload.get("items") if isinstance(payload, dict) else None
        req_list = (items[0].get("requisitionList") if items and isinstance(items[0], dict) else None) or []
        if not req_list:
            break
        for item in req_list:
            try:
                title = _safe_str(item.get("Title"))
                req_id = _safe_str(item.get("Id"))
                if not title or not req_id:
                    continue
                location = _safe_str(item.get("PrimaryLocation"))
                jobs.append(_simple_jobpost(
                    ats="oracle_recruiting", source=JobSource.ORACLE_RECRUITING, board_token=host,
                    title=title,
                    job_url=f"https://{host}/hcmUI/CandidateExperience/en/sites/{site}/job/{req_id}",
                    location=location,
                    description=_strip_html(item.get("ShortDescriptionStr") or item.get("ExternalDescriptionStr")),
                    source_job_id=req_id,
                    posted_at=_parse_dt(item.get("PostedDate")),
                    extra={"site": site, "secondary_locations": _location_name(item.get("secondaryLocations"))},
                ))
            except Exception as exc:  # noqa: BLE001
                logger.debug("Oracle ORC: skip row: %s", exc)
        if len(req_list) < page_size:
            break
        offset += page_size
    logger.info("Oracle ORC %r: normalized %s jobs", host, len(jobs))
    return jobs


# ─── Paylocity ───────────────────────────────────────────────────────────────

async def scrape_paylocity_board(board_token: str, *, max_jobs: int = 2000) -> list[JobPost]:
    """Public feed: https://recruiting.paylocity.com/recruiting/v2/api/feed/jobs/{companyId}"""
    token = board_token.strip()
    if not token:
        return []
    try:
        payload = await _http_json(f"https://recruiting.paylocity.com/recruiting/v2/api/feed/jobs/{token}")
    except Exception as exc:
        logger.warning("Paylocity %r: %s", token, exc)
        return []
    items = payload.get("jobs") if isinstance(payload, dict) else payload
    if not isinstance(items, list):
        return []
    jobs: list[JobPost] = []
    for item in items[:max_jobs]:
        try:
            title = _safe_str(item.get("title") or item.get("jobTitle") or item.get("positionTitle"))
            if not title:
                continue
            job_id_n = _safe_str(item.get("jobId") or item.get("id"))
            jobs.append(_simple_jobpost(
                ats="paylocity", source=JobSource.PAYLOCITY, board_token=token,
                title=title,
                job_url=_safe_str(item.get("applyUrl") or item.get("jobUrl"))
                        or f"https://recruiting.paylocity.com/recruiting/jobs/Details/{job_id_n}",
                location=_location_name(item.get("location") or item.get("locationName")),
                description=_strip_html(item.get("description") or item.get("jobDescription")),
                source_job_id=job_id_n,
                posted_at=_parse_dt(item.get("publishedDate") or item.get("datePosted")),
                job_type=_safe_str(item.get("employmentType")),
            ))
        except Exception as exc:  # noqa: BLE001
            logger.debug("Paylocity: skip row: %s", exc)
    logger.info("Paylocity %r: normalized %s jobs", token, len(jobs))
    return jobs


# ─── UKG Pro / UltiPro Recruiting ────────────────────────────────────────────

async def scrape_ukg_board(board_token: str, *, max_jobs: int = 2000) -> list[JobPost]:
    """UKG job boards expose a POST search endpoint used by their own UI.

    board_token: the board path, e.g. "COMPA123COMP/JobBoard/11111111-2222-...".
    Endpoint: https://recruiting.ultipro.com/{token}/JobBoardView/LoadSearchResults
    """
    token = board_token.strip().strip("/")
    if not token:
        return []
    body = {
        "opportunitySearch": {
            "Top": min(max_jobs, 1000),
            "Skip": 0,
            "QueryString": "",
            "OrderBy": [{"Value": "postedDateDesc", "PropertyName": "PostedDate", "Ascending": False}],
            "Filters": [],
        },
        "matchCriteria": {
            "PreferredJobs": [], "Educations": [], "LicenseAndCertifications": [],
            "Skills": [], "hasNoLicenses": False, "SkippedSkills": [],
        },
    }
    try:
        payload = await _http_json(
            f"https://recruiting.ultipro.com/{token}/JobBoardView/LoadSearchResults",
            method="POST", json_body=body,
        )
    except Exception as exc:
        logger.warning("UKG %r: %s", token, exc)
        return []
    items = payload.get("opportunities") if isinstance(payload, dict) else None
    if not isinstance(items, list):
        return []
    jobs: list[JobPost] = []
    for item in items[:max_jobs]:
        try:
            title = _safe_str(item.get("Title"))
            if not title:
                continue
            locations = item.get("Locations") or []
            loc_parts = []
            for loc in locations:
                addr = (loc or {}).get("Address") or {}
                city = _safe_str((addr.get("City") or ""))
                state = _safe_str(((addr.get("State") or {}).get("Code") if isinstance(addr.get("State"), dict) else addr.get("State")))
                country = _safe_str(((addr.get("Country") or {}).get("Code") if isinstance(addr.get("Country"), dict) else addr.get("Country")))
                loc_parts.append(", ".join(p for p in (city, state, country) if p))
            link = _safe_str(item.get("Link"))
            jobs.append(_simple_jobpost(
                ats="ukg", source=JobSource.UKG, board_token=token.split("/")[0],
                title=title,
                job_url=link or f"https://recruiting.ultipro.com/{token}/OpportunityDetail?opportunityId={_safe_str(item.get('Id'))}",
                location="; ".join(p for p in loc_parts if p),
                description=_strip_html(item.get("BriefDescription") or item.get("Description")),
                source_job_id=_safe_str(item.get("Id") or item.get("RequisitionNumber")),
                posted_at=_parse_dt(item.get("PostedDate")),
                job_type=_safe_str(item.get("FullTime")),
                extra={"requisition_number": _safe_str(item.get("RequisitionNumber"))},
            ))
        except Exception as exc:  # noqa: BLE001
            logger.debug("UKG: skip row: %s", exc)
    logger.info("UKG %r: normalized %s jobs", token, len(jobs))
    return jobs


# ─── Zoho Recruit ────────────────────────────────────────────────────────────

async def scrape_zoho_recruit_board(board_token: str, *, max_jobs: int = 2000) -> list[JobPost]:
    """Zoho Recruit hosted careers pages are server-rendered.

    Board page: https://{token}.zohorecruit.com/jobs/Careers
    """
    token = board_token.strip()
    if not token:
        return []
    base = f"https://{token}.zohorecruit.com"
    try:
        page = await _http_text(f"{base}/jobs/Careers")
    except Exception as exc:
        logger.warning("Zoho Recruit %r: %s", token, exc)
        return []
    jobs: list[JobPost] = []
    pairs = _anchor_jobs(page, rf"(?:{_re.escape(base)})?/jobs/Careers/\d+[^\"']*", base_url=base)
    for url, title in pairs[:max_jobs]:
        id_match = _re.search(r"/jobs/Careers/(\d+)", url)
        jobs.append(_simple_jobpost(
            ats="zoho_recruit", source=JobSource.ZOHO_RECRUIT, board_token=token,
            title=title, job_url=url,
            source_job_id=id_match.group(1) if id_match else "",
        ))
    logger.info("Zoho Recruit %r: normalized %s jobs", token, len(jobs))
    return jobs


# ─── ADP Workforce Now ───────────────────────────────────────────────────────

async def scrape_adp_board(board_token: str, *, max_jobs: int = 2000) -> list[JobPost]:
    """ADP WFN career centers expose a public job-requisitions JSON feed.

    board_token: the cid GUID from the careers URL
    (workforcenow.adp.com/mascsr/default/mdf/recruitment/recruitment.html?cid={cid}).
    """
    token = board_token.strip()
    if not token:
        return []
    try:
        payload = await _http_json(
            "https://workforcenow.adp.com/mascsr/default/careercenter/public/events/staffing/v1/job-requisitions",
            params={"cid": token, "timeStamp": str(int(datetime.utcnow().timestamp() * 1000)),
                    "lang": "en_US", "ccId": "19000101_000001", "locale": "en_US",
                    "$top": str(min(max_jobs, 500)), "$skip": "0"},
        )
    except Exception as exc:
        logger.warning("ADP %r: %s", token, exc)
        return []
    items = payload.get("jobRequisitions") if isinstance(payload, dict) else None
    if not isinstance(items, list):
        return []
    jobs: list[JobPost] = []
    for item in items[:max_jobs]:
        try:
            title = _safe_str(item.get("requisitionTitle") or (item.get("job") or {}).get("jobTitle"))
            if not title:
                continue
            req_id = _safe_str(item.get("itemID") or (item.get("requisitionID") or ""))
            locs = item.get("requisitionLocations") or []
            loc_parts = []
            for loc in locs:
                name = ((loc or {}).get("nameCode") or {}).get("shortName") or _location_name(loc)
                if name:
                    loc_parts.append(_safe_str(name))
            jobs.append(_simple_jobpost(
                ats="adp", source=JobSource.ADP, board_token=token,
                title=title,
                job_url=(
                    "https://workforcenow.adp.com/mascsr/default/mdf/recruitment/recruitment.html"
                    f"?cid={token}&jobId={req_id}&lang=en_US&source=CC2"
                ),
                location="; ".join(loc_parts),
                description=_strip_html(item.get("requisitionDescription")),
                source_job_id=req_id,
                posted_at=_parse_dt(item.get("postDate")),
            ))
        except Exception as exc:  # noqa: BLE001
            logger.debug("ADP: skip row: %s", exc)
    logger.info("ADP %r: normalized %s jobs", token, len(jobs))
    return jobs


# ─── Dover ───────────────────────────────────────────────────────────────────

async def scrape_dover_board(board_token: str, *, max_jobs: int = 2000) -> list[JobPost]:
    """Dover careers pages: JSON API first, HTML fallback.

    API:  https://app.dover.io/api/v1/careers-page/{token}/jobs
    Page: https://app.dover.io/{token}/careers
    """
    token = board_token.strip()
    if not token:
        return []
    jobs: list[JobPost] = []
    try:
        payload = await _http_json(f"https://app.dover.io/api/v1/careers-page/{token}/jobs")
        items = payload.get("results") or payload.get("jobs") or payload.get("data") if isinstance(payload, dict) else payload
        if isinstance(items, list):
            for item in items[:max_jobs]:
                title = _safe_str(item.get("title") or item.get("name"))
                if not title:
                    continue
                job_id_n = _safe_str(item.get("id"))
                jobs.append(_simple_jobpost(
                    ats="dover", source=JobSource.DOVER, board_token=token,
                    title=title,
                    job_url=_safe_str(item.get("url")) or f"https://app.dover.io/apply/{token}/{job_id_n}",
                    location=_location_name(item.get("location") or item.get("locations")),
                    source_job_id=job_id_n,
                ))
    except Exception as exc:
        logger.debug("Dover JSON %r failed (%s); falling back to HTML", token, exc)
    if not jobs:
        try:
            page = await _http_text(f"https://app.dover.io/{token}/careers")
            for url, title in _anchor_jobs(page, r"(?:https://app\.dover\.io)?/apply/[^\"']+", base_url="https://app.dover.io")[:max_jobs]:
                jobs.append(_simple_jobpost(
                    ats="dover", source=JobSource.DOVER, board_token=token,
                    title=title, job_url=url, source_job_id=url.rsplit("/", 1)[-1],
                ))
        except Exception as exc:
            logger.warning("Dover %r: %s", token, exc)
            return []
    logger.info("Dover %r: normalized %s jobs", token, len(jobs))
    return jobs


# ─── Gem ─────────────────────────────────────────────────────────────────────

async def scrape_gem_board(board_token: str, *, max_jobs: int = 2000) -> list[JobPost]:
    """Gem hosted job boards (jobs.gem.com/{token}) — anchor extraction."""
    token = board_token.strip()
    if not token:
        return []
    try:
        page = await _http_text(f"https://jobs.gem.com/{token}")
    except Exception as exc:
        logger.warning("Gem %r: %s", token, exc)
        return []
    jobs: list[JobPost] = []
    pairs = _anchor_jobs(
        page,
        rf"(?:https://jobs\.gem\.com)?/{_re.escape(token)}/[A-Za-z0-9=_-]{{8,}}",
        base_url="https://jobs.gem.com",
    )
    for url, title in pairs[:max_jobs]:
        jobs.append(_simple_jobpost(
            ats="gem", source=JobSource.GEM, board_token=token,
            title=title, job_url=url, source_job_id=url.rsplit("/", 1)[-1],
        ))
    logger.info("Gem %r: normalized %s jobs", token, len(jobs))
    return jobs


# ─── SAP SuccessFactors (Career Site Builder) ────────────────────────────────

async def scrape_successfactors_board(board_token: str, *, max_jobs: int = 2000) -> list[JobPost]:
    """SuccessFactors Career Site Builder sites (e.g. jobs.sap.com) paginate
    server-rendered /search/ pages via the startrow parameter.

    board_token: full base URL of the career site, e.g. "https://jobs.sap.com".
    """
    base = board_token.strip().rstrip("/")
    if not base:
        return []
    if not base.startswith("http"):
        base = f"https://{base}"
    jobs: list[JobPost] = []
    seen_urls: set[str] = set()
    row_re = _re.compile(
        r"<a[^>]+class=\"[^\"]*jobTitle-link[^\"]*\"[^>]+href=\"([^\"]+)\"[^>]*>(.*?)</a>",
        _re.IGNORECASE | _re.DOTALL,
    )
    for startrow in range(0, max_jobs, 25):
        try:
            page = await _http_text(f"{base}/search/", params={"q": "", "startrow": str(startrow)})
        except Exception as exc:
            if startrow == 0:
                logger.warning("SuccessFactors %r: %s", base, exc)
                return []
            break
        found_new = False
        for match in row_re.finditer(page):
            href = match.group(1).strip()
            title = _strip_html(match.group(2))
            if not title:
                continue
            url = href if href.startswith("http") else base + href
            if url in seen_urls:
                continue
            seen_urls.add(url)
            found_new = True
            jobs.append(_simple_jobpost(
                ats="successfactors", source=JobSource.SUCCESSFACTORS,
                board_token=base.replace("https://", "").replace("http://", ""),
                title=title, job_url=url, source_job_id=url.rstrip("/").rsplit("/", 1)[-1],
            ))
            if len(jobs) >= max_jobs:
                break
        if not found_new or len(jobs) >= max_jobs:
            break
    logger.info("SuccessFactors %r: normalized %s jobs", base, len(jobs))
    return jobs


# ─── Phenom ──────────────────────────────────────────────────────────────────

async def scrape_phenom_board(board_token: str, *, max_jobs: int = 2000) -> list[JobPost]:
    """Phenom-powered career sites expose a public jobs JSON used by their SPA.

    board_token: the careers domain, e.g. "careers.example.com".
    Endpoint: https://{domain}/api/apply/v2/jobs?domain={domain}
    """
    domain = board_token.strip().replace("https://", "").replace("http://", "").rstrip("/")
    if not domain:
        return []
    jobs: list[JobPost] = []
    start = 0
    page_size = 100
    while len(jobs) < max_jobs:
        try:
            payload = await _http_json(
                f"https://{domain}/api/apply/v2/jobs",
                params={"domain": domain, "start": str(start), "num": str(page_size)},
            )
        except Exception as exc:
            if start == 0:
                logger.warning("Phenom %r: %s", domain, exc)
                return []
            break
        items = None
        if isinstance(payload, dict):
            items = payload.get("positions") or payload.get("jobs") or (payload.get("data") or {}).get("jobs")
        if not isinstance(items, list) or not items:
            break
        for item in items:
            try:
                title = _safe_str(item.get("name") or item.get("title"))
                if not title:
                    continue
                path = _safe_str(item.get("canonicalPositionUrl") or item.get("externalPath") or item.get("applyUrl"))
                url = path if path.startswith("http") else f"https://{domain}{path}"
                jobs.append(_simple_jobpost(
                    ats="phenom", source=JobSource.PHENOM, board_token=domain,
                    title=title, job_url=url,
                    location=_location_name(item.get("location") or item.get("locations")),
                    description=_strip_html(item.get("description") or item.get("job_description")),
                    source_job_id=_safe_str(item.get("jobId") or item.get("id") or item.get("positionId")),
                    posted_at=_parse_dt(item.get("postedDate") or item.get("t_create")),
                ))
                if len(jobs) >= max_jobs:
                    break
            except Exception as exc:  # noqa: BLE001
                logger.debug("Phenom: skip row: %s", exc)
        if len(items) < page_size:
            break
        start += page_size
    logger.info("Phenom %r: normalized %s jobs", domain, len(jobs))
    return jobs


# ─── Dayforce ────────────────────────────────────────────────────────────────

async def scrape_dayforce_board(board_token: str, *, max_jobs: int = 2000) -> list[JobPost]:
    """Dayforce hosted portals (jobs.dayforcehcm.com/en-US/{token}/CANDIDATEPORTAL).

    The portal SPA reads a JSON feed; we try the feed first and fall back to
    anchor extraction for tenants with server-rendered boards.
    """
    token = board_token.strip().strip("/")
    if not token:
        return []
    parts = token.split("/")
    client_name = parts[0]
    site = parts[1] if len(parts) > 1 else "CANDIDATEPORTAL"
    jobs: list[JobPost] = []
    try:
        payload = await _http_json(
            f"https://jobs.dayforcehcm.com/api/jobposting/en-US/{client_name}/{site}",
            params={"page": "1", "pageSize": str(min(max_jobs, 500))},
        )
        items = payload.get("jobPostings") or payload.get("postings") or payload.get("jobs") if isinstance(payload, dict) else payload
        if isinstance(items, list):
            for item in items[:max_jobs]:
                title = _safe_str(item.get("title") or item.get("jobTitle"))
                if not title:
                    continue
                job_id_n = _safe_str(item.get("id") or item.get("jobPostingId") or item.get("referenceNumber"))
                jobs.append(_simple_jobpost(
                    ats="dayforce", source=JobSource.DAYFORCE, board_token=client_name,
                    title=title,
                    job_url=_safe_str(item.get("jobDetailsUrl"))
                            or f"https://jobs.dayforcehcm.com/en-US/{client_name}/{site}/jobs/{job_id_n}",
                    location=_location_name(item.get("location") or item.get("city")),
                    description=_strip_html(item.get("description")),
                    source_job_id=job_id_n,
                    posted_at=_parse_dt(item.get("datePosted") or item.get("postedDate")),
                ))
    except Exception as exc:
        logger.debug("Dayforce JSON %r failed (%s); falling back to HTML", token, exc)
    if not jobs:
        try:
            page = await _http_text(f"https://jobs.dayforcehcm.com/en-US/{client_name}/{site}")
            pairs = _anchor_jobs(
                page,
                rf"(?:https://jobs\.dayforcehcm\.com)?/en-US/{_re.escape(client_name)}/{_re.escape(site)}/jobs/\d+",
                base_url="https://jobs.dayforcehcm.com",
            )
            for url, title in pairs[:max_jobs]:
                jobs.append(_simple_jobpost(
                    ats="dayforce", source=JobSource.DAYFORCE, board_token=client_name,
                    title=title, job_url=url, source_job_id=url.rsplit("/", 1)[-1],
                ))
        except Exception as exc:
            logger.warning("Dayforce %r: %s", token, exc)
            return []
    logger.info("Dayforce %r: normalized %s jobs", token, len(jobs))
    return jobs


# ─── Join.com ────────────────────────────────────────────────────────────────

async def scrape_join_board(board_token: str, *, max_jobs: int = 2000) -> list[JobPost]:
    """Join.com company pages are server-rendered; extract job anchors.

    Board page: https://join.com/companies/{token}
    """
    token = board_token.strip()
    if not token:
        return []
    try:
        page = await _http_text(f"https://join.com/companies/{token}")
    except Exception as exc:
        logger.warning("Join %r: %s", token, exc)
        return []
    jobs: list[JobPost] = []
    pairs = _anchor_jobs(
        page,
        rf"(?:https://join\.com)?/companies/{_re.escape(token)}/\d+[^\"']*",
        base_url="https://join.com",
    )
    for url, title in pairs[:max_jobs]:
        id_match = _re.search(rf"/companies/{_re.escape(token)}/(\d+)", url)
        jobs.append(_simple_jobpost(
            ats="join", source=JobSource.JOIN_COM, board_token=token,
            title=title, job_url=url,
            source_job_id=id_match.group(1) if id_match else "",
        ))
    logger.info("Join %r: normalized %s jobs", token, len(jobs))
    return jobs


# ─── Hireology ───────────────────────────────────────────────────────────────

async def scrape_hireology_board(board_token: str, *, max_jobs: int = 2000) -> list[JobPost]:
    """Hireology hosted career sites ({token}.hireology.com) — anchor extraction."""
    token = board_token.strip()
    if not token:
        return []
    base = f"https://{token}.hireology.com"
    page = ""
    for candidate in (base, f"{base}/careers"):
        try:
            page = await _http_text(candidate)
            if page:
                break
        except Exception as exc:
            logger.debug("Hireology %r: %s failed: %s", token, candidate, exc)
    if not page:
        logger.warning("Hireology %r: no reachable career page", token)
        return []
    jobs: list[JobPost] = []
    pairs = _anchor_jobs(page, rf"(?:{_re.escape(base)})?/(?:careers|jobs)/[A-Za-z0-9_-]+[^\"']*", base_url=base)
    for url, title in pairs[:max_jobs]:
        jobs.append(_simple_jobpost(
            ats="hireology", source=JobSource.HIREOLOGY, board_token=token,
            title=title, job_url=url, source_job_id=url.rstrip("/").rsplit("/", 1)[-1],
        ))
    logger.info("Hireology %r: normalized %s jobs", token, len(jobs))
    return jobs


# ─── Freshteam (Freshworks) ──────────────────────────────────────────────────

async def scrape_freshteam_board(board_token: str, *, max_jobs: int = 2000) -> list[JobPost]:
    """Public widget feed: https://{token}.freshteam.com/hire/widgets/jobs.json"""
    token = board_token.strip()
    if not token:
        return []
    try:
        payload = await _http_json(f"https://{token}.freshteam.com/hire/widgets/jobs.json")
    except Exception as exc:
        logger.warning("Freshteam %r: %s", token, exc)
        return []
    items = payload.get("jobs") if isinstance(payload, dict) else payload
    if not isinstance(items, list):
        return []
    jobs: list[JobPost] = []
    for item in items[:max_jobs]:
        try:
            title = _safe_str(item.get("title"))
            if not title:
                continue
            branch = item.get("branch") or {}
            loc_parts = [_safe_str(branch.get("city")), _safe_str(branch.get("state")), _safe_str(branch.get("country_code"))]
            jobs.append(_simple_jobpost(
                ats="freshteam", source=JobSource.FRESHTEAM, board_token=token,
                title=title,
                job_url=_safe_str(item.get("url")) or f"https://{token}.freshteam.com/jobs/{_safe_str(item.get('id'))}",
                location=", ".join(p for p in loc_parts if p),
                description=_strip_html(item.get("description")),
                source_job_id=_safe_str(item.get("id")),
                posted_at=_parse_dt(item.get("created_at")),
                job_type=_safe_str(item.get("job_type")),
                extra={"department": _safe_str((item.get("department") or {}).get("name") if isinstance(item.get("department"), dict) else item.get("department")), "remote": item.get("remote")},
            ))
        except Exception as exc:  # noqa: BLE001
            logger.debug("Freshteam: skip row: %s", exc)
    logger.info("Freshteam %r: normalized %s jobs", token, len(jobs))
    return jobs


# ─── Jobylon ─────────────────────────────────────────────────────────────────

async def scrape_jobylon_board(board_token: str, *, max_jobs: int = 2000) -> list[JobPost]:
    """Public JSON feed: https://feed.jobylon.com/feeds/{token}/?format=json"""
    token = board_token.strip()
    if not token:
        return []
    try:
        payload = await _http_json(f"https://feed.jobylon.com/feeds/{token}/", params={"format": "json"})
    except Exception as exc:
        logger.warning("Jobylon %r: %s", token, exc)
        return []
    items = payload if isinstance(payload, list) else (payload.get("jobs") if isinstance(payload, dict) else None)
    if not isinstance(items, list):
        return []
    jobs: list[JobPost] = []
    for item in items[:max_jobs]:
        try:
            title = _safe_str(item.get("title"))
            if not title:
                continue
            locs = item.get("locations") or []
            loc = ""
            if isinstance(locs, list) and locs:
                first = (locs[0] or {}).get("location") or {}
                loc = _safe_str(first.get("text") or first.get("city"))
            company = _safe_str((item.get("company") or {}).get("name") if isinstance(item.get("company"), dict) else "")
            job = _simple_jobpost(
                ats="jobylon", source=JobSource.JOBYLON, board_token=token,
                title=title,
                job_url=_safe_str(item.get("urls", {}).get("ad") if isinstance(item.get("urls"), dict) else item.get("url")),
                location=loc,
                description=_strip_html(item.get("descr") or item.get("description")),
                source_job_id=_safe_str(item.get("id")),
                posted_at=_parse_dt(item.get("from_date") or item.get("created_at")),
                job_type=_safe_str(item.get("employment_type")),
            )
            if company:
                job.company = company
            jobs.append(job)
        except Exception as exc:  # noqa: BLE001
            logger.debug("Jobylon: skip row: %s", exc)
    logger.info("Jobylon %r: normalized %s jobs", token, len(jobs))
    return jobs


# ─── Comeet ──────────────────────────────────────────────────────────────────

async def scrape_comeet_board(board_token: str, *, max_jobs: int = 2000) -> list[JobPost]:
    """Comeet hosted careers pages (www.comeet.com/jobs/{token}) — anchors."""
    token = board_token.strip()
    if not token:
        return []
    try:
        page = await _http_text(f"https://www.comeet.com/jobs/{token}")
    except Exception as exc:
        logger.warning("Comeet %r: %s", token, exc)
        return []
    jobs: list[JobPost] = []
    pairs = _anchor_jobs(
        page,
        rf"(?:https://www\.comeet\.com)?/jobs/{_re.escape(token)}/[A-Za-z0-9._-]+",
        base_url="https://www.comeet.com",
    )
    for url, title in pairs[:max_jobs]:
        jobs.append(_simple_jobpost(
            ats="comeet", source=JobSource.COMEET, board_token=token,
            title=title, job_url=url, source_job_id=url.rsplit("/", 1)[-1],
        ))
    logger.info("Comeet %r: normalized %s jobs", token, len(jobs))
    return jobs


# ─── Homerun ─────────────────────────────────────────────────────────────────

async def scrape_homerun_board(board_token: str, *, max_jobs: int = 2000) -> list[JobPost]:
    """Homerun hosted career sites ({token}.homerun.co) — anchor extraction."""
    token = board_token.strip()
    if not token:
        return []
    base = f"https://{token}.homerun.co"
    try:
        page = await _http_text(base)
    except Exception as exc:
        logger.warning("Homerun %r: %s", token, exc)
        return []
    jobs: list[JobPost] = []
    pairs = _anchor_jobs(page, rf"(?:{_re.escape(base)})?/[a-z0-9-]{{6,}}(?:/[a-z]{{2}})?", base_url=base)
    for url, title in pairs[:max_jobs]:
        slug = url.rstrip("/").rsplit("/", 1)[-1]
        if slug in {"privacy", "terms", "about", "contact", "jobs"}:
            continue
        jobs.append(_simple_jobpost(
            ats="homerun", source=JobSource.HOMERUN, board_token=token,
            title=title, job_url=url, source_job_id=slug,
        ))
    logger.info("Homerun %r: normalized %s jobs", token, len(jobs))
    return jobs


# ─── CATS (catsone) ──────────────────────────────────────────────────────────

async def scrape_catsone_board(board_token: str, *, max_jobs: int = 2000) -> list[JobPost]:
    """CATS hosted career portals ({token}.catsone.com/careers) — anchors."""
    token = board_token.strip()
    if not token:
        return []
    base = f"https://{token}.catsone.com"
    try:
        page = await _http_text(f"{base}/careers")
    except Exception as exc:
        logger.warning("CATS %r: %s", token, exc)
        return []
    jobs: list[JobPost] = []
    pairs = _anchor_jobs(page, rf"(?:{_re.escape(base)})?/careers/[^\"']+", base_url=base)
    for url, title in pairs[:max_jobs]:
        jobs.append(_simple_jobpost(
            ats="catsone", source=JobSource.CATSONE, board_token=token,
            title=title, job_url=url, source_job_id=url.rstrip("/").rsplit("/", 1)[-1],
        ))
    logger.info("CATS %r: normalized %s jobs", token, len(jobs))
    return jobs


# ─── Multi-ATS dispatcher ────────────────────────────────────────────────────

ATS_DISPATCH = {
    "greenhouse": scrape_greenhouse_board,
    "lever": scrape_lever_board,
    "ashby": scrape_ashby_board,
    "smartrecruiters": scrape_smartrecruiters_board,
    "recruitee": scrape_recruitee_board,
    "personio": scrape_personio_board,
    "teamtailor": scrape_teamtailor_board,
    "jazzhr": scrape_jazzhr_board,
    "rippling": scrape_rippling_board,
    "bamboohr": scrape_bamboohr_board,
    "workable": scrape_workable_board,
    # Extended coverage
    "breezyhr": scrape_breezyhr_board,
    "breezy": scrape_breezyhr_board,
    "pinpoint": scrape_pinpoint_board,
    "polymer": scrape_polymer_board,
    "jobvite": scrape_jobvite_board,
    "icims": scrape_icims_board,
    "paylocity": scrape_paylocity_board,
    "ukg": scrape_ukg_board,
    "ultipro": scrape_ukg_board,
    "zoho_recruit": scrape_zoho_recruit_board,
    "zoho": scrape_zoho_recruit_board,
    "adp": scrape_adp_board,
    "dover": scrape_dover_board,
    "gem": scrape_gem_board,
    "successfactors": scrape_successfactors_board,
    "sap_successfactors": scrape_successfactors_board,
    "phenom": scrape_phenom_board,
    "eightfold": scrape_phenom_board,  # same /api/apply/v2/jobs pattern
    "dayforce": scrape_dayforce_board,
    "join": scrape_join_board,
    "hireology": scrape_hireology_board,
    # 2026-07-11 additions
    "freshteam": scrape_freshteam_board,
    "jobylon": scrape_jobylon_board,
    "comeet": scrape_comeet_board,
    "homerun": scrape_homerun_board,
    "catsone": scrape_catsone_board,
    "cats": scrape_catsone_board,
}


async def scrape_ats(
    ats_name: str,
    board_token: str | tuple[str, str],
    *,
    max_jobs: int = 2000,
    base_host: str = "wd5.myworkdayjobs.com",
) -> list[JobPost]:
    """Dispatch to the appropriate ATS scraper.

    For Workday, board_token must be a 2-tuple of (tenant, site).
    For Oracle Recruiting, board_token is (host, siteNumber) or "host|siteNumber".
    For all other ATS, board_token is a string.
    """
    name = ats_name.lower().strip()
    if name == "workday":
        if not isinstance(board_token, (tuple, list)) or len(board_token) != 2:
            logger.warning("Workday board_token must be (tenant, site); got %r", board_token)
            return []
        tenant, site = board_token
        return await scrape_workday_board(tenant=tenant, site=site, base_host=base_host, max_jobs=max_jobs)
    if name in {"oracle", "oracle_recruiting", "orc"}:
        return await scrape_oracle_board(board_token, max_jobs=max_jobs)

    fn = ATS_DISPATCH.get(name)
    if not fn:
        logger.warning("Unknown ATS %r", ats_name)
        return []
    return await fn(board_token=board_token, max_jobs=max_jobs)


SUPPORTED_ATS: frozenset[str] = frozenset(ATS_DISPATCH) | {"workday", "oracle", "oracle_recruiting", "orc"}

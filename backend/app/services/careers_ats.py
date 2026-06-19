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
    For all other ATS, board_token is a string.
    """
    name = ats_name.lower().strip()
    if name == "workday":
        if not isinstance(board_token, (tuple, list)) or len(board_token) != 2:
            logger.warning("Workday board_token must be (tenant, site); got %r", board_token)
            return []
        tenant, site = board_token
        return await scrape_workday_board(tenant=tenant, site=site, base_host=base_host, max_jobs=max_jobs)

    fn = ATS_DISPATCH.get(name)
    if not fn:
        logger.warning("Unknown ATS %r", ats_name)
        return []
    return await fn(board_token=board_token, max_jobs=max_jobs)

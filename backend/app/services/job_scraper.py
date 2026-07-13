"""
PlaceUp Career — Job Scraping Service
Multi-source job scraping using JobSpy, USAJobs API, and LinkedIn RapidAPI.

Sources:
1. JobSpy (python-jobspy) — LinkedIn, Indeed, Glassdoor, ZipRecruiter, Google
2. USAJobs API — Government jobs (free, no rate limit)
3. LinkedIn Job Search RapidAPI — Additional LinkedIn coverage

Inspired by: github.com/speedyapply/JobSpy, github.com/PaulMcInnis/JobFunnel
"""

import asyncio
import logging
import os
import time
from datetime import datetime
from typing import Optional

import httpx
import pandas as pd

from app.config import settings
from app.models.job import (
    JobPost, JobSource, JobCategory, SalaryRange, VisaBadges,
    ScrapeRequest, ScrapeResult,
)
from app.utils.deduplication import generate_content_hash, generate_job_id, is_near_duplicate
from app.services.visa_classifier import classify_job
from app.services.careers_ats import scrape_greenhouse_board
from app.services.dice_scraper import scrape_dice
from app.services.h1b_sponsor_pipeline import scrape_h1b_sponsor_boards
from app.services.job_description_details import (
    DEFAULT_HEADERS,
    clean_description_text,
    fetch_full_job_description,
    is_html_fetch_allowed,
)
from app.services.global_visa_rules import resolve_country
from app.utils.job_quality import has_complete_job_description
from app.services.scrapling_job_discovery import (
    build_scrapling_targets,
    scrape_scrapling_targets,
)
from app.utils.terminal_table import render_table

logger = logging.getLogger(__name__)

_rapidapi_disabled_until = 0.0
_provider_disabled_until: dict[str, float] = {}
_provider_empty_streaks: dict[str, int] = {}


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


RAPIDAPI_REQUEST_DELAY_SECONDS = _env_float("RAPIDAPI_REQUEST_DELAY_SECONDS", 3.0)
RAPIDAPI_RATE_LIMIT_COOLDOWN_SECONDS = _env_float("RAPIDAPI_RATE_LIMIT_COOLDOWN_SECONDS", 900.0)
PROVIDER_BLOCK_COOLDOWN_SECONDS = _env_float("SCRAPER_PROVIDER_BLOCK_COOLDOWN_SECONDS", 1800.0)


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


PROVIDER_EMPTY_CIRCUIT_THRESHOLD = max(
    1,
    _env_int("SCRAPER_PROVIDER_EMPTY_CIRCUIT_THRESHOLD", 4),
)
BLOCK_PRONE_JOBSPY_SOURCES = {"google", "glassdoor", "zip_recruiter"}


def _normalize_source_name(source: str) -> str:
    """Normalize source labels so metrics and logs stay consistent."""
    return source.strip().lower().replace("-", "_")


def _provider_circuit_open(source: str) -> bool:
    until = _provider_disabled_until.get(_normalize_source_name(source), 0.0)
    return time.monotonic() < until


def _provider_circuit_remaining(source: str) -> int:
    until = _provider_disabled_until.get(_normalize_source_name(source), 0.0)
    return max(0, int(until - time.monotonic()))


def _open_provider_circuit(source: str, reason: str) -> None:
    normalized = _normalize_source_name(source)
    _provider_disabled_until[normalized] = time.monotonic() + PROVIDER_BLOCK_COOLDOWN_SECONDS
    logger.warning(
        "%s provider circuit opened for %ss: %s",
        normalized,
        int(PROVIDER_BLOCK_COOLDOWN_SECONDS),
        reason,
    )


def _close_unawaited(awaitable_job) -> None:
    close = getattr(awaitable_job, "close", None)
    if callable(close):
        close()


def _looks_like_provider_block(exc: Exception) -> bool:
    text = str(exc).lower()
    block_markers = (
        "429",
        "403",
        "too many requests",
        "forbidden",
        "cf-waf",
        "cloudflare",
        "/sorry/",
        "captcha",
        "rate limit",
        "responseerror",
    )
    return any(marker in text for marker in block_markers)


def _record_provider_result(source: str, count: int) -> None:
    normalized = _normalize_source_name(source)
    if normalized not in BLOCK_PRONE_JOBSPY_SOURCES:
        return
    if count > 0:
        _provider_empty_streaks[normalized] = 0
        return
    streak = _provider_empty_streaks.get(normalized, 0) + 1
    _provider_empty_streaks[normalized] = streak
    if streak >= PROVIDER_EMPTY_CIRCUIT_THRESHOLD and not _provider_circuit_open(normalized):
        _open_provider_circuit(
            normalized,
            f"{streak} consecutive empty responses from a block-prone public provider",
        )


def _resolve_greenhouse_tokens(request: ScrapeRequest) -> list[str]:
    tokens = [token.strip() for token in request.greenhouse_board_tokens if token.strip()]
    if not tokens and settings.greenhouse_board_tokens.strip():
        tokens = [token.strip() for token in settings.greenhouse_board_tokens.split(",") if token.strip()]
    return tokens


# ─── JobSpy Scraper ───────────────────────────────────────────

async def scrape_jobspy(
    search_term: str,
    location: str = "United States",
    results_wanted: int = 50,
    hours_old: Optional[int] = 72,
    site_names: Optional[list[str]] = None,
    page_size: int = 35,
    max_pages: int = 15,
    proxies: Optional[list[str]] = None,
) -> list[JobPost]:
    """Scrape jobs using python-jobspy library.

    JobSpy supports concurrent scraping from:
    - LinkedIn, Indeed, Glassdoor, ZipRecruiter, Google

    Args:
        search_term: Job title or keyword to search
        location: Geographic location filter
        results_wanted: Maximum results per source
        hours_old: Maximum age of postings in hours
        site_names: Which sites to scrape (default: all)

    Returns:
        List of normalized JobPost objects
    """
    if site_names:
        source_name = _normalize_source_name(site_names[0])
        if _provider_circuit_open(source_name):
            logger.info(
                "JobSpy: skipping %s for %ss because provider circuit is open",
                source_name,
                _provider_circuit_remaining(source_name),
            )
            return []

    try:
        from jobspy import scrape_jobs as jobspy_scrape

        for noisy_logger in (
            "JobSpy",
            "JobSpy:Google",
            "JobSpy:LinkedIn",
            "JobSpy:Indeed",
            "JobSpy:Glassdoor",
            "JobSpy:ZipRecruiter",
        ):
            logging.getLogger(noisy_logger).setLevel(logging.CRITICAL)

        if site_names is None:
            site_names = ["indeed", "linkedin", "glassdoor", "zip_recruiter", "google"]

        logger.info(f"JobSpy: Scraping '{search_term}' from {site_names} (paginated up to {results_wanted})")

        # Run blocking scrape in thread pool (JobSpy honors offset for paging)
        loop = asyncio.get_event_loop()
        jobs: list[JobPost] = []
        offset = 0
        pages = 0

        indeed_country = _jobspy_indeed_country(location)
        scrape_kwargs = dict(
            site_name=site_names,
            search_term=search_term,
            location=location,
            country_indeed=indeed_country,
            linkedin_fetch_description=True,
            verbose=0,
        )
        proxy_list = proxies or ([settings.proxy_url] if settings.proxy_url else None)
        if hours_old is not None:
            scrape_kwargs["hours_old"] = hours_old
        if proxy_list:
            scrape_kwargs["proxies"] = proxy_list

        while len(jobs) < results_wanted and pages < max_pages:
            chunk = min(page_size, results_wanted - len(jobs))

            def _run_batch(off: int, want: int) -> pd.DataFrame:
                call_kwargs = scrape_kwargs.copy()
                call_kwargs["results_wanted"] = want
                call_kwargs["offset"] = off
                return jobspy_scrape(**call_kwargs)

            df: pd.DataFrame = await loop.run_in_executor(
                None,
                lambda: _run_batch(offset, chunk),
            )
            pages += 1

            if df is None or df.empty:
                break

            for _, row in df.iterrows():
                try:
                    job = _jobspy_row_to_jobpost(row)
                    if job:
                        extras = job.extra_metadata if isinstance(job.extra_metadata, dict) else {}
                        extras["requested_location"] = location
                        extras["requested_search_term"] = search_term
                        job.extra_metadata = extras
                        jobs.append(job)
                except Exception as e:
                    logger.debug(f"JobSpy: Skipping row due to error: {e}")
                    continue

            got = len(df)
            offset += got
            if got < chunk:
                break

        if not jobs:
            logger.info(f"JobSpy: No results for '{search_term}' on {site_names}")

        if site_names:
            _record_provider_result(site_names[0], len(jobs))

        logger.info(f"JobSpy: Got {len(jobs)} jobs for '{search_term}' from {site_names}")
        return jobs

    except ImportError:
        logger.error("python-jobspy not installed. Run: pip install python-jobspy")
        return []
    except Exception as e:
        if site_names and _looks_like_provider_block(e):
            _open_provider_circuit(site_names[0], str(e))
        logger.info(f"JobSpy provider skipped for {site_names}: {e}")
        return []


def _pandas_scalar_str(value: object, default: str = "") -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return default
    return str(value).strip()


def _pandas_scalar_maybe_int(value: object) -> Optional[int]:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


def _pandas_scalar_maybe_float(value: object) -> Optional[float]:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def _pandas_scalar_maybe_bool(value: object) -> Optional[bool]:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    return bool(value)


def _format_skills_cell(value: object) -> Optional[str]:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, (list, tuple, set)):
        skill_list = [_pandas_scalar_str(s) for s in value if _pandas_scalar_str(s)]
        return ", ".join(skill_list) if skill_list else None
    text = _pandas_scalar_str(value)
    return text or None


def _rapidapi_location_filter(location: str) -> str:
    normalized = (location or "").strip().lower()
    if normalized in {"north america", "north_america", "us canada", "usa canada"}:
        return '"United States" OR "Canada"'
    return f'"{location or "United States"}"'


_INDEED_COUNTRY_BY_CODE = {
    "US": "USA", "GB": "UK", "AE": "United Arab Emirates",
    "CA": "Canada", "IE": "Ireland", "DE": "Germany", "NL": "Netherlands",
    "AU": "Australia", "NZ": "New Zealand", "SG": "Singapore", "JP": "Japan",
    "PT": "Portugal", "FR": "France", "ES": "Spain", "SE": "Sweden",
    "DK": "Denmark", "NO": "Norway", "CH": "Switzerland", "FI": "Finland",
    "BE": "Belgium", "AT": "Austria", "PL": "Poland", "EE": "Estonia",
    "QA": "Qatar", "SA": "Saudi Arabia", "IT": "Italy", "LU": "Luxembourg",
    "KR": "South Korea", "TW": "Taiwan", "HK": "Hong Kong",
    "CZ": "Czech Republic", "IN": "India",
}


def _jobspy_indeed_country(location: str) -> str:
    """Return JobSpy's Indeed market for every supported destination."""
    return _INDEED_COUNTRY_BY_CODE.get(resolve_country(location) or "", "USA")


def _source_supports_location(src: JobSource, location: str) -> bool:
    """Avoid expensive country/source combinations that cannot return jobs."""
    country = resolve_country(location)
    if src in {JobSource.USAJOBS, JobSource.DICE}:
        return country == "US"
    if src == JobSource.ZIPRECRUITER:
        return country in {"US", "CA"}
    return True


def _jobspy_location_for_source(src: JobSource, location: str) -> str:
    normalized = (location or "").strip().lower()
    if src == JobSource.GLASSDOOR and normalized in {"united states", "usa", "us"}:
        return "New York, NY"
    if src == JobSource.GLASSDOOR and normalized == "canada":
        return "Toronto, ON"
    return location


def _parse_datetime_cell(value: object) -> Optional[datetime]:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).strip()
    if not text:
        return None
    try:
        sanitized = text.replace("Z", "+00:00")
        return datetime.fromisoformat(sanitized)
    except ValueError:
        return None


def _jobspy_row_to_jobpost(row: pd.Series) -> Optional[JobPost]:
    """Convert a JobSpy DataFrame row to a JobPost model."""
    title = _pandas_scalar_str(row.get("title"))
    company = _pandas_scalar_str(row.get("company") or row.get("company_name"))
    location = _pandas_scalar_str(row.get("location"))

    if not title or not company:
        return None

    # Parse salary
    salary = None
    min_sal = row.get("min_amount", None)
    max_sal = row.get("max_amount", None)
    if min_sal or max_sal:
        try:
            currency_code = _pandas_scalar_str(row.get("currency")) or "USD"
            salary = SalaryRange(
                min_salary=float(min_sal) if min_sal and pd.notna(min_sal) else None,
                max_salary=float(max_sal) if max_sal and pd.notna(max_sal) else None,
                currency=currency_code,
                period=str(row.get("interval", "yearly")).lower() or "yearly",
            )
        except (ValueError, TypeError):
            pass

    # Determine source
    site = _pandas_scalar_str(row.get("site")).lower()
    source_map = {
        "linkedin": JobSource.LINKEDIN,
        "indeed": JobSource.INDEED,
        "glassdoor": JobSource.GLASSDOOR,
        "zip_recruiter": JobSource.ZIPRECRUITER,
        "google": JobSource.GOOGLE,
    }
    source = source_map.get(site, JobSource.LINKEDIN)

    description = _pandas_scalar_str(row.get("description"))
    job_url = _pandas_scalar_str(row.get("job_url") or row.get("link"))
    job_url_direct = _pandas_scalar_str(row.get("job_url_direct")) or None
    listing_type_val = _pandas_scalar_str(row.get("listing_type")) or None
    salary_src = _pandas_scalar_str(row.get("salary_source")) or None
    emails_raw = row.get("emails")
    extra_jobspy = {
        "experience_range": _pandas_scalar_str(row.get("experience_range")) or None,
        "work_from_home_type": _pandas_scalar_str(row.get("work_from_home_type")) or None,
        "company_addresses": _pandas_scalar_str(row.get("company_addresses")) or None,
        "company_url_direct": _pandas_scalar_str(row.get("company_url_direct")) or None,
        "company_num_employees": _pandas_scalar_str(row.get("company_num_employees")) or None,
        "company_revenue": _pandas_scalar_str(row.get("company_revenue")) or None,
        "vacancy_raw": row.get("vacancy_count"),
    }

    nested_emails = None
    if emails_raw is not None and not (isinstance(emails_raw, float) and pd.isna(emails_raw)):
        nested_emails = emails_raw if isinstance(emails_raw, list) else str(emails_raw)
    extra_jobspy["emails"] = nested_emails
    extra_metadata = {"jobspy": {k: v for k, v in extra_jobspy.items() if v not in (None, "", [])}}

    job_id = generate_job_id(title, company, location)

    return JobPost(
        id=job_id,
        title=title,
        company=company,
        location=location,
        description=description,
        job_url=job_url,
        salary=salary,
        source=source,
        industry=_pandas_scalar_str(row.get("company_industry")) or "",
        posted_at=_parse_datetime_cell(row.get("date_posted")),
        source_job_id=_pandas_scalar_str(row.get("id")),
        job_type=_pandas_scalar_str(row.get("job_type")),
        experience_level=_pandas_scalar_str(row.get("job_level")),
        is_remote=_pandas_scalar_maybe_bool(row.get("is_remote")),
        salary_source=salary_src,
        listing_type=listing_type_val,
        job_function=_pandas_scalar_str(row.get("job_function")) or "",
        vacancy_count=_pandas_scalar_maybe_int(row.get("vacancy_count")),
        skills=_format_skills_cell(row.get("skills")),
        job_url_direct=job_url_direct,
        company_url=_pandas_scalar_str(row.get("company_url")) or "",
        company_logo=_pandas_scalar_str(row.get("company_logo")) or "",
        company_description=_pandas_scalar_str(row.get("company_description")) or "",
        company_rating=_pandas_scalar_maybe_float(row.get("company_rating")),
        company_reviews_count=_pandas_scalar_maybe_int(row.get("company_reviews_count")),
        extra_metadata=extra_metadata if extra_metadata.get("jobspy") else {},
        content_hash=generate_content_hash(title, company, location),
        scraped_at=datetime.utcnow(),
    )


# ─── USAJobs API Scraper ──────────────────────────────────────

async def scrape_usajobs(
    search_term: str,
    location: str = "",
    results_per_page: int = 50,
) -> list[JobPost]:
    """Fetch government jobs from the USAJobs API.

    Free API with generous rate limits. Requires API key and email.
    Endpoint: https://data.usajobs.gov/api/search

    Args:
        search_term: Job keyword to search
        location: City, state, or "United States"
        results_per_page: Max results (up to 500)

    Returns:
        List of normalized JobPost objects
    """
    usajobs_key = (settings.usajobs_api_key or "").strip()
    usajobs_email = (settings.usajobs_email or "").strip()
    if (
        not usajobs_key
        or not usajobs_email
        or "example.com" in usajobs_email.lower()
        or usajobs_key.lower().startswith("your_")
    ):
        logger.info("USAJobs: API key or email not configured")
        return []

    try:
        url = "https://data.usajobs.gov/api/search"
        headers = {
            "Host": "data.usajobs.gov",
            "User-Agent": usajobs_email,
            "Authorization-Key": usajobs_key,
        }
        params = {
            "Keyword": search_term,
            "ResultsPerPage": str(results_per_page),
        }
        normalized_location = (location or "").strip().lower()
        if normalized_location and normalized_location not in {"united states", "usa", "us"}:
            params["LocationName"] = location

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, headers=headers, params=params)
            response.raise_for_status()
            data = response.json()

        results = data.get("SearchResult", {}).get("SearchResultItems", [])
        logger.info(f"USAJobs: Got {len(results)} results for '{search_term}'")

        jobs = []
        for item in results:
            try:
                job = _usajobs_item_to_jobpost(item)
                if job:
                    jobs.append(job)
            except Exception as e:
                logger.debug(f"USAJobs: Skipping item due to error: {e}")
                continue

        return jobs

    except Exception as e:
        logger.error(f"USAJobs API error: {e}")
        return []


def _usajobs_item_to_jobpost(item: dict) -> Optional[JobPost]:
    """Convert a USAJobs API result item to a JobPost model."""
    matched = item.get("MatchedObjectDescriptor", {})
    title = matched.get("PositionTitle", "").strip()
    org = matched.get("OrganizationName", "").strip()

    if not title or not org:
        return None

    # Location
    locations = matched.get("PositionLocation", [])
    location = locations[0].get("LocationName", "") if locations else ""

    # Salary
    salary = None
    remuneration = matched.get("PositionRemuneration", [])
    if remuneration:
        rem = remuneration[0]
        try:
            salary = SalaryRange(
                min_salary=float(rem.get("MinimumRange", 0)),
                max_salary=float(rem.get("MaximumRange", 0)),
                currency="USD",
                period=str(rem.get("RateIntervalCode", "Per Year")).lower(),
            )
        except (ValueError, TypeError):
            pass

    description = matched.get("QualificationSummary", "")
    job_url = matched.get("PositionURI", "")
    job_id = generate_job_id(title, org, location)

    return JobPost(
        id=job_id,
        title=title,
        company=org,
        location=location,
        description=description,
        job_url=job_url,
        salary=salary,
        source=JobSource.USAJOBS,
        source_job_id=matched.get("PositionID", ""),
        category=JobCategory.GOVERNMENT,
        job_type=matched.get("PositionSchedule", [{}])[0].get("Name", "Full-time") if matched.get("PositionSchedule") else "Full-time",
        content_hash=generate_content_hash(title, org, location),
        scraped_at=datetime.utcnow(),
        # Government jobs are inherently visa-friendly for certain categories
        visa=VisaBadges(visa_opt=True, visa_score=40),
    )


# ─── LinkedIn RapidAPI Scraper ─────────────────────────────────

async def scrape_linkedin_rapidapi(
    search_term: str,
    location: str = "United States",
    results_wanted: int = 50,
) -> list[JobPost]:
    """Fetch jobs from LinkedIn via RapidAPI (JSearch / LinkedIn Job Search).

    Uses the LinkedIn Job Search API on RapidAPI.
    Endpoint: linkedin-job-search-api.p.rapidapi.com

    Args:
        search_term: Job keyword to search
        location: Location filter
        results_wanted: Max results

    Returns:
        List of normalized JobPost objects
    """
    global _rapidapi_disabled_until
    rapidapi_key = (settings.rapidapi_key or "").strip()
    if not rapidapi_key or rapidapi_key.lower().startswith("your_"):
        # Missing credentials are permanent for this execution. Opening the
        # circuit prevents every queued role/location task from sleeping and
        # repeating this warning until the Cloud Run deadline is reached.
        _open_provider_circuit("rapidapi", "API key not configured")
        logger.warning("LinkedIn RapidAPI: API key not configured")
        return []
    if _provider_circuit_open("rapidapi"):
        logger.info(
            "LinkedIn RapidAPI: provider circuit open for %ss; skipping",
            _provider_circuit_remaining("rapidapi"),
        )
        return []
    if time.monotonic() < _rapidapi_disabled_until:
        logger.info("LinkedIn RapidAPI: temporarily paused after provider rate limiting")
        return []

    try:
        url = "https://linkedin-job-search-api.p.rapidapi.com/active-jb-24h"
        headers = {
            "x-rapidapi-key": rapidapi_key,
            "x-rapidapi-host": "linkedin-job-search-api.p.rapidapi.com",
        }
        params = {
            "limit": str(min(max(results_wanted, 1), 100)),
            "offset": "0",
            "title_filter": f'"{search_term}"',
            "location_filter": _rapidapi_location_filter(location),
            "description_type": "text",
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, headers=headers, params=params)
            if response.status_code in {403, 429}:
                _rapidapi_disabled_until = time.monotonic() + RAPIDAPI_RATE_LIMIT_COOLDOWN_SECONDS
                _open_provider_circuit("rapidapi", f"HTTP {response.status_code}")
                logger.warning(
                    "LinkedIn RapidAPI returned %s; pausing remaining RapidAPI requests for this run",
                    response.status_code,
                )
                return []
            response.raise_for_status()
            data = response.json()

        results = data if isinstance(data, list) else data.get("results", data.get("data", []))
        logger.info(f"LinkedIn RapidAPI: Got {len(results)} results for '{search_term}'")

        jobs = []
        for item in results[:results_wanted]:
            try:
                job = _rapidapi_item_to_jobpost(item)
                if job:
                    jobs.append(job)
            except Exception as e:
                logger.debug(f"LinkedIn RapidAPI: Skipping item: {e}")
                continue

        return jobs

    except Exception as e:
        logger.warning(f"LinkedIn RapidAPI unavailable: {e}")
        return []


def _rapidapi_item_to_jobpost(item: dict) -> Optional[JobPost]:
    """Convert a LinkedIn RapidAPI result to a JobPost model."""
    title = (item.get("title") or item.get("job_title") or "").strip()
    company = (item.get("company_name") or item.get("company") or "").strip()
    location = (item.get("location") or item.get("job_location") or "").strip()

    if not title or not company:
        return None

    job_id = generate_job_id(title, company, location)
    description = item.get("description") or item.get("job_description") or ""

    return JobPost(
        id=job_id,
        title=title,
        company=company,
        location=location,
        description=description,
        job_url=item.get("linkedin_url") or item.get("url") or "",
        source=JobSource.RAPIDAPI,
        source_job_id=str(item.get("id", "")),
        content_hash=generate_content_hash(title, company, location),
        scraped_at=datetime.utcnow(),
    )


# ─── Orchestrator ──────────────────────────────────────────────

async def run_scrape_cycle(
    request: Optional[ScrapeRequest] = None,
    existing_hashes: Optional[set[str]] = None,
) -> tuple[ScrapeResult, list[JobPost]]:
    """Run a complete scraping cycle across all configured sources.

    This is the main orchestration function that:
    1. Scrapes from all enabled sources in parallel
    2. Deduplicates results
    3. Classifies each job for visa compatibility
    4. Returns normalized, deduplicated, classified jobs

    Args:
        request: Scrape configuration (uses defaults if None)
        existing_hashes: Set of existing content hashes for dedup

    Returns:
        ScrapeResult with all scraped jobs and statistics
    """
    start_time = time.time()
    request = request or ScrapeRequest()
    existing_hashes = existing_hashes or set()

    all_jobs: list[JobPost] = []
    errors: list[str] = []
    sources_used: list[str] = []
    source_attempts: dict[str, int] = {}
    source_scraped: dict[str, int] = {}
    source_errors: dict[str, int] = {}
    google_allowed_terms: set[str] = set()
    if JobSource.GOOGLE in request.sources:
        try:
            from app.job_taxonomy import all_role_names
            google_allowed_terms = {term.lower() for term in all_role_names()}
        except Exception:
            google_allowed_terms = set()

    # Build scraping tasks for all query × source combinations
    tasks: list[tuple[str, asyncio.Future]] = []
    for search_term in request.search_terms:
        for location in request.locations:
            # JobSpy sources (run each source independently for better reliability)
            site_map = {
                JobSource.LINKEDIN: "linkedin",
                JobSource.INDEED: "indeed",
                JobSource.GLASSDOOR: "glassdoor",
                JobSource.ZIPRECRUITER: "zip_recruiter",
                JobSource.GOOGLE: "google",
            }
            for src in request.sources:
                if not _source_supports_location(src, location):
                    continue
                site_name = site_map.get(src)
                if site_name:
                    if src == JobSource.GOOGLE and google_allowed_terms and search_term.lower() not in google_allowed_terms:
                        continue
                    if src == JobSource.ZIPRECRUITER and not settings.scrape_ziprecruiter_jobspy_enabled:
                        continue
                    if src == JobSource.GLASSDOOR and not settings.scrape_glassdoor_jobspy_enabled:
                        continue
                    normalized_source = _normalize_source_name(site_name)
                    source_results_wanted = min(request.results_per_source, 20) if src == JobSource.GOOGLE else request.results_per_source
                    source_page_size = min(request.jobspy_page_size, 10) if src == JobSource.GOOGLE else request.jobspy_page_size
                    source_max_pages = min(request.jobspy_max_pages, 3) if src == JobSource.GOOGLE else request.jobspy_max_pages
                    tasks.append((site_name, scrape_jobspy(
                        search_term=search_term,
                        location=_jobspy_location_for_source(src, location),
                        results_wanted=source_results_wanted,
                        hours_old=request.jobspy_hours_old,
                        site_names=[site_name],
                        page_size=source_page_size,
                        max_pages=source_max_pages,
                    )))
                    sources_used.append(normalized_source)
                    source_attempts[normalized_source] = source_attempts.get(normalized_source, 0) + 1

            # USAJobs
            if JobSource.USAJOBS in request.sources:
                if _source_supports_location(JobSource.USAJOBS, location):
                    tasks.append(("usajobs", scrape_usajobs(
                        search_term=search_term,
                        location=location,
                        results_per_page=request.results_per_source,
                    )))
                    sources_used.append("usajobs")
                    source_attempts["usajobs"] = source_attempts.get("usajobs", 0) + 1

            # LinkedIn RapidAPI
            if JobSource.RAPIDAPI in request.sources:
                tasks.append(("rapidapi", scrape_linkedin_rapidapi(
                    search_term=search_term,
                    location=location,
                    results_wanted=request.results_per_source,
                )))
                sources_used.append("rapidapi")
                source_attempts["rapidapi"] = source_attempts.get("rapidapi", 0) + 1

            # Dice — tech-focused, per query × location
            if JobSource.DICE in request.sources:
                if _source_supports_location(JobSource.DICE, location):
                    tasks.append(("dice", scrape_dice(
                        search_term=search_term,
                        location=location,
                        results_wanted=request.results_per_source,
                    )))
                    sources_used.append("dice")
                    source_attempts["dice"] = source_attempts.get("dice", 0) + 1

    scrapling_requested_sources = {
        JobSource.LINKEDIN,
        JobSource.GLASSDOOR,
        JobSource.ZIPRECRUITER,
        JobSource.MONSTER,
        JobSource.JOOBLE,
        JobSource.SCRAPLING_DISCOVERY,
    }
    if any(src in request.sources for src in scrapling_requested_sources):
        include_discovery = JobSource.SCRAPLING_DISCOVERY in request.sources
        targets = build_scrapling_targets(
            search_terms=request.search_terms,
            locations=request.locations,
            include_glassdoor=JobSource.GLASSDOOR in request.sources and not settings.scrape_glassdoor_jobspy_enabled,
            include_ziprecruiter=JobSource.ZIPRECRUITER in request.sources and not settings.scrape_ziprecruiter_jobspy_enabled,
            include_monster=JobSource.MONSTER in request.sources,
            include_jooble=JobSource.JOOBLE in request.sources,
            include_linkedin=JobSource.LINKEDIN in request.sources,
            include_discovery=include_discovery,
            include_search_pages=include_discovery,
        )
        if targets:
            tasks.append(("scrapling_discovery", scrape_scrapling_targets(targets)))
            sources_used.append("scrapling_discovery")
            source_attempts["scrapling_discovery"] = len(targets)

    clean_source_map = {
        JobSource.REMOTEOK: "remoteok",
        JobSource.REMOTIVE: "remotive",
        JobSource.ARBEITNOW: "arbeitnow",
        JobSource.JOBICY: "jobicy",
        JobSource.WEWORKREMOTELY: "weworkremotely",
        JobSource.JOBTECH: "jobtech",
        JobSource.EURES: "eures",
        JobSource.UK_FIND_A_JOB: "uk_findajob",
        JobSource.NHS_JOBS: "nhs_jobs",
        JobSource.JOBBANK_CA: "jobbank_ca",
        JobSource.BA_JOBSUCHE: "ba_jobsuche",
        JobSource.FRANCE_TRAVAIL: "france_travail",
        JobSource.MYCAREERSFUTURE: "mycareersfuture",
        JobSource.TYOMARKKINATORI: "tyomarkkinatori",
        JobSource.NAV_ARBEIDSPLASSEN: "nav_arbeidsplassen",
    }
    clean_sources = {
        clean_source_map[src]
        for src in request.sources
        if src in clean_source_map
    }
    if clean_sources:
        async def _scrape_clean_sources() -> list[JobPost]:
            from app.etl.sources.global_sources import run_all_clean_sources

            clean_jobs, clean_status = await run_all_clean_sources(
                hours=request.jobspy_hours_old,
                max_jobs_per_source=max(500, request.results_per_source * 10),
                only=clean_sources,
                english_only=True,
                queries=list(request.search_terms or []),
            )
            logger.info("clean_sources status: %s", clean_status)
            return clean_jobs

        tasks.append(("clean_sources", _scrape_clean_sources()))
        sources_used.append("clean_sources")
        source_attempts["clean_sources"] = len(clean_sources)

    greenhouse_tokens = _resolve_greenhouse_tokens(request)
    if JobSource.GREENHOUSE in request.sources:
        if greenhouse_tokens:
            greenhouse_cap = min(8000, max(request.results_per_source * 35, 800))
            for board_token in greenhouse_tokens:
                tasks.append((
                    "greenhouse",
                    scrape_greenhouse_board(board_token, max_jobs=greenhouse_cap),
                ))
                sources_used.append("greenhouse")
                source_attempts["greenhouse"] = source_attempts.get("greenhouse", 0) + 1
        else:
            logger.info(
                "GREENHOUSE not given any explicit board tokens — coverage comes from H1B_SPONSOR pipeline instead."
            )

    # H1B Sponsor pipeline — pulls from every curated H1B sponsor's ATS board
    # (Greenhouse / Lever / Ashby / Workday / SmartRecruiters / Recruitee / Personio /
    #  Teamtailor / JazzHR / Rippling / BambooHR), stamps each role with H1B verification.
    if JobSource.H1B_SPONSOR in request.sources:
        tasks.append((
            "h1b_sponsor",
            scrape_h1b_sponsor_boards(
                tiers=tuple(request.h1b_sponsor_tiers),
                max_jobs_per_sponsor=request.h1b_sponsor_max_jobs,
                concurrency=request.h1b_sponsor_concurrency,
            ),
        ))
        sources_used.append("h1b_sponsor")
        source_attempts["h1b_sponsor"] = source_attempts.get("h1b_sponsor", 0) + 1

    # Execute scrape tasks with a concurrency cap (queries × portals can explode otherwise)
    if tasks:

        concurrency = getattr(settings, "scrape_max_concurrency", None) or 28
        semaphore = asyncio.Semaphore(concurrency)
        rapidapi_semaphore = asyncio.Semaphore(1)
        google_semaphore = asyncio.Semaphore(1)

        async def _guarded_capture(source_tag: str, awaitable_job):
            normalized_tag = _normalize_source_name(source_tag.split(":", 1)[0])
            def _skip_open_circuit():
                _close_unawaited(awaitable_job)
                logger.info(
                    "Scrape task skipped for %s: provider circuit open for %ss",
                    source_tag,
                    _provider_circuit_remaining(normalized_tag),
                )
                return source_tag, [], None

            if _provider_circuit_open(normalized_tag):
                return _skip_open_circuit()
            async with semaphore:
                try:
                    if _provider_circuit_open(normalized_tag):
                        return _skip_open_circuit()

                    def _task_timeout_seconds() -> int:
                        normalized = _normalize_source_name(source_tag.split(":", 1)[0])
                        if normalized in {"h1b_sponsor", "clean_sources"}:
                            return max(settings.scrape_source_timeout_seconds, 7200)
                        return settings.scrape_source_timeout_seconds

                    async def _with_timeout():
                        return await asyncio.wait_for(
                            awaitable_job,
                            timeout=_task_timeout_seconds(),
                        )

                    if _normalize_source_name(source_tag) == "google":
                        async with google_semaphore:
                            if _provider_circuit_open(normalized_tag):
                                return _skip_open_circuit()
                            await asyncio.sleep(2.5)
                            if _provider_circuit_open(normalized_tag):
                                return _skip_open_circuit()
                            outcome = await _with_timeout()
                            if isinstance(outcome, list):
                                _record_provider_result(source_tag, len(outcome))
                            return source_tag, outcome, None
                    if _normalize_source_name(source_tag) == "rapidapi":
                        async with rapidapi_semaphore:
                            if _provider_circuit_open(normalized_tag):
                                return _skip_open_circuit()
                            await asyncio.sleep(RAPIDAPI_REQUEST_DELAY_SECONDS)
                            if _provider_circuit_open(normalized_tag):
                                return _skip_open_circuit()
                            outcome = await _with_timeout()
                            if isinstance(outcome, list):
                                _record_provider_result(source_tag, len(outcome))
                            return source_tag, outcome, None
                    outcome = await _with_timeout()
                    if isinstance(outcome, list):
                        _record_provider_result(source_tag, len(outcome))
                    return source_tag, outcome, None
                except asyncio.TimeoutError as exc:
                    _open_provider_circuit(source_tag, f"timed out after {_task_timeout_seconds()}s")
                    return source_tag, None, TimeoutError(
                        f"timed out after {_task_timeout_seconds()}s"
                    )
                except Exception as exc:
                    if _looks_like_provider_block(exc):
                        _open_provider_circuit(source_tag, str(exc))
                    return source_tag, None, exc

        results = await asyncio.gather(*[
            _guarded_capture(name, coroutine)
            for name, coroutine in tasks
        ])

        for source_name, outcome, fault in results:
            normalized_source = _normalize_source_name(source_name.split(":", 1)[0])
            if fault is not None:
                message = f"{source_name}: {fault}"
                errors.append(message)
                logger.error(f"Scrape task failed: {message}")
                source_errors[normalized_source] = source_errors.get(normalized_source, 0) + 1
            elif isinstance(outcome, list):
                all_jobs.extend(outcome)
                source_scraped[normalized_source] = source_scraped.get(normalized_source, 0) + len(outcome)

    try:
        from app.services.linkedin_job_details import enrich_linkedin_jobs

        await enrich_linkedin_jobs(all_jobs)
    except Exception as exc:
        logger.warning("LinkedIn detail enrichment step skipped: %s", exc)

    await _hydrate_thin_job_descriptions(all_jobs)

    # Deduplicate + target-country scope + years-of-experience tag.
    from app.services.job_filters import is_target_country_scope, parse_years, is_entry_level, is_target_experience
    seen_hashes: set[str] = set(existing_hashes)
    unique_jobs: list[JobPost] = []
    duplicates_skipped = 0
    geo_filtered = 0
    experience_filtered = 0

    for job in all_jobs:
        if job.content_hash in seen_hashes:
            duplicates_skipped += 1
            continue
        # Target-country scope across the configured global country set.
        metadata = getattr(job, "extra_metadata", None) or {}
        requested_location = metadata.get("requested_location", "") if isinstance(metadata, dict) else ""
        geo_text = f"{getattr(job, 'location', '') or ''} {requested_location} {getattr(job, 'title', '') or ''}"
        if not is_target_country_scope(geo_text):
            geo_filtered += 1
            continue
        # Tag years-of-experience heuristic onto the JobPost extras.
        ymin, ymax = parse_years(f"{getattr(job,'title','')}\n{getattr(job,'description','')}")
        if not is_target_experience(getattr(job, "title", "") or "", ymin, ymax, max_years=10):
            experience_filtered += 1
            continue
        try:
            existing_extras = getattr(job, "extra_metadata", None) or {}
            if not isinstance(existing_extras, dict):
                existing_extras = {}
            existing_extras["years_min"] = ymin
            existing_extras["years_max"] = ymax
            existing_extras["entry_level"] = is_entry_level(ymin)
            existing_extras["target_experience"] = True
            existing_extras["target_experience_max_years"] = 10
            job.extra_metadata = existing_extras  # type: ignore[attr-defined]
        except Exception:
            pass
        seen_hashes.add(job.content_hash)
        unique_jobs.append(job)

    if geo_filtered:
        logger.info(f"Geo-filtered {geo_filtered} non-target-country jobs from {len(all_jobs)} scraped")
    if experience_filtered:
        logger.info(f"Experience-filtered {experience_filtered} roles outside 0-10 years from {len(all_jobs)} scraped")

    try:
        from app.services.scrapegraph_enrichment import enrich_jobs_with_scrapegraph

        await enrich_jobs_with_scrapegraph(unique_jobs)
    except Exception as exc:
        logger.warning("ScrapeGraphAI enrichment step skipped: %s", exc)

    # Classify each job for visa compatibility (without downgrading
    # records already stamped by the H1B sponsor pipeline).
    for job in unique_jobs:
        try:
            visa_result = classify_job(
                title=job.title,
                company=job.company,
                description=job.description,
                location=job.location,
                country_code=(job.extra_metadata or {}).get("visa_country") if isinstance(job.extra_metadata, dict) else None,
            )
            existing = job.visa or VisaBadges()
            job.visa = VisaBadges(
                visa_opt=existing.visa_opt or visa_result.visa_opt,
                visa_stem_opt=existing.visa_stem_opt or visa_result.visa_stem_opt,
                visa_h1b=existing.visa_h1b or visa_result.visa_h1b,
                h1b_verified=existing.h1b_verified or visa_result.h1b_verified,
                visa_score=max(existing.visa_score, visa_result.score),
                visa_country=visa_result.country_code,
                visa_country_name=visa_result.country_name,
                visa_programs=visa_result.visa_programs,
                visa_program_names=visa_result.visa_program_names,
                sponsor_verified=existing.h1b_verified or visa_result.sponsor_verified,
                sponsor_source=visa_result.sponsor_source,
                english_friendly=visa_result.english_friendly,
            )
            extras = dict(job.extra_metadata or {})
            extras.update({
                "visa_country": visa_result.country_code,
                "visa_country_name": visa_result.country_name,
                "visa_programs": visa_result.visa_programs,
                "visa_program_names": visa_result.visa_program_names,
                "sponsor_verified": existing.h1b_verified or visa_result.sponsor_verified,
                "sponsor_source": visa_result.sponsor_source,
                "english_friendly": visa_result.english_friendly,
            })
            job.extra_metadata = extras
        except Exception as e:
            logger.debug(f"Visa classification failed for {job.id}: {e}")

    source_unique: dict[str, int] = {}
    for job in unique_jobs:
        normalized_source = _normalize_source_name(job.source.value if hasattr(job.source, "value") else str(job.source))
        source_unique[normalized_source] = source_unique.get(normalized_source, 0) + 1

    all_source_keys = sorted(set(source_attempts) | set(source_scraped) | set(source_unique) | set(source_errors))
    source_breakdown = {
        source: {
            "attempts": source_attempts.get(source, 0),
            "scraped": source_scraped.get(source, 0),
            "unique": source_unique.get(source, 0),
            "errors": source_errors.get(source, 0),
        }
        for source in all_source_keys
    }

    if source_breakdown:
        summary_rows = [
            {
                "source": source,
                "attempts": stats["attempts"],
                "scraped": stats["scraped"],
                "unique": stats["unique"],
                "errors": stats["errors"],
            }
            for source, stats in source_breakdown.items()
        ]
        logger.info("Scrape source summary:\n%s", render_table(summary_rows, headers=["source", "attempts", "scraped", "unique", "errors"]))

    duration = time.time() - start_time

    return ScrapeResult(
        total_scraped=len(all_jobs),
        new_jobs=len(unique_jobs),
        duplicates_skipped=duplicates_skipped,
        errors=errors,
        duration_seconds=round(duration, 2),
        sources_used=list(set(sources_used)),
        source_breakdown=source_breakdown,
    ), unique_jobs


async def _hydrate_thin_job_descriptions(jobs: list[JobPost]) -> None:
    """Fetch every incomplete JD before persistence.

    This intentionally has no per-run candidate cap: completeness is a locked
    publication invariant, not an optional enrichment budget. Failed repairs
    are quarantined by the central loader and never reach the frontend.
    """
    if not jobs:
        return

    concurrency = max(1, _env_int("SCRAPER_JD_HYDRATE_CONCURRENCY", 16))
    timeout = max(8.0, _env_float("SCRAPER_JD_HYDRATE_TIMEOUT_SECONDS", 22.0))

    def _candidate_urls(job: JobPost) -> list[str]:
        seen: set[str] = set()
        urls: list[str] = []

        def add(value: object) -> None:
            url = str(value or "").strip()
            if not url or url in seen or not is_html_fetch_allowed(url):
                return
            seen.add(url)
            urls.append(url)

        add(getattr(job, "job_url_direct", ""))
        add(getattr(job, "job_url", ""))

        extras = getattr(job, "extra_metadata", None) or {}
        if isinstance(extras, dict):
            for key in (
                "apply_url",
                "application_url",
                "direct_apply_url",
                "external_apply_url",
                "canonical_url",
                "source_url",
                "url",
            ):
                add(extras.get(key))

        return urls

    candidates: list[JobPost] = []
    candidate_urls: dict[str, list[str]] = {}
    for job in jobs:
        description = clean_description_text(getattr(job, "description", "") or "")
        if has_complete_job_description(description):
            continue
        urls = _candidate_urls(job)
        if urls:
            candidates.append(job)
            candidate_urls[job.id] = urls

    if not candidates:
        return

    semaphore = asyncio.Semaphore(concurrency)

    async def _hydrate_one(job: JobPost) -> bool:
        current = clean_description_text(getattr(job, "description", "") or "")
        details = None
        attempted_urls = candidate_urls.get(job.id, [])
        for url in attempted_urls:
            async with semaphore:
                details = await fetch_full_job_description(
                    url,
                    timeout=timeout,
                    expand_links=True,
                    client=description_client,
                )
            if details:
                replacement = clean_description_text(details.description)
                if has_complete_job_description(replacement) and len(replacement) > len(current):
                    break
            details = None
        if details is None:
            return False
        replacement = clean_description_text(details.description)
        job.description = replacement
        job.job_url = details.source_url or job.job_url
        extras = dict(job.extra_metadata or {})
        extras["description_hydrated"] = True
        extras["description_hydrated_from"] = details.source_url
        extras["description_extractor"] = details.extractor
        extras["description_hydration_attempted_urls"] = len(attempted_urls)
        job.extra_metadata = extras
        return True

    limits = httpx.Limits(
        max_connections=max(concurrency * 2, 20),
        max_keepalive_connections=max(concurrency, 10),
        keepalive_expiry=30.0,
    )
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(timeout, connect=min(8.0, timeout), read=timeout, write=8.0, pool=8.0),
        follow_redirects=True,
        headers=DEFAULT_HEADERS,
        limits=limits,
    ) as description_client:
        results = await asyncio.gather(*[_hydrate_one(job) for job in candidates], return_exceptions=True)
    hydrated = sum(1 for result in results if result is True)
    logger.info(
        "JD hydration: upgraded %s/%s incomplete direct-page descriptions (no cap; concurrency=%s)",
        hydrated,
        len(candidates),
        concurrency,
    )


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default

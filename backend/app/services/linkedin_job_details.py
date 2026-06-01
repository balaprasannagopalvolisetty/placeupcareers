"""LinkedIn guest job detail extraction.

LinkedIn search pages often expose only compact card text. This module fetches
the actual guest job URL and extracts the JobPosting JSON-LD/details that are
needed for company names and full job descriptions.

Throttling policy (added after the 6h run was getting hammered with 429s):

  1. Per-process token bucket — at most LINKEDIN_REQUESTS_PER_MINUTE
     guest-page fetches per minute, regardless of asyncio concurrency.
  2. Exponential backoff on every 429 / 503, respecting the
     Retry-After header when LinkedIn sends one.
  3. Circuit breaker — once we hit N 429s within a short window we
     stop attempting LinkedIn detail fetches for COOLDOWN_SECONDS. The
     rest of the scrape continues normally; LinkedIn enrichment
     resumes automatically once the cooldown elapses.
  4. Optional Scrapling stealth fallback — when stealth is on and
     plain httpx is locked out, we re-fetch the same URL via
     Scrapling's StealthyFetcher (which rotates headers + JS-renders).
     This is best-effort and skipped if Scrapling isn't importable.
"""

from __future__ import annotations

import asyncio
import html
import json
import logging
import os
import random
import re
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

from app.models.job import JobPost
from app.utils.deduplication import generate_content_hash, generate_job_id

logger = logging.getLogger(__name__)

BOARD_COMPANIES = {"linkedin", "indeed", "glassdoor", "ziprecruiter", "zip_recruiter", "google"}

# Multiple realistic UAs so consecutive requests don't look identical to
# LinkedIn's bot heuristics. Picked from current Chrome/Safari major versions.
USER_AGENTS = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
)


def _build_headers() -> dict[str, str]:
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Upgrade-Insecure-Requests": "1",
    }


# Kept for backward compatibility — callers that imported DEFAULT_HEADERS still work.
DEFAULT_HEADERS = _build_headers()


# ─── Throttling configuration (env-tunable) ──────────────────────────

def _env_int(name: str, default: int) -> int:
    try: return int(os.getenv(name, str(default)))
    except (TypeError, ValueError): return default

def _env_float(name: str, default: float) -> float:
    try: return float(os.getenv(name, str(default)))
    except (TypeError, ValueError): return default

REQUESTS_PER_MINUTE = _env_int("LINKEDIN_REQUESTS_PER_MINUTE", 18)  # ≈ one every 3.3s
BREAKER_THRESHOLD   = _env_int("LINKEDIN_BREAKER_THRESHOLD", 5)
BREAKER_WINDOW      = _env_int("LINKEDIN_BREAKER_WINDOW_SECONDS", 120)
COOLDOWN_SECONDS    = _env_int("LINKEDIN_COOLDOWN_SECONDS", 600)
MAX_BACKOFF_SECONDS = _env_float("LINKEDIN_MAX_BACKOFF_SECONDS", 90.0)
THIN_DESCRIPTION_CHARS = _env_int("LINKEDIN_THIN_DESCRIPTION_CHARS", 1200)
ENRICH_MAX_JOBS_PER_RUN = _env_int("LINKEDIN_ENRICH_MAX_JOBS_PER_RUN", 500)
USE_STEALTH_FALLBACK = os.getenv("LINKEDIN_USE_STEALTH_FALLBACK", "true").strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class _LinkedInGate:
    """Process-wide throttle + circuit breaker. One per process — safe
    because Cloud Run runs LinkedIn enrichment from a single Cloud Run
    Job instance at a time."""
    minute_window: deque[float] = field(default_factory=deque)
    recent_429s: deque[float] = field(default_factory=deque)
    cooldown_until: float = 0.0
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    def _trim(self, q: deque[float], window: float, now: float) -> None:
        while q and q[0] < now - window:
            q.popleft()

    async def acquire(self) -> bool:
        """Block until we're allowed to make another LinkedIn request.
        Returns False when we're inside the cooldown circuit — caller
        should skip rather than attempt."""
        async with self.lock:
            now = time.monotonic()
            if now < self.cooldown_until:
                return False
            self._trim(self.minute_window, 60.0, now)
            if len(self.minute_window) >= REQUESTS_PER_MINUTE:
                wait = max(0.5, 60.0 - (now - self.minute_window[0]))
                logger.debug("LinkedIn throttle: waiting %.2fs (rpm cap)", wait)
                await asyncio.sleep(wait)
                now = time.monotonic()
                self._trim(self.minute_window, 60.0, now)
            self.minute_window.append(now)
            return True

    async def record_429(self) -> bool:
        """Note a 429. Returns True if we just tripped the breaker."""
        async with self.lock:
            now = time.monotonic()
            self.recent_429s.append(now)
            self._trim(self.recent_429s, BREAKER_WINDOW, now)
            if len(self.recent_429s) >= BREAKER_THRESHOLD and now >= self.cooldown_until:
                self.cooldown_until = now + COOLDOWN_SECONDS
                logger.warning(
                    "LinkedIn circuit breaker tripped — pausing detail enrichment for %ss "
                    "(%s 429s in the last %ss)",
                    COOLDOWN_SECONDS, len(self.recent_429s), BREAKER_WINDOW,
                )
                return True
            return False

    def is_open(self) -> bool:
        return time.monotonic() < self.cooldown_until

    def cooldown_remaining(self) -> int:
        return max(0, int(self.cooldown_until - time.monotonic()))


# Module-level singleton. One gate shared across all coroutines in this process.
_GATE = _LinkedInGate()


def linkedin_gate_status() -> dict:
    """Expose the gate state for health endpoints / logging."""
    return {
        "circuit_open": _GATE.is_open(),
        "cooldown_remaining_seconds": _GATE.cooldown_remaining(),
        "requests_in_last_minute": len(_GATE.minute_window),
        "recent_429s": len(_GATE.recent_429s),
        "rpm_cap": REQUESTS_PER_MINUTE,
    }


@dataclass
class LinkedInJobDetails:
    title: str = ""
    company: str = ""
    location: str = ""
    description: str = ""
    employment_type: str = ""
    posted_at: datetime | None = None
    source_job_id: str = ""
    canonical_url: str = ""


def is_linkedin_job_url(url: str) -> bool:
    parsed = urlparse(url or "")
    host = parsed.netloc.lower()
    return "linkedin.com" in host and "/jobs/" in parsed.path.lower()


def needs_linkedin_enrichment(job: JobPost) -> bool:
    url = getattr(job, "job_url", "") or getattr(job, "job_url_direct", "") or ""
    if not is_linkedin_job_url(url):
        return False
    company = (getattr(job, "company", "") or "").strip().lower()
    description = (getattr(job, "description", "") or "").strip()
    return company in BOARD_COMPANIES or len(description) < THIN_DESCRIPTION_CHARS


async def enrich_linkedin_jobs(
    jobs: list[JobPost],
    *,
    max_jobs: int = ENRICH_MAX_JOBS_PER_RUN,
    concurrency: int = 4,
) -> int:
    """Enrich job descriptions/companies by fetching their canonical
    LinkedIn detail pages.

    Concurrency is double-gated:
      - asyncio.Semaphore caps parallel coroutines.
      - The module-level _GATE throttles to LINKEDIN_REQUESTS_PER_MINUTE
        across the process, so even with a higher semaphore we stay
        under LinkedIn's rate threshold.
    """
    candidates = [job for job in jobs if needs_linkedin_enrichment(job)]
    if not candidates:
        return 0
    if _GATE.is_open():
        logger.info(
            "LinkedIn enrichment paused (circuit open — %ss remaining); skipping %s candidates.",
            _GATE.cooldown_remaining(), len(candidates),
        )
        return 0
    candidates = candidates[:max_jobs]
    semaphore = asyncio.Semaphore(max(1, min(concurrency, 4)))  # ≤4 hard cap
    enriched = 0
    skipped = 0
    failures_429 = 0

    async with httpx.AsyncClient(
        timeout=httpx.Timeout(35.0, connect=10.0),
        headers=_build_headers(),
        follow_redirects=True,
        http2=True,
    ) as client:

        async def _run(job: JobPost) -> None:
            nonlocal enriched, skipped, failures_429
            async with semaphore:
                # Bail early if the breaker tripped mid-batch.
                if _GATE.is_open():
                    skipped += 1
                    return
                try:
                    details = await fetch_linkedin_job_details(
                        client, job.job_url or job.job_url_direct or ""
                    )
                except LinkedInRateLimited as exc:
                    failures_429 += 1
                    logger.debug("LinkedIn 429 for %s: %s", job.job_url, exc)
                    return
                except Exception as exc:
                    logger.debug("LinkedIn detail enrichment failed for %s: %s", job.job_url, exc)
                    return
                if apply_linkedin_details(job, details):
                    enriched += 1

        await asyncio.gather(*[_run(job) for job in candidates])

    logger.info(
        "LinkedIn detail enrichment: %s repaired, %s 429-failed, %s skipped (breaker_open=%s)",
        enriched, failures_429, skipped, _GATE.is_open(),
    )
    return enriched


class LinkedInRateLimited(Exception):
    """Raised when LinkedIn returns 429 or otherwise rejects the request.

    Caller treats this as a transient miss: the job just doesn't get
    enriched this run — the scheduled scraper retries it next cycle."""


async def fetch_linkedin_job_details(client: httpx.AsyncClient, url: str) -> LinkedInJobDetails:
    """Fetch + parse a LinkedIn job detail page with adaptive backoff.

    Strategy:
      1. Pass through the process-wide throttle gate.
      2. Try the canonical guest URL with rotated UA + retry up to
         3 times with exponential backoff (respecting Retry-After).
      3. If httpx is locked out and stealth fallback is enabled, hand
         the same URL to Scrapling's StealthyFetcher and parse its
         HTML output.
      4. Raise LinkedInRateLimited if every attempt failed — caller
         logs and moves on, rather than crashing the whole batch.
    """
    canonical = canonical_linkedin_job_url(url)
    target = canonical or url
    if not target:
        return LinkedInJobDetails()

    if not await _GATE.acquire():
        raise LinkedInRateLimited("circuit open")

    last_err: Exception | None = None
    backoff = 4.0
    for attempt in range(3):
        try:
            response = await client.get(
                target,
                headers=_build_headers(),  # fresh UA each retry
            )
        except httpx.HTTPError as exc:
            last_err = exc
            await asyncio.sleep(min(backoff, MAX_BACKOFF_SECONDS))
            backoff = min(backoff * 2, MAX_BACKOFF_SECONDS)
            continue

        if response.status_code in (429, 503):
            tripped = await _GATE.record_429()
            # Respect Retry-After if it's present and reasonable.
            try:
                wait = float(response.headers.get("retry-after", ""))
            except ValueError:
                wait = 0.0
            if not wait:
                wait = backoff
            wait = min(wait + random.uniform(0, 2.0), MAX_BACKOFF_SECONDS)
            logger.debug(
                "LinkedIn %s on %s — sleeping %.1fs (attempt %s/3, breaker_open=%s)",
                response.status_code, target, wait, attempt + 1, tripped,
            )
            await asyncio.sleep(wait)
            backoff = min(backoff * 2, MAX_BACKOFF_SECONDS)
            if tripped:
                break  # don't keep hammering after the breaker opens
            continue

        if response.status_code >= 400:
            last_err = httpx.HTTPStatusError(
                f"LinkedIn HTTP {response.status_code}", request=response.request, response=response
            )
            break

        details = parse_linkedin_job_html(response.text)
        if canonical:
            details.canonical_url = canonical
        elif str(response.url):
            details.canonical_url = canonical_linkedin_job_url(str(response.url)) or str(response.url)
        return details

    # ── Stealth fallback (Scrapling) — best-effort, only if enabled.
    if USE_STEALTH_FALLBACK:
        try:
            details = await _fetch_via_scrapling(target)
        except Exception as exc:  # noqa: BLE001
            logger.debug("LinkedIn Scrapling fallback failed: %s", exc)
        else:
            if details and (details.title or details.description):
                if canonical:
                    details.canonical_url = canonical
                return details

    raise LinkedInRateLimited(str(last_err) if last_err else "LinkedIn fetch failed")


async def _fetch_via_scrapling(url: str) -> LinkedInJobDetails | None:
    """Best-effort stealth fetch through Scrapling. Returns None if the
    library isn't installed or the fetch fails — caller handles None."""
    try:
        # Lazy import; the rest of the worker runs fine without Scrapling.
        from scrapling.fetchers import StealthyFetcher  # type: ignore
    except ImportError:
        return None
    loop = asyncio.get_running_loop()

    def _go() -> str:
        page = StealthyFetcher.fetch(url, headless=True, network_idle=True, timeout=45000)
        # Scrapling exposes the rendered HTML on .html or .text depending
        # on version — try both.
        return getattr(page, "html", None) or getattr(page, "text", "") or ""

    html_text = await loop.run_in_executor(None, _go)
    if not html_text:
        return None
    return parse_linkedin_job_html(html_text)


def apply_linkedin_details(job: JobPost, details: LinkedInJobDetails) -> bool:
    changed = False
    current_company = (job.company or "").strip()
    if details.company and (not current_company or current_company.lower() in BOARD_COMPANIES):
        job.company = details.company
        changed = True
    if details.title and (not job.title or job.title.lower().endswith(" jobs")):
        job.title = details.title
        changed = True
    if details.location and _location_is_better(details.location, job.location):
        job.location = details.location
        changed = True
    if details.description and len(details.description) > len((job.description or "").strip()):
        job.description = details.description
        changed = True
    if details.employment_type and not job.job_type:
        job.job_type = details.employment_type
        changed = True
    if details.posted_at and not job.posted_at:
        job.posted_at = details.posted_at
        changed = True
    if details.canonical_url and details.canonical_url != job.job_url:
        job.job_url = details.canonical_url
        changed = True
    if details.source_job_id:
        stable_source_id = f"linkedin:{details.source_job_id}"
        if job.source_job_id != stable_source_id:
            job.source_job_id = stable_source_id
            changed = True

    if changed:
        job.id = generate_job_id(job.title, job.company, job.location or job.job_url)
        job.content_hash = generate_content_hash(job.title, job.company, job.location or job.job_url)
        extra = job.extra_metadata if isinstance(job.extra_metadata, dict) else {}
        extra["linkedin_detail_enriched"] = True
        job.extra_metadata = extra
    return changed


def parse_linkedin_job_html(markup: str) -> LinkedInJobDetails:
    soup = BeautifulSoup(markup or "", "html.parser")
    jsonld = _find_jobposting_jsonld(soup)
    details = LinkedInJobDetails()
    if jsonld:
        details.title = _clean(jsonld.get("title"))
        org = jsonld.get("hiringOrganization") or {}
        if isinstance(org, dict):
            details.company = _clean(org.get("name"))
        details.location = _location_from_jsonld(jsonld.get("jobLocation"))
        details.description = _html_to_text(jsonld.get("description"))
        details.employment_type = _employment_type(jsonld.get("employmentType"))
        details.posted_at = _parse_datetime(jsonld.get("datePosted"))
    if not details.title:
        details.title = _clean(_meta_content(soup, "og:title")).split(" | ")[0]
    if not details.company:
        details.company = _company_from_page(soup)
    if not details.location:
        details.location = _clean(_select_text(soup, ".topcard__flavor--bullet, .job-search-card__location"))
    if not details.description:
        details.description = _description_from_page(soup)
    details.source_job_id = _source_job_id_from_soup(soup)
    details.canonical_url = canonical_linkedin_job_url(_meta_content(soup, "og:url"))
    return details


def canonical_linkedin_job_url(url: str) -> str:
    match = re.search(r"/jobs/view/(\d+)", url or "")
    if not match:
        match = re.search(r"[?&]currentJobId=(\d+)", url or "")
    if not match:
        return ""
    return f"https://www.linkedin.com/jobs/view/{match.group(1)}"


def _find_jobposting_jsonld(soup: BeautifulSoup) -> dict[str, Any]:
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        try:
            payload = json.loads(script.string or script.get_text("", strip=True) or "{}")
        except json.JSONDecodeError:
            continue
        stack = payload if isinstance(payload, list) else [payload]
        while stack:
            item = stack.pop(0)
            if not isinstance(item, dict):
                continue
            item_type = item.get("@type")
            types = item_type if isinstance(item_type, list) else [item_type]
            if any(str(t).lower() == "jobposting" for t in types):
                return item
            graph = item.get("@graph")
            if isinstance(graph, list):
                stack.extend(graph)
    return {}


def _description_from_page(soup: BeautifulSoup) -> str:
    selectors = (
        ".show-more-less-html__markup",
        ".description__text",
        ".jobs-description__content",
        "[data-test-id='job-description']",
    )
    for selector in selectors:
        node = soup.select_one(selector)
        if node:
            text = _html_to_text(str(node))
            if len(text) > 120:
                return text
    return ""


def _company_from_page(soup: BeautifulSoup) -> str:
    for selector in (
        ".topcard__org-name-link",
        ".topcard__flavor",
        ".job-search-card__subtitle-link",
    ):
        value = _clean(_select_text(soup, selector))
        if value and value.lower() not in BOARD_COMPANIES:
            return value
    og_title = _meta_content(soup, "og:title")
    match = re.search(r"\bat\s+(.+?)(?:\s*\||$)", og_title or "", flags=re.IGNORECASE)
    return _clean(match.group(1)) if match else ""


def _location_from_jsonld(value: Any) -> str:
    locations = value if isinstance(value, list) else [value]
    parts: list[str] = []
    for location in locations:
        if not isinstance(location, dict):
            continue
        address = location.get("address") or {}
        if not isinstance(address, dict):
            continue
        city = _clean(address.get("addressLocality"))
        region = _clean(address.get("addressRegion"))
        country = _clean(address.get("addressCountry"))
        line = ", ".join(part for part in (city, region) if part)
        if country and country not in line:
            line = ", ".join(part for part in (line, country) if part)
        if line:
            parts.append(line)
    return "; ".join(dict.fromkeys(parts))


def _html_to_text(value: Any) -> str:
    text = html.unescape(str(value or ""))
    soup = BeautifulSoup(text, "html.parser")
    for br in soup.find_all("br"):
        br.replace_with("\n")
    for node in soup.find_all(["li", "p", "div", "h2", "h3"]):
        node.insert_before("\n")
    text = soup.get_text("\n", strip=True)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _employment_type(value: Any) -> str:
    if isinstance(value, list):
        return ", ".join(_clean(item).replace("_", " ").title() for item in value if _clean(item))
    return _clean(value).replace("_", " ").title()


def _parse_datetime(value: Any) -> datetime | None:
    text = _clean(value)
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _source_job_id_from_soup(soup: BeautifulSoup) -> str:
    for key in ("jobPostingId", "currentJobId"):
        text = str(soup)
        match = re.search(rf'"{key}"\s*:\s*"?(\d+)"?', text)
        if match:
            return match.group(1)
    return ""


def _location_is_better(candidate: str, current: str) -> bool:
    if not candidate:
        return False
    current_clean = _clean(current).lower()
    if not current_clean or current_clean in {"united states", "remote", "not specified"}:
        return True
    return len(candidate) > len(current or "") and "," in candidate


def _meta_content(soup: BeautifulSoup, prop: str) -> str:
    node = soup.find("meta", attrs={"property": prop}) or soup.find("meta", attrs={"name": prop})
    return _clean(node.get("content")) if node else ""


def _select_text(soup: BeautifulSoup, selector: str) -> str:
    node = soup.select_one(selector)
    return node.get_text(" ", strip=True) if node else ""


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()

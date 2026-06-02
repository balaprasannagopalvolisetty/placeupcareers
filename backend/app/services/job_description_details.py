"""Fetch full job descriptions from public job-detail pages.

This module is used only for backfilling thin database rows. It avoids HTML
fetches for boards where our ingestion policy requires official APIs only.
"""

from __future__ import annotations

import html
import json
import logging
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

BLOCKED_HTML_DOMAINS = (
    "linkedin.com",
    "indeed.com",
    "glassdoor.com",
)

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,application/json;q=0.8,*/*;q=0.7",
    "Accept-Language": "en-US,en;q=0.9",
}


@dataclass(slots=True)
class JobDescriptionDetails:
    description: str
    source_url: str
    extractor: str


def is_html_fetch_allowed(url: str) -> bool:
    host = (urlparse(url or "").hostname or "").lower()
    return bool(host) and not any(host == domain or host.endswith(f".{domain}") for domain in BLOCKED_HTML_DOMAINS)


def is_thin_description(description: str | None, *, min_chars: int = 1200, min_words: int = 120) -> bool:
    text = clean_description_text(description or "")
    return len(text) < min_chars or len(text.split()) < min_words


async def fetch_full_job_description(url: str, *, timeout: float = 25.0) -> JobDescriptionDetails | None:
    if not url or not is_html_fetch_allowed(url):
        return None

    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True, headers=DEFAULT_HEADERS) as client:
            response = await client.get(url)
            if response.status_code in (401, 403, 404, 410):
                logger.debug("JD fetch skipped %s status=%s", url, response.status_code)
                return None
            response.raise_for_status()
    except Exception as exc:  # noqa: BLE001
        logger.debug("JD fetch failed for %s: %s", url, exc)
        return None

    content_type = response.headers.get("content-type", "")
    body = response.text or ""
    if "json" in content_type:
        text = _description_from_json(_safe_json(body))
        if text:
            return JobDescriptionDetails(text, str(response.url), "json")
        return None

    soup = BeautifulSoup(body, "lxml")
    extracted = _extract_json_ld_job_description(soup)
    if extracted:
        return JobDescriptionDetails(extracted, str(response.url), "json_ld")

    extracted = _extract_dom_job_description(soup)
    if extracted:
        return JobDescriptionDetails(extracted, str(response.url), "dom")

    return None


def clean_description_text(value: Any) -> str:
    text = str(value or "")
    if not text:
        return ""
    text = html.unescape(text)
    text = re.sub(r"(?i)<\s*br\s*/?\s*>", "\n", text)
    text = re.sub(r"(?i)</\s*(p|div|li|ul|ol|h[1-6]|section|article)\s*>", "\n", text)
    text = BeautifulSoup(text, "lxml").get_text("\n")
    text = html.unescape(text)
    text = text.replace("\xa0", " ")
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\n[ \t]+", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _safe_json(text: str) -> Any:
    try:
        return json.loads(text)
    except Exception:
        return None


def _extract_json_ld_job_description(soup: BeautifulSoup) -> str:
    for script in soup.find_all("script", {"type": re.compile(r"application/ld\+json", re.I)}):
        payload = _safe_json(script.string or script.get_text() or "")
        text = _description_from_json(payload)
        if text:
            return text
    return ""


def _description_from_json(payload: Any) -> str:
    for item in _walk_json(payload):
        if not isinstance(item, dict):
            continue
        item_type = item.get("@type") or item.get("type")
        item_types = item_type if isinstance(item_type, list) else [item_type]
        lowered_types = {str(t).lower() for t in item_types if t}
        if "jobposting" not in lowered_types and not any("jobposting" in t for t in lowered_types):
            continue
        text = clean_description_text(
            item.get("description")
            or item.get("responsibilities")
            or item.get("jobDescription")
            or ""
        )
        if len(text.split()) >= 80:
            return text
    return ""


def _walk_json(payload: Any):
    if isinstance(payload, dict):
        yield payload
        for key in ("@graph", "graph", "jobs", "data", "results", "content"):
            value = payload.get(key)
            if value is not None:
                yield from _walk_json(value)
        return
    if isinstance(payload, list):
        for item in payload:
            yield from _walk_json(item)


def _extract_dom_job_description(soup: BeautifulSoup) -> str:
    for tag in soup(["script", "style", "noscript", "svg", "form", "nav", "header", "footer"]):
        tag.decompose()

    selectors = (
        "[data-testid='job-description']",
        "[data-test='job-description']",
        "[data-qa='job-description']",
        "[data-automation-id='jobPostingDescription']",
        "[itemprop='description']",
        ".job-description",
        ".jobDescription",
        ".posting-description",
        ".posting-content",
        ".description",
        "#job-description",
        "#jobDescription",
        "main",
        "article",
    )
    candidates: list[tuple[int, str, str]] = []
    for selector in selectors:
        for node in soup.select(selector):
            text = clean_description_text(node.get_text("\n"))
            score = _description_score(text)
            if score > 0:
                candidates.append((score, selector, text))

    if not candidates:
        text = clean_description_text(soup.get_text("\n"))
        if _description_score(text) > 0:
            candidates.append((_description_score(text), "page_text", text))

    if not candidates:
        return ""

    candidates.sort(key=lambda row: row[0], reverse=True)
    return candidates[0][2]


def _description_score(text: str) -> int:
    words = text.split()
    if len(words) < 80:
        return 0
    lowered = text.lower()
    markers = (
        "responsibilities",
        "requirements",
        "qualifications",
        "about the job",
        "job description",
        "what you'll do",
        "what you will do",
        "benefits",
        "salary",
    )
    marker_score = sum(80 for marker in markers if marker in lowered)
    return min(len(text), 20000) + marker_score

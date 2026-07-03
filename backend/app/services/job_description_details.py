"""Fetch full job descriptions from public job-detail pages.

This module is used only for backfilling thin database rows. It avoids HTML
fetches for boards where our ingestion policy requires official APIs only.
"""

from __future__ import annotations

import html
import asyncio
import json
import logging
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx
import ipaddress
import socket
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


def _resolves_to_private_ip(host: str) -> bool:
    """True if the host is (or resolves to) a private/loopback/link-local IP.

    SSRF guard: scraped postings carry attacker-controlled job_url values that
    we fetch server-side. Without this a posting could point at cloud metadata
    (169.254.169.254), localhost, or an internal service and exfiltrate data.
    """
    # If the host is already an IP literal, classify it directly.
    try:
        literal = ipaddress.ip_address(host.strip("[]"))
        return (
            literal.is_private or literal.is_loopback or literal.is_link_local
            or literal.is_reserved or literal.is_multicast or literal.is_unspecified
        )
    except ValueError:
        pass
    try:
        infos = socket.getaddrinfo(host, None)
    except (socket.gaierror, UnicodeError, OSError):
        # DNS failure. In restricted/offline environments legitimate public
        # hosts also fail to resolve, so do NOT hard-block on resolution
        # failure alone — the literal/keyword checks above already stop the
        # dangerous cases (localhost, metadata, private IP literals).
        return False
    for info in infos:
        ip_str = info[4][0]
        try:
            ip = ipaddress.ip_address(ip_str.split("%")[0])
        except ValueError:
            return True
        if (
            ip.is_private or ip.is_loopback or ip.is_link_local
            or ip.is_reserved or ip.is_multicast or ip.is_unspecified
        ):
            return True
    return False


def is_html_fetch_allowed(url: str) -> bool:
    parsed = urlparse(url or "")
    # Only fetch over standard web schemes; block file://, gopher://, etc.
    if parsed.scheme not in ("http", "https"):
        return False
    host = (parsed.hostname or "").lower()
    if not host:
        return False
    if any(host == domain or host.endswith(f".{domain}") for domain in BLOCKED_HTML_DOMAINS):
        return False
    # Block direct localhost/metadata literals fast, then verify DNS resolution
    # does not land on a private range (defends against DNS rebinding to some
    # extent and against hostnames that alias internal IPs).
    if host in ("localhost", "metadata", "metadata.google.internal") or host.endswith((".local", ".internal", ".lan")):
        return False
    if _resolves_to_private_ip(host):
        return False
    return True


def is_thin_description(description: str | None, *, min_chars: int = 1200, min_words: int = 120) -> bool:
    text = clean_description_text(description or "")
    return len(text) < min_chars or len(text.split()) < min_words


async def fetch_full_job_description(url: str, *, timeout: float = 25.0, expand_links: bool = True) -> JobDescriptionDetails | None:
    if not url or not is_html_fetch_allowed(url):
        return None

    async def _fetch() -> JobDescriptionDetails | None:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(timeout, connect=min(8.0, timeout), read=timeout, write=8.0, pool=8.0),
            follow_redirects=True,
            headers=DEFAULT_HEADERS,
        ) as client:
            return await _fetch_full_job_description(client, url, expand_links=expand_links)

    try:
        return await asyncio.wait_for(_fetch(), timeout=timeout + 5.0)
    except asyncio.TimeoutError:
        logger.debug("JD fetch timed out for %s", url)
        return None
    except Exception as exc:  # noqa: BLE001
        logger.debug("JD fetch failed for %s: %s", url, exc)
        return None


async def _fetch_full_job_description(
    client: httpx.AsyncClient,
    url: str,
    *,
    expand_links: bool,
    _depth: int = 0,
) -> JobDescriptionDetails | None:
    response = await client.get(url)
    if response.status_code != 200:
        logger.debug("JD fetch skipped %s status=%s", url, response.status_code)
        return None
    response.raise_for_status()

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
    if extracted and not is_thin_description(extracted, min_chars=1400, min_words=140):
        return JobDescriptionDetails(extracted, str(response.url), "dom")

    if expand_links and _depth < 1:
        for detail_url in _candidate_detail_links(soup, str(response.url)):
            try:
                nested = await _fetch_full_job_description(client, detail_url, expand_links=False, _depth=_depth + 1)
            except Exception as exc:  # noqa: BLE001
                logger.debug("JD nested fetch failed for %s: %s", detail_url, exc)
                continue
            if nested and (not extracted or len(nested.description) > len(extracted) + 300):
                return nested

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


def _candidate_detail_links(soup: BeautifulSoup, base_url: str) -> list[str]:
    base_host = (urlparse(base_url).hostname or "").lower()
    seen: set[str] = set()
    candidates: list[tuple[int, str]] = []
    link_re = re.compile(
        r"(?i)\b("
        r"job|jobs|career|careers|opening|position|posting|detail|description|"
        r"req|requisition|apply|view"
        r")\b"
    )
    bad_re = re.compile(r"(?i)\b(login|signin|privacy|terms|cookie|mailto:|tel:|share|saved)\b")
    for anchor in soup.find_all("a", href=True):
        href = str(anchor.get("href") or "").strip()
        label = clean_description_text(anchor.get_text(" "))
        if not href or bad_re.search(href) or bad_re.search(label):
            continue
        absolute = urljoin(base_url, href)
        parsed = urlparse(absolute)
        host = (parsed.hostname or "").lower()
        if not host or host != base_host or not is_html_fetch_allowed(absolute):
            continue
        if absolute in seen:
            continue
        hay = f"{absolute} {label}"
        if not link_re.search(hay):
            continue
        score = 0
        if re.search(r"(?i)\b(job|jobs|career|careers|posting|position|opening)\b", absolute):
            score += 8
        if re.search(r"(?i)\b(apply|view|details?|description|req|requisition)\b", hay):
            score += 5
        if len(label.split()) <= 12:
            score += 2
        seen.add(absolute)
        candidates.append((score, absolute))
    candidates.sort(key=lambda row: row[0], reverse=True)
    return [url for _, url in candidates[:4]]


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
    scam_noise = (
        "gift card",
        "wire transfer",
        "processing fee",
        "training fee",
        "whatsapp",
        "telegram",
    )
    if any(term in lowered for term in scam_noise):
        return 0
    return min(len(text), 20000) + marker_score

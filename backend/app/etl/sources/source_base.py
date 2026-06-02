"""
Shared plumbing for "clean-200" global job-source connectors.

Goal (per GLOBAL_JOB_COVERAGE_PLAN.md §B6): the scraper must only ever
*process* HTTP 200 responses and must NEVER let a flaky/blocked source
raise errors into the pipeline or hammer a host into 4xx/5xx storms.

This module provides:
  - safe_get_json / safe_get_text : fetch that returns None on any non-200
    (after a bounded retry on 429/503), instead of raising.
  - SourceHealth                  : in-memory per-source circuit breaker —
    N consecutive failures disables a source for the rest of the cycle.
  - is_probably_english           : cheap language gate (requirement B4).
  - guarded_source                : wrap a connector coroutine so one bad
    source is skipped (logged), never aborting the whole run.

No dependency on the rest of the app beyond logging, so it is safe to
import and unit-test in isolation.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Optional

import httpx

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 20.0          # seconds
DEFAULT_RETRIES = 2             # extra attempts on transient (429/503) only
RETRYABLE_STATUS = {429, 503}
DEFAULT_HEADERS = {
    # A plain, honest UA. These sources are public/bot-friendly.
    "User-Agent": "PlaceUpCareerBot/1.0 (+https://placeupcareer.com)",
    "Accept": "application/json, text/xml, */*",
}


@dataclass
class SourceHealth:
    """Per-source circuit breaker + status log for one scrape cycle.

    Trip the breaker after `threshold` consecutive failures so we stop
    retrying a dead/blocked source within the same cycle.
    """
    threshold: int = 3
    _consec_fail: dict[str, int] = field(default_factory=dict)
    _disabled: set[str] = field(default_factory=set)
    last_status: dict[str, str] = field(default_factory=dict)

    def is_open(self, source: str) -> bool:
        """True if the breaker is tripped (source should be skipped)."""
        return source in self._disabled

    def record_ok(self, source: str) -> None:
        self._consec_fail[source] = 0
        self.last_status[source] = "ok"

    def record_fail(self, source: str, reason: str) -> None:
        n = self._consec_fail.get(source, 0) + 1
        self._consec_fail[source] = n
        self.last_status[source] = f"fail({n}): {reason}"
        if n >= self.threshold:
            self._disabled.add(source)
            logger.warning("circuit breaker OPEN for %s after %s failures", source, n)

    def summary(self) -> dict[str, str]:
        return dict(self.last_status)


async def safe_get_json(
    url: str,
    *,
    client: Optional[httpx.AsyncClient] = None,
    params: Optional[dict] = None,
    headers: Optional[dict] = None,
    timeout: float = DEFAULT_TIMEOUT,
    retries: int = DEFAULT_RETRIES,
) -> Optional[Any]:
    """GET `url` and return parsed JSON, or None on any non-200 / error.

    Never raises. Retries only on 429/503 with linear backoff. Anything
    else (403/404/500/timeout/JSON error) → log + return None so the
    caller can skip cleanly.
    """
    text = await safe_get_text(
        url, client=client, params=params, headers=headers,
        timeout=timeout, retries=retries,
    )
    if text is None:
        return None
    try:
        import json
        return json.loads(text)
    except (ValueError, TypeError) as exc:
        logger.warning("non-JSON body from %s: %s", url, exc)
        return None


async def safe_get_text(
    url: str,
    *,
    client: Optional[httpx.AsyncClient] = None,
    params: Optional[dict] = None,
    headers: Optional[dict] = None,
    timeout: float = DEFAULT_TIMEOUT,
    retries: int = DEFAULT_RETRIES,
) -> Optional[str]:
    """GET `url` and return the response body text, or None on non-200.

    Only an HTTP 200 is treated as success — exactly what "we only accept
    200 codes" requires. 429/503 get a bounded retry; everything else is a
    clean skip.
    """
    merged_headers = {**DEFAULT_HEADERS, **(headers or {})}
    own_client = client is None
    if own_client:
        client = httpx.AsyncClient(timeout=timeout, follow_redirects=True)
    try:
        attempt = 0
        while True:
            try:
                resp = await client.get(url, params=params, headers=merged_headers)
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                if attempt < retries:
                    attempt += 1
                    await asyncio.sleep(attempt)  # linear backoff
                    continue
                logger.warning("network error GET %s: %s", url, exc)
                return None

            if resp.status_code == 200:
                return resp.text

            if resp.status_code in RETRYABLE_STATUS and attempt < retries:
                attempt += 1
                # Honour Retry-After when present, else linear backoff.
                wait = _retry_after_seconds(resp) or attempt
                await asyncio.sleep(min(wait, 10))
                continue

            logger.info("skip %s — HTTP %s", url, resp.status_code)
            return None
    finally:
        if own_client:
            await client.aclose()


def _retry_after_seconds(resp: httpx.Response) -> Optional[float]:
    raw = resp.headers.get("Retry-After")
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


# ─── language heuristic (requirement B4: English-friendly only) ──────────────

# Common English function words. Their presence is a cheap, dependency-free
# signal that a posting is written in English — good enough to filter out
# local-language postings from non-English-speaking countries' portals.
_EN_STOPWORDS = {
    "the", "and", "for", "you", "are", "with", "our", "your", "this", "that",
    "will", "have", "from", "work", "team", "role", "we", "to", "of", "in",
    "experience", "skills", "join", "looking", "about", "responsibilities",
}


def is_probably_english(text: str, *, min_hits: int = 4) -> bool:
    """Best-effort: True if `text` looks like English prose.

    Counts distinct English stop-words in the first chunk of text. Cheap and
    dependency-free; replace with `langdetect` later if higher precision is
    needed. Empty/short text → False (can't confirm English).
    """
    if not text:
        return False
    sample = text.lower()[:1500]
    tokens = set(_split_words(sample))
    hits = len(tokens & _EN_STOPWORDS)
    return hits >= min_hits


def _split_words(text: str):
    word = []
    for ch in text:
        if ch.isalpha():
            word.append(ch)
        elif word:
            yield "".join(word)
            word = []
    if word:
        yield "".join(word)


async def guarded_source(
    name: str,
    coro_factory: Callable[[], Awaitable[list]],
    *,
    health: SourceHealth,
) -> list:
    """Run one source connector, swallowing failures.

    Returns the connector's list, or [] if the breaker is open or the
    connector raised. Guarantees a single bad source can never abort the
    cycle or surface an error to the pipeline/frontend.
    """
    if health.is_open(name):
        logger.info("skip %s — circuit breaker open", name)
        return []
    try:
        result = await coro_factory()
        health.record_ok(name)
        return result or []
    except Exception as exc:  # defensive: connectors should not raise, but never trust
        health.record_fail(name, repr(exc))
        logger.warning("source %s failed: %s", name, exc)
        return []

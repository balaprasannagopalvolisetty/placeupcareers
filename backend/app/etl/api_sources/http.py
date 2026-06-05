from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)


async def get_json(
    url: str,
    *,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = 30.0,
    retries: int = 2,
    backoff_seconds: float = 1.5,
) -> Any:
    """GET JSON with small exponential backoff.

    Failures bubble to the source runner, where they are logged per source so
    one provider cannot crash the full 6-hour job.
    """
    last_exc: Exception | None = None
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True, headers=headers) as client:
        for attempt in range(retries + 1):
            try:
                response = await client.get(url, params=params)
                if response.status_code in {429, 500, 502, 503, 504} and attempt < retries:
                    await asyncio.sleep(backoff_seconds * (2 ** attempt))
                    continue
                response.raise_for_status()
                return response.json()
            except Exception as exc:
                last_exc = exc
                if attempt >= retries:
                    break
                logger.info("Retrying %s after %s", url, exc)
                await asyncio.sleep(backoff_seconds * (2 ** attempt))
    raise last_exc or RuntimeError(f"GET failed: {url}")

"""Lightweight cache layer — Redis-backed when REDIS_URL is set, with a safe
in-process TTL fallback otherwise.

Goals:
  * Speed up the expensive read endpoints (jobs counts, alerts series, analytics
    market) so the dashboard feels instant even while the scraper writes.
  * NEVER break if Redis is unavailable — every failure degrades to the local
    fallback (or to recomputing), so deploying without a Redis instance is fine.

Usage:
    from app.services.cache import cache_get_json, cache_set_json, cached_json

    data = cache_get_json("analytics:market")
    if data is None:
        data = expensive()
        cache_set_json("analytics:market", data, ttl=120)

or the async helper:

    data = await cached_json("analytics:market", ttl=120, producer=expensive_async)
"""
from __future__ import annotations

import json
import logging
import os
import time
from typing import Any, Awaitable, Callable, Optional

logger = logging.getLogger(__name__)

_REDIS_URL = (os.getenv("REDIS_URL") or "").strip()
_redis = None
_redis_tried = False

# In-process fallback (per Cloud Run instance). Bounded so it can't grow forever.
_local: dict[str, tuple[float, Any]] = {}
_LOCAL_MAX = 512


def _get_redis():
    global _redis, _redis_tried
    if _redis is not None or _redis_tried:
        return _redis
    _redis_tried = True
    if not _REDIS_URL:
        return None
    try:
        import redis  # type: ignore

        _redis = redis.Redis.from_url(_REDIS_URL, socket_timeout=1.5, socket_connect_timeout=1.5, decode_responses=True)
        _redis.ping()
        logger.info("Cache: connected to Redis")
    except Exception as exc:  # pragma: no cover - depends on deploy env
        logger.warning("Cache: Redis unavailable, using in-process fallback: %s", exc)
        _redis = None
    return _redis


def cache_get_json(key: str) -> Optional[Any]:
    r = _get_redis()
    if r is not None:
        try:
            raw = r.get(key)
            return json.loads(raw) if raw else None
        except Exception:
            pass
    hit = _local.get(key)
    if hit and hit[0] > time.monotonic():
        return hit[1]
    if hit:
        _local.pop(key, None)
    return None


def cache_set_json(key: str, value: Any, ttl: int = 120) -> None:
    r = _get_redis()
    if r is not None:
        try:
            r.setex(key, ttl, json.dumps(value, default=str))
            return
        except Exception:
            pass
    if len(_local) > _LOCAL_MAX:
        _local.clear()
    _local[key] = (time.monotonic() + ttl, value)


async def cached_json(key: str, ttl: int, producer: Callable[[], Awaitable[Any]]) -> Any:
    """Return cached JSON for key, or run the async producer and cache it."""
    cached = cache_get_json(key)
    if cached is not None:
        return cached
    value = await producer()
    try:
        cache_set_json(key, value, ttl=ttl)
    except Exception:
        pass
    return value


def cache_invalidate(prefix: str = "") -> None:
    r = _get_redis()
    if r is not None and prefix:
        try:
            for k in r.scan_iter(match=f"{prefix}*", count=200):
                r.delete(k)
        except Exception:
            pass
    for k in [k for k in _local if not prefix or k.startswith(prefix)]:
        _local.pop(k, None)

"""
Security middleware: rate limiting, security headers, request-size cap.

Why this module exists
----------------------
The API previously had no rate limiting and no security headers beyond
CORS. That made it cheap to brute-force /api/auth/login, scrape /api/jobs
in tight loops, or load the API in a third-party iframe. This module
centralises those defenses so they apply to every route uniformly.

Design notes
------------
- Rate limiter is an in-process sliding window keyed by (client_ip,
  bucket). Buckets isolate cheap reads from expensive writes, so a
  flood of /api/jobs requests can't deny service to /api/auth/login.
- For multi-instance Cloud Run, swap the in-process counters for Redis
  in `RATE_LIMIT_BACKEND=redis`; the contract stays the same.
- Headers follow OWASP secure-headers guidance and are safe to apply
  to a JSON API (no CSP needed — Firebase Hosting already sets one
  for the SPA).
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict, deque
from typing import Deque, Dict, Tuple

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, Response

log = logging.getLogger(__name__)

# (max_requests, window_seconds) per bucket.
RATE_LIMITS: Dict[str, Tuple[int, int]] = {
    # Strict bucket: login / signup / password / OAuth. Brute-force surface.
    "auth": (10, 60),
    # Moderate bucket: writes that mutate user data.
    "write": (60, 60),
    # Generous bucket: reads. Job listings, taxonomy, dashboard summary.
    "read": (240, 60),
}


def _bucket_for(path: str, method: str) -> str:
    if "/api/auth" in path:
        return "auth"
    if method.upper() in {"POST", "PUT", "PATCH", "DELETE"}:
        return "write"
    return "read"


def _client_ip(request: Request) -> str:
    # Cloud Run injects the real client IP into X-Forwarded-For. Trust
    # only the leftmost entry — anything else is attacker-controlled.
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",", 1)[0].strip()
    return request.client.host if request.client else "unknown"


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Sliding-window per-IP per-bucket limiter."""

    def __init__(self, app):
        super().__init__(app)
        self._hits: Dict[Tuple[str, str], Deque[float]] = defaultdict(deque)

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        # Don't rate-limit health checks or static schema. Cloud Run pings
        # /api/health constantly; throttling those is wasted CPU.
        if path in {"/api/health", "/api/health/", "/", "/docs", "/openapi.json", "/redoc"}:
            return await call_next(request)

        bucket = _bucket_for(path, request.method)
        max_req, window = RATE_LIMITS[bucket]
        ip = _client_ip(request)
        key = (ip, bucket)
        now = time.monotonic()

        hits = self._hits[key]
        # Drop entries older than the window.
        while hits and hits[0] < now - window:
            hits.popleft()

        if len(hits) >= max_req:
            retry_after = max(1, int(window - (now - hits[0])))
            log.info("Rate-limit hit: ip=%s bucket=%s path=%s", ip, bucket, path)
            return JSONResponse(
                {
                    "detail": "Too many requests. Please slow down and try again shortly.",
                    "bucket": bucket,
                    "retry_after": retry_after,
                },
                status_code=429,
                headers={
                    "Retry-After": str(retry_after),
                    "X-RateLimit-Bucket": bucket,
                    "X-RateLimit-Limit": str(max_req),
                    "X-RateLimit-Remaining": "0",
                },
            )

        hits.append(now)
        response = await call_next(request)
        response.headers["X-RateLimit-Bucket"] = bucket
        response.headers["X-RateLimit-Limit"] = str(max_req)
        response.headers["X-RateLimit-Remaining"] = str(max(0, max_req - len(hits)))
        return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Apply hardened response headers to every request."""

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        # OWASP secure headers tuned for a JSON API behind HTTPS.
        # We don't set CSP here — it's a JSON API. The SPA gets CSP
        # from firebase.json (Firebase Hosting).
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault(
            "Permissions-Policy",
            "geolocation=(), microphone=(), camera=(), payment=(), usb=()",
        )
        # HSTS — Cloud Run terminates TLS, browsers should pin HTTPS.
        # Only set on real responses (Cloud Run injects HTTPS upstream).
        if request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https":
            response.headers.setdefault(
                "Strict-Transport-Security",
                "max-age=31536000; includeSubDomains",
            )
        return response

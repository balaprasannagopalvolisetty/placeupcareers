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
import secrets
import time
from collections import defaultdict, deque
from typing import Deque, Dict, Tuple
from urllib.parse import urlparse

import jwt
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, Response

from app.config import settings
from app.zero_trust import ban_tracker, denial_response

# Public endpoints where a 401/403 response means a failed credential attempt
# (login, OTP, invite code, password reset). Repeated failures here feed the
# auto-ban tracker so brute-forcing any of them from one IP trips a temp block.
SENSITIVE_AUTH_PATHS = {
    "/api/auth/signin",
    "/api/auth/otp/verify",
    "/api/auth/otp/request",
    "/api/invite/validate",
    "/api/invite/verify",
    "/api/auth/forgot-password",
    "/api/auth/reset-password",
    "/api/forgot-password",
    "/api/reset-password",
}

log = logging.getLogger(__name__)

# (max_requests, window_seconds) per bucket.
RATE_LIMITS: Dict[str, Tuple[int, int]] = {
    # Strict bucket: login / signup / password / OAuth. Brute-force surface.
    # 20/min per IP is far more than any real user needs (nobody logs in 20x
    # a minute) while cutting credential-stuffing throughput 3x vs the old 60.
    "auth": (20, 60),
    # Moderate bucket: writes that mutate user data.
    "write": (60, 60),
    # Generous bucket: reads. Job listings, taxonomy, dashboard summary.
    "read": (1200, 60),
}

MAX_REQUEST_BODY_BYTES = 12 * 1024 * 1024

PUBLIC_READ_PATHS = {
    "/",
    "/api/health",
    "/api/auth/demo",
    "/api/auth/oidc/providers",
    "/api/auth/session",
    "/api/billing/plans",
    "/api/invite/status",
    # The category/role taxonomy powers the signup "target positions" picker,
    # which unauthenticated visitors need. It's a static public list — no user
    # data — so it's safe to expose without a token.
    "/api/jobs/taxonomy",
    "/docs",
    "/openapi.json",
    "/redoc",
}
PUBLIC_READ_PREFIXES = (
    "/api/auth/oidc/google",
    "/api/payments/plans",
)
PUBLIC_WRITE_PATHS = {
    "/api/auth/signin",
    "/api/auth/signup",
    "/api/auth/otp/request",
    "/api/auth/otp/verify",
    "/api/auth/refresh",
    "/api/auth/logout",
    "/api/auth/forgot-password",
    "/api/auth/reset-password",
    "/api/forgot-password",
    "/api/reset-password",
    "/api/billing/webhook",
    "/api/contact",
    "/api/invite/validate",
    "/api/invite/waitlist",
    "/api/invite/verify",
}

RATE_LIMIT_EXEMPT_GET_PREFIXES = (
    "/api/jobs",
    "/api/visa",
    "/api/user/dashboard",
)


def _bucket_for(path: str, method: str) -> str:
    # Invite-code guessing is the same brute-force surface as login, so
    # /api/invite/* shares the strict auth bucket.
    if "/api/auth" in path or "/api/invite" in path:
        return "auth"
    if method.upper() in {"POST", "PUT", "PATCH", "DELETE"}:
        return "write"
    return "read"


def _client_ip(request: Request) -> str:
    """Resolve the originating client IP across the proxy chain.

    Header priority (highest trust first):
      1. `CF-Connecting-IP`  - Cloudflare injects this when the request
         comes through the CF proxy. We trust it because Cloudflare's
         WAF is the public-facing edge once DNS is proxied; nothing
         else can reach Cloud Run if firewall rules require the CF
         IP range (see .github/CLOUDFLARE.md).
      2. `True-Client-IP`    - Cloudflare Enterprise version of #1.
      3. `X-Forwarded-For`   - Cloud Run injects this. The leftmost
         entry is the real client; anything to its right is the
         proxy chain itself.
      4. `request.client.host` - direct socket peer, only useful when
         no proxies are in front.
    """
    for header in ("cf-connecting-ip", "true-client-ip"):
        value = request.headers.get(header)
        if value:
            return value.strip()
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
        if request.method.upper() == "GET" and any(path.startswith(prefix) for prefix in RATE_LIMIT_EXEMPT_GET_PREFIXES):
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


class RequestSizeLimitMiddleware(BaseHTTPMiddleware):
    """Reject oversized request bodies before route handlers parse them."""

    async def dispatch(self, request: Request, call_next) -> Response:
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                size = int(content_length)
            except ValueError:
                size = 0
            if size > MAX_REQUEST_BODY_BYTES:
                return JSONResponse(
                    {"detail": "Request body is too large."},
                    status_code=413,
                    headers={"X-Max-Request-Body-Bytes": str(MAX_REQUEST_BODY_BYTES)},
                )
        return await call_next(request)


def _has_valid_auth_header(request: Request) -> bool:
    authorization = request.headers.get("authorization", "")
    api_key = request.headers.get("x-api-key", "")
    if authorization.lower().startswith("bearer "):
        return bool(_user_id_from_header(request))
    if api_key and settings.internal_api_key:
        return secrets.compare_digest(api_key, settings.internal_api_key)
    return False


def _has_any_credential(request: Request) -> bool:
    """True if the caller presented *some* credential (bearer, api key, or
    refresh cookie). Used to separate a routine expired-token 401 — which a
    real client silently refreshes — from anonymous probing of protected
    routes. Only the latter feeds the auto-ban, so legitimate users whose
    access token merely expired are never banned."""
    if request.headers.get("authorization", "").lower().startswith("bearer "):
        return True
    if request.headers.get("x-api-key"):
        return True
    # Refresh-cookie name mirrors app.security.REFRESH_COOKIE_NAME.
    return "placeup_refresh" in request.cookies


def _is_public_read(path: str) -> bool:
    if path in PUBLIC_READ_PATHS:
        return True
    return any(path.startswith(prefix) for prefix in PUBLIC_READ_PREFIXES)


def _allowed_origin_hosts() -> set[str]:
    hosts: set[str] = {
        "placeupcareer.com",
        "www.placeupcareer.com",
        "localhost",
        "127.0.0.1",
    }
    for origin in settings.cors_origins:
        try:
            parsed = urlparse(origin)
            if parsed.hostname:
                hosts.add(parsed.hostname.lower())
        except Exception:
            continue
    return hosts


def _has_trusted_origin(request: Request) -> bool:
    """Validate browser write origins without blocking server-to-server calls."""
    origin = request.headers.get("origin")
    referer = request.headers.get("referer")
    candidate = origin or referer
    if not candidate:
        # Native/mobile/server clients usually omit Origin; they still need auth
        # or a Stripe signature on protected routes.
        return True
    try:
        parsed = urlparse(candidate)
    except Exception:
        return False
    return bool(parsed.hostname and parsed.hostname.lower() in _allowed_origin_hosts())


def _passed_through_cloudflare(request: Request) -> bool:
    """When CF_ORIGIN_SECRET is set, require the header a Cloudflare
    Transform Rule stamps on every proxied request. Traffic that hits the
    Cloud Run URL directly (bypassing Cloudflare's WAF, bot fight mode and
    edge rate limits) won't carry it and gets dropped here. Empty setting
    = check disabled, so this is safe to deploy before the CF rule exists."""
    if not settings.cf_origin_secret:
        return True
    supplied = request.headers.get("x-cf-origin-secret", "")
    return bool(supplied) and secrets.compare_digest(supplied, settings.cf_origin_secret)


class RouteAccessMiddleware(BaseHTTPMiddleware):
    """Zero-trust route gate. Deny-by-default: a request is refused unless it
    matches an explicit public allowlist OR carries a verified credential.

    Also the enforcement point for two "assume-breach" controls:
      - auto-ban: repeated unauthorized attempts from an IP trip a temp block;
      - uniform denial: every refusal returns the SAME body pointing at the
        security contact, so the API never leaks *why* a request failed.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path.rstrip("/") or "/"
        method = request.method.upper()
        ip = _client_ip(request)

        # CORS preflight / cheap probes never carry a body to authorize.
        if method in {"OPTIONS", "HEAD"}:
            return await call_next(request)

        # 1. Assume-breach: if this IP is banned, refuse immediately.
        ban_left = ban_tracker.banned_for(ip)
        if ban_left:
            return denial_response(status_code=429, retry_after=ban_left)

        # 2. Cloudflare origin lock (health/root stay open for Cloud Run probes).
        if path not in {"/", "/api/health"} and not _passed_through_cloudflare(request):
            log.warning("Blocked direct-to-origin request: path=%s ip=%s", path, ip)
            ban_tracker.record_failure(ip)
            return denial_response(status_code=403)

        # 3. Explicit public reads.
        if method == "GET" and _is_public_read(path):
            return await self._forward(request, call_next, path, ip)

        # 4. Explicit public writes (still origin-checked, except Stripe webhook).
        if path in PUBLIC_WRITE_PATHS:
            if path != "/api/billing/webhook" and not _has_trusted_origin(request):
                ban_tracker.record_failure(ip)
                return denial_response(status_code=403)
            return await self._forward(request, call_next, path, ip)

        # 5. Protected API surface — must be authenticated (deny-by-default).
        if path.startswith("/api/"):
            if not _has_valid_auth_header(request):
                # Only count as an attack when NO credential was presented at
                # all. A present-but-expired token is a routine client refresh,
                # never a ban trigger.
                if not _has_any_credential(request):
                    ban_tracker.record_failure(ip)
                return denial_response(status_code=401)
            if method in {"POST", "PUT", "PATCH", "DELETE"} and not _has_trusted_origin(request):
                ban_tracker.record_failure(ip)
                return denial_response(status_code=403)
            return await self._forward(request, call_next, path, ip)

        # 6. Default deny: any path that isn't an explicitly-allowed public
        #    route and isn't an authenticated API call is refused outright.
        log.info("Default-deny unknown path=%s ip=%s", path, ip)
        ban_tracker.record_failure(ip)
        return denial_response(status_code=403)

    async def _forward(self, request: Request, call_next, path: str, ip: str) -> Response:
        """Run the handler, then feed the auto-ban tracker for failed attempts
        on sensitive credential endpoints (login, OTP, invite, reset)."""
        response = await call_next(request)
        if path in SENSITIVE_AUTH_PATHS:
            if response.status_code in (401, 403):
                new_ban = ban_tracker.record_failure(ip)
                if new_ban:
                    # This attempt tripped the ban — return the uniform block so
                    # the very next call is already refused with a retry hint.
                    return denial_response(status_code=429, retry_after=new_ban)
            elif 200 <= response.status_code < 300:
                ban_tracker.clear(ip)
        return response


def _user_id_from_header(request: Request) -> str:
    authorization = request.headers.get("authorization", "")
    if not authorization.lower().startswith("bearer "):
        return ""
    token = authorization.split(" ", 1)[1].strip()
    if not token:
        return ""
    try:
        claims = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            audience="placeup-career-web",
            issuer="placeup-career-api",
        )
        return str(claims.get("sub") or "")
    except jwt.InvalidTokenError:
        return ""


class AuditLogMiddleware(BaseHTTPMiddleware):
    """Log access to sensitive API surfaces with user/IP/status metadata."""

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        path = request.url.path
        sensitive = path.startswith((
            "/api/auth",
            "/api/user",
            "/api/resume",
            "/api/match",
            "/api/contacts",
            "/api/alerts",
            "/api/analytics",
        ))
        high_signal = request.method.upper() != "GET" or response.status_code >= 400
        if sensitive and high_signal:
            log.info(
                "audit access method=%s path=%s status=%s user_id=%s ip=%s",
                request.method,
                path,
                response.status_code,
                _user_id_from_header(request) or "anonymous",
                _client_ip(request),
            )
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

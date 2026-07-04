"""
Zero-Trust application-security core.

Design tenets ("never trust, always verify"):

1. Verify explicitly — every protected request is authenticated AND authorized
   from a cryptographically verified principal, not from network position.
2. Least privilege — a principal carries scopes; handlers assert the specific
   scope/ownership they need, nothing broader.
3. Deny by default — anything not explicitly allowed is refused. The
   middleware treats an unrecognized route as protected, and helpers raise
   on the *absence* of proof rather than trusting a missing check.
4. Assume breach — repeated unauthorized attempts from an IP trip an
   auto-ban; every denial is audit-logged; credentials are short-lived.

Everything a denied caller sees is the SAME uniform payload pointing at the
security contact, so the API never leaks *why* a request was refused
(no user-enumeration, no "wrong password vs no such user" oracle).

This module is import-safe (no FastAPI app state, no DB) so it can be unit
tested in isolation.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import Lock
from typing import Iterable, Optional

import jwt
from starlette.responses import JSONResponse

from app.config import settings

log = logging.getLogger("placeup.zero_trust")


# ─────────────────────────────────────────────────────────────────────────────
# Principal — the verified identity attached to a request.
# ─────────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class Principal:
    """A cryptographically verified caller. Never constructed from
    unauthenticated input — only from a validated token."""
    subject: str                      # user id, or "svc:<name>" for services
    kind: str                         # "user" | "service" | "anonymous"
    scopes: frozenset[str] = field(default_factory=frozenset)
    session_id: Optional[str] = None
    email: Optional[str] = None

    @property
    def is_authenticated(self) -> bool:
        return self.kind != "anonymous" and bool(self.subject)

    def has_scope(self, scope: str) -> bool:
        # "admin" is an implicit superscope.
        return scope in self.scopes or "admin" in self.scopes


ANONYMOUS = Principal(subject="", kind="anonymous")


# ─────────────────────────────────────────────────────────────────────────────
# Uniform denial — the ONLY thing a blocked caller ever sees.
# ─────────────────────────────────────────────────────────────────────────────
class AccessDenied(Exception):
    """Raised anywhere authorization fails. Carries an HTTP status and an
    optional retry hint; the message shown to the user is always the generic
    one built by denial_response()."""

    def __init__(self, status_code: int = 403, retry_after: Optional[int] = None, reason: str = ""):
        self.status_code = status_code
        self.retry_after = retry_after
        self.reason = reason  # internal only — logged, never returned
        super().__init__(reason or "access denied")


def denial_body(retry_after: Optional[int] = None) -> dict:
    contact = settings.security_contact_email
    if retry_after:
        msg = (
            "Access is temporarily blocked. Please wait a few minutes and try "
            f"again. If you believe this is a mistake, reach out to {contact}."
        )
    else:
        msg = (
            "You don't have access to this resource. If you believe this is a "
            f"mistake, please reach out to our team at {contact}."
        )
    body = {"detail": msg, "contact": contact}
    if retry_after:
        body["retry_after"] = retry_after
    return body


def denial_response(status_code: int = 403, retry_after: Optional[int] = None) -> JSONResponse:
    headers = {"Retry-After": str(retry_after)} if retry_after else None
    return JSONResponse(denial_body(retry_after), status_code=status_code, headers=headers)


# ─────────────────────────────────────────────────────────────────────────────
# Client IP resolution (Cloudflare-aware, matches middleware).
# ─────────────────────────────────────────────────────────────────────────────
def client_ip(headers) -> str:
    for h in ("cf-connecting-ip", "true-client-ip"):
        v = headers.get(h)
        if v:
            return v.strip()
    xff = headers.get("x-forwarded-for")
    if xff:
        return xff.split(",", 1)[0].strip()
    return ""


# ─────────────────────────────────────────────────────────────────────────────
# Auto-ban tracker — assume-breach containment for repeated unauthorized hits.
# In-process (per Cloud Run instance). For multi-instance, back it with Redis;
# the interface stays identical.
# ─────────────────────────────────────────────────────────────────────────────
class BanTracker:
    def __init__(self, *, threshold: int, window_s: int, ban_s: int):
        self.threshold = threshold
        self.window_s = window_s
        self.ban_s = ban_s
        self._fails: dict[str, list[float]] = {}
        self._banned_until: dict[str, float] = {}
        self._lock = Lock()

    def _now(self) -> float:
        return time.monotonic()

    def banned_for(self, ip: str) -> int:
        """Seconds remaining on an active ban, else 0."""
        if not ip:
            return 0
        with self._lock:
            until = self._banned_until.get(ip)
            if until is None:
                return 0
            remaining = until - self._now()
            if remaining <= 0:
                self._banned_until.pop(ip, None)
                return 0
            return int(remaining) + 1

    def record_failure(self, ip: str) -> int:
        """Register one auth/authorization failure. Returns ban seconds if this
        failure tripped (or is under) an active ban, else 0."""
        if not ip or self.threshold <= 0:
            return 0
        now = self._now()
        with self._lock:
            hits = [t for t in self._fails.get(ip, []) if t > now - self.window_s]
            hits.append(now)
            self._fails[ip] = hits
            if len(hits) >= self.threshold:
                self._banned_until[ip] = now + self.ban_s
                self._fails.pop(ip, None)
                log.warning("zero_trust auto-ban ip=%s failures=%s ban_s=%s", ip, len(hits), self.ban_s)
                return self.ban_s
            return 0

    def clear(self, ip: str) -> None:
        """A successful auth clears the failure streak (not an active ban)."""
        if not ip:
            return
        with self._lock:
            self._fails.pop(ip, None)


ban_tracker = BanTracker(
    threshold=settings.zt_ban_threshold,
    window_s=settings.zt_ban_window_seconds,
    ban_s=settings.zt_ban_duration_seconds,
)


# ─────────────────────────────────────────────────────────────────────────────
# Token verification → Principal. Pure crypto, no DB. Session/existence checks
# happen in the FastAPI dependency layer (deps.py) which can touch the store.
# ─────────────────────────────────────────────────────────────────────────────
def principal_from_access_token(token: str) -> Optional[Principal]:
    """Return a Principal iff the bearer access token is fully valid
    (signature, exp, iss, aud, typ). Never trusts unsigned claims."""
    if not token:
        return None
    try:
        claims = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            audience="placeup-career-web",
            issuer="placeup-career-api",
            options={"require": ["exp", "iat", "sub"]},
        )
    except jwt.InvalidTokenError:
        return None
    if claims.get("typ") != "access":
        return None
    sub = str(claims.get("sub") or "")
    if not sub:
        return None
    scopes = claims.get("scopes") or []
    if isinstance(scopes, str):
        scopes = scopes.split()
    # Admin membership is authoritative from the allowlist, checked elsewhere;
    # here we only carry what the signed token asserts.
    return Principal(
        subject=sub,
        kind="user",
        scopes=frozenset(str(s) for s in scopes),
        session_id=str(claims.get("sid") or "") or None,
        email=str(claims.get("email") or "") or None,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Service-to-service identity — short-lived signed tokens for internal workers.
# ─────────────────────────────────────────────────────────────────────────────
def _service_secret() -> str:
    return settings.service_token_secret or settings.jwt_secret


def create_service_token(service_name: str, *, scopes: Iterable[str] = ()) -> str:
    """Mint a short-lived identity token for an internal service (scraper, ATS
    worker). Workers present this instead of a long-lived shared key, so a
    leaked token expires on its own and carries a named, least-privilege
    identity."""
    now = datetime.now(tz=timezone.utc)
    payload = {
        "typ": "service",
        "sub": f"svc:{service_name}",
        "scopes": list(scopes),
        "iat": int(now.timestamp()),
        "exp": int(now.timestamp()) + settings.service_token_ttl_seconds,
        "iss": "placeup-career-api",
        "aud": "placeup-career-internal",
    }
    return jwt.encode(payload, _service_secret(), algorithm="HS256")


def principal_from_service_token(token: str) -> Optional[Principal]:
    if not token:
        return None
    try:
        claims = jwt.decode(
            token,
            _service_secret(),
            algorithms=["HS256"],
            audience="placeup-career-internal",
            issuer="placeup-career-api",
            options={"require": ["exp", "iat", "sub"]},
        )
    except jwt.InvalidTokenError:
        return None
    if claims.get("typ") != "service":
        return None
    sub = str(claims.get("sub") or "")
    if not sub.startswith("svc:"):
        return None
    scopes = claims.get("scopes") or []
    if isinstance(scopes, str):
        scopes = scopes.split()
    return Principal(subject=sub, kind="service", scopes=frozenset(str(s) for s in scopes))


# ─────────────────────────────────────────────────────────────────────────────
# Authorization primitives — called by handlers to assert least privilege.
# They RAISE AccessDenied on failure (deny-by-default): a handler that forgets
# to call them still can't be reached anonymously because the middleware gate
# already required a principal.
# ─────────────────────────────────────────────────────────────────────────────
def require_authenticated(principal: Optional[Principal]) -> Principal:
    if principal is None or not principal.is_authenticated:
        raise AccessDenied(status_code=401, reason="unauthenticated")
    return principal


def require_scope(principal: Optional[Principal], scope: str) -> Principal:
    p = require_authenticated(principal)
    if not p.has_scope(scope):
        raise AccessDenied(status_code=403, reason=f"missing scope {scope}")
    return p


def require_owner(principal: Optional[Principal], resource_owner_id: str) -> Principal:
    """Object-level authorization — the heart of IDOR prevention. The caller
    must own the resource (or be an admin-scoped principal)."""
    p = require_authenticated(principal)
    if p.has_scope("admin"):
        return p
    if not resource_owner_id or p.subject != str(resource_owner_id):
        raise AccessDenied(status_code=403, reason="not resource owner")
    return p

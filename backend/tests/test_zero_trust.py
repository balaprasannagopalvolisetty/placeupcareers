"""
Unit tests for the zero-trust security core (app/zero_trust.py).

These cover the pure-logic surface that needs no DB or running app:
token→principal verification, least-privilege authorization helpers,
object-level ownership (IDOR) checks, the uniform denial payload, and the
auto-ban tracker's window/threshold/expiry behaviour.
"""
from __future__ import annotations

import time

import jwt
import pytest
from starlette.requests import Request

from app.config import settings
from app import zero_trust as zt


# ─── Token → Principal ───────────────────────────────────────────────────────
def _access_token(**overrides) -> str:
    claims = {
        "sub": "user-123",
        "typ": "access",
        "iat": int(time.time()),
        "exp": int(time.time()) + 300,
        "iss": "placeup-career-api",
        "aud": "placeup-career-web",
        "scopes": ["read", "write"],
        "sid": "sess-1",
        "email": "a@b.com",
    }
    claims.update(overrides)
    return jwt.encode(claims, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def test_valid_access_token_yields_principal():
    p = zt.principal_from_access_token(_access_token())
    assert p is not None
    assert p.subject == "user-123"
    assert p.kind == "user"
    assert p.is_authenticated
    assert p.has_scope("read") and p.has_scope("write")
    assert not p.has_scope("admin")


def test_expired_token_rejected():
    assert zt.principal_from_access_token(_access_token(exp=int(time.time()) - 5)) is None


def test_wrong_type_rejected():
    assert zt.principal_from_access_token(_access_token(typ="refresh")) is None


def test_bad_signature_rejected():
    forged = jwt.encode(
        {"sub": "x", "typ": "access", "iat": int(time.time()), "exp": int(time.time()) + 300,
         "iss": "placeup-career-api", "aud": "placeup-career-web"},
        "not-the-real-secret",
        algorithm="HS256",
    )
    assert zt.principal_from_access_token(forged) is None


def test_wrong_audience_rejected():
    assert zt.principal_from_access_token(_access_token(aud="someone-else")) is None


def test_empty_token_rejected():
    assert zt.principal_from_access_token("") is None
    assert zt.principal_from_access_token(None) is None  # type: ignore[arg-type]


def test_admin_is_superscope():
    p = zt.principal_from_access_token(_access_token(scopes=["admin"]))
    assert p is not None
    assert p.has_scope("anything")  # admin implies all


# ─── Service identity ────────────────────────────────────────────────────────
def test_service_token_roundtrip():
    tok = zt.create_service_token("ats-worker", scopes=["jobs:write"])
    p = zt.principal_from_service_token(tok)
    assert p is not None
    assert p.kind == "service"
    assert p.subject == "svc:ats-worker"
    assert p.has_scope("jobs:write")


def test_access_token_not_accepted_as_service():
    # An access token must not authenticate as a service identity.
    assert zt.principal_from_service_token(_access_token()) is None


def test_service_token_not_accepted_as_access():
    tok = zt.create_service_token("scraper")
    assert zt.principal_from_access_token(tok) is None


def test_service_token_header_is_separate_from_cloud_run_iam():
    tok = zt.create_service_token("web-server", scopes=["pipeline"])
    p = zt.principal_from_service_token(tok)

    assert p is not None
    assert p.subject == "svc:web-server"
    assert p.has_scope("pipeline")


def test_internal_api_key_is_valid_for_cloud_tasks_origin_bypass():
    from app.middleware.security import _has_valid_internal_credential

    previous = settings.internal_api_key
    settings.internal_api_key = "test-internal-key"
    try:
        request = Request({
            "type": "http",
            "method": "POST",
            "path": "/api/apply/internal-submit",
            "headers": [(b"x-api-key", b"test-internal-key")],
        })
        assert _has_valid_internal_credential(request) is True
    finally:
        settings.internal_api_key = previous


# ─── Authorization helpers (deny-by-default) ─────────────────────────────────
def test_require_authenticated_rejects_anonymous():
    with pytest.raises(zt.AccessDenied) as e:
        zt.require_authenticated(zt.ANONYMOUS)
    assert e.value.status_code == 401
    with pytest.raises(zt.AccessDenied):
        zt.require_authenticated(None)


def test_require_scope():
    p = zt.principal_from_access_token(_access_token(scopes=["read"]))
    assert zt.require_scope(p, "read") is p
    with pytest.raises(zt.AccessDenied) as e:
        zt.require_scope(p, "write")
    assert e.value.status_code == 403


def test_require_owner_allows_owner():
    p = zt.principal_from_access_token(_access_token(sub="owner-1"))
    assert zt.require_owner(p, "owner-1") is p


def test_require_owner_blocks_other_user():
    p = zt.principal_from_access_token(_access_token(sub="attacker"))
    with pytest.raises(zt.AccessDenied) as e:
        zt.require_owner(p, "victim-id")  # IDOR attempt
    assert e.value.status_code == 403


def test_require_owner_admin_override():
    p = zt.principal_from_access_token(_access_token(sub="admin-user", scopes=["admin"]))
    assert zt.require_owner(p, "someone-elses-resource") is p


# ─── Uniform denial payload ──────────────────────────────────────────────────
def test_denial_body_mentions_contact():
    body = zt.denial_body()
    assert settings.security_contact_email in body["detail"]
    assert body["contact"] == settings.security_contact_email
    assert "retry_after" not in body


def test_denial_body_with_retry():
    body = zt.denial_body(retry_after=120)
    assert body["retry_after"] == 120
    assert "wait" in body["detail"].lower()


# ─── Auto-ban tracker ────────────────────────────────────────────────────────
def test_ban_trips_at_threshold():
    t = zt.BanTracker(threshold=3, window_s=60, ban_s=30)
    assert t.record_failure("1.2.3.4") == 0
    assert t.record_failure("1.2.3.4") == 0
    assert t.record_failure("1.2.3.4") == 30  # third trips it
    assert t.banned_for("1.2.3.4") > 0


def test_ban_isolated_per_ip():
    t = zt.BanTracker(threshold=2, window_s=60, ban_s=30)
    t.record_failure("a")
    assert t.record_failure("a") == 30
    assert t.banned_for("a") > 0
    assert t.banned_for("b") == 0  # different IP unaffected


def test_success_clears_failure_streak():
    t = zt.BanTracker(threshold=3, window_s=60, ban_s=30)
    t.record_failure("ip")
    t.record_failure("ip")
    t.clear("ip")
    assert t.record_failure("ip") == 0  # streak reset, no ban yet
    assert t.record_failure("ip") == 0
    assert t.record_failure("ip") == 30  # takes 3 fresh failures


def test_ban_disabled_when_threshold_zero():
    t = zt.BanTracker(threshold=0, window_s=60, ban_s=30)
    for _ in range(50):
        assert t.record_failure("flood") == 0
    assert t.banned_for("flood") == 0


def test_window_expiry_prevents_ban():
    t = zt.BanTracker(threshold=3, window_s=1, ban_s=30)
    t.record_failure("slow")
    time.sleep(1.1)  # first failure ages out of the window
    t.record_failure("slow")
    assert t.record_failure("slow") == 0  # only 2 within window → no ban
    assert t.banned_for("slow") == 0


def test_empty_ip_never_banned():
    t = zt.BanTracker(threshold=1, window_s=60, ban_s=30)
    assert t.record_failure("") == 0
    assert t.banned_for("") == 0


# ─── Client IP resolution ────────────────────────────────────────────────────
def test_client_ip_prefers_cloudflare():
    assert zt.client_ip({"cf-connecting-ip": "9.9.9.9", "x-forwarded-for": "1.1.1.1"}) == "9.9.9.9"


def test_client_ip_falls_back_to_xff():
    assert zt.client_ip({"x-forwarded-for": "1.1.1.1, 2.2.2.2"}) == "1.1.1.1"


def test_client_ip_empty_when_absent():
    assert zt.client_ip({}) == ""

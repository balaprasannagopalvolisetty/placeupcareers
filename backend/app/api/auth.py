"""
Production-grade authentication for PlaceUp Career.

Uses short-lived bearer JWTs for API access plus rotating refresh tokens
stored as HttpOnly Secure cookies. Refresh token hashes and revocation state
live in Firestore auth_sessions documents.
"""
from __future__ import annotations

import logging
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import httpx
import jwt
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import RedirectResponse

from app.config import settings
from app.db import user_store
from app.models.user import AuthRequest, AuthResponse, SessionResponse, SignupRequest, TokenRefreshResponse, UserProfile
from app.security import (
    REFRESH_COOKIE_NAME,
    create_access_token,
    generate_refresh_token,
    get_refresh_token_from_request,
    hash_password,
    optional_user_id,
    refresh_token_hash,
    verify_password,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["Auth"])


DEMO_EMAIL = "demo@placeup.dev"
DEMO_PASSWORD = "Password123!"
OIDC_STATE_COOKIE = "placeup_oidc_state"
ACCESS_EXPIRES_SECONDS = settings.jwt_expires_minutes * 60


def _client_ip(request: Request) -> str:
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",", 1)[0].strip()
    return request.client.host if request.client else ""


def _refresh_expiry() -> datetime:
    return datetime.now(tz=timezone.utc) + timedelta(days=settings.refresh_token_expires_days)


def _cookie_secure(request: Request | None = None) -> bool:
    if settings.is_production:
        return True
    if request and request.headers.get("x-forwarded-proto") == "https":
        return True
    return False


def _cookie_samesite(request: Request | None = None) -> str:
    # The SPA (placeupcareer.com) and the API (Cloud Run) are on different
    # origins, so the refresh cookie is a cross-site cookie. Browsers only send
    # cross-site cookies when SameSite=None AND Secure. Use "none" whenever the
    # connection is secure (prod/https); fall back to "lax" for local http dev
    # (browsers reject SameSite=None without Secure).
    return "none" if _cookie_secure(request) else "lax"


def _set_refresh_cookie(response: Response, token: str, request: Request | None = None) -> None:
    response.set_cookie(
        REFRESH_COOKIE_NAME,
        token,
        max_age=settings.refresh_token_expires_days * 24 * 60 * 60,
        path="/api/auth",
        secure=_cookie_secure(request),
        httponly=True,
        samesite=_cookie_samesite(request),
    )


def _clear_refresh_cookie(response: Response, request: Request | None = None) -> None:
    response.delete_cookie(
        REFRESH_COOKIE_NAME,
        path="/api/auth",
        secure=_cookie_secure(request),
        httponly=True,
        samesite=_cookie_samesite(request),
    )


def _user_profile(user: dict) -> UserProfile:
    return UserProfile(
        id=user["id"],
        first_name=user.get("first_name") or "",
        last_name=user.get("last_name") or "",
        email=user.get("email") or "",
        phone=user.get("phone"),
        location=user.get("location"),
        visa_status=user.get("visa_status"),
        experience_years=user.get("experience_years"),
        current_role=user.get("current_role"),
        current_company=user.get("current_company"),
        plan=user.get("plan") or "Pro",
        summary=user.get("summary"),
        linkedin_url=user.get("linkedin_url"),
        github_url=user.get("github_url"),
        portfolio_url=user.get("portfolio_url"),
    )


def _trusted_origin(request: Request) -> bool:
    origin = request.headers.get("origin")
    if not origin:
        return True
    return origin.rstrip("/") in {item.rstrip("/") for item in settings.cors_origins}


def _enforce_trusted_origin(request: Request) -> None:
    if not _trusted_origin(request):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Untrusted request origin")


def _issue_session(user: dict, request: Request, response: Response) -> AuthResponse:
    refresh_token = generate_refresh_token()
    session = user_store.create_auth_session(
        user["id"],
        refresh_hash=refresh_token_hash(refresh_token),
        expires_at=_refresh_expiry(),
        user_agent=request.headers.get("user-agent", ""),
        ip_address=_client_ip(request),
    )
    _set_refresh_cookie(response, refresh_token, request)
    token = create_access_token(
        user_id=user["id"],
        email=user["email"],
        plan=user.get("plan") or "Pro",
        session_id=session["id"],
    )
    return AuthResponse(
        access_token=token,
        expires_in=ACCESS_EXPIRES_SECONDS,
        user_id=user["id"],
        email=user["email"],
        first_name=user.get("first_name") or "",
        last_name=user.get("last_name") or "",
        plan=user.get("plan") or "Pro",
    )


def _issue_redirect_session(user: dict, request: Request, redirect_to: str) -> RedirectResponse:
    response = RedirectResponse(redirect_to, status_code=status.HTTP_302_FOUND)
    _issue_session(user, request, response)
    return response


def _google_redirect_uri(request: Request) -> str:
    if settings.oidc_google_redirect_uri:
        return settings.oidc_google_redirect_uri
    generated = str(request.url_for("google_oidc_callback"))
    if request.headers.get("x-forwarded-proto") == "https":
        generated = generated.replace("http://", "https://", 1)
    return generated


def _frontend_redirect(path: str = "/dashboard") -> str:
    base = settings.frontend_url.split(",", 1)[0].strip().rstrip("/")
    return f"{base}{path}"


def _ensure_demo_user() -> dict:
    """Idempotent demo-user seed. Returns the user row."""
    user = user_store.get_user_by_email(DEMO_EMAIL)
    if user:
        if not verify_password(DEMO_PASSWORD, user.get("password_hash", "")):
            user_store.set_user_password(user["id"], hash_password(DEMO_PASSWORD))
            logger.info("Demo user password reset to default")
            user = user_store.get_user_by_email(DEMO_EMAIL)
        return user

    user = user_store.create_user(
        email=DEMO_EMAIL,
        password_hash=hash_password(DEMO_PASSWORD),
        first_name="Demo",
        last_name="Candidate",
        visa_status="F1-OPT",
        experience_years="3-5 years",
    )
    user_store.update_user_profile(
        user["id"],
        {
            "phone": "+1 (555) 012-3456",
            "location": "San Francisco, CA",
            "current_role": "Senior Software Engineer",
            "summary": "Experienced full-stack engineer focused on growth-stage product delivery.",
            "linkedin_url": "https://linkedin.com/in/demo-candidate",
            "github_url": "https://github.com/demo-candidate",
            "portfolio_url": "https://demo.placeup.dev",
        },
    )
    user_store.update_preferences(
        user["id"],
        {
            "job_preferences": "Senior Frontend / Full Stack roles at mid-to-large tech companies.",
            "notification_new_jobs": True,
            "notification_daily_digest": True,
            "notification_ats_updates": True,
        },
    )
    logger.info("Demo user seeded: %s", DEMO_EMAIL)
    return user_store.get_user_by_email(DEMO_EMAIL)


@router.get("/demo")
async def get_demo_credentials():
    """Return demo credentials and seed the demo account if missing."""
    if settings.is_production:
        raise HTTPException(status_code=404, detail="Not available in production")
    _ensure_demo_user()
    return {
        "email": DEMO_EMAIL,
        "password": DEMO_PASSWORD,
        "note": "Pre-seeded test account. Not available in production.",
    }


@router.post("/signin", response_model=AuthResponse)
async def signin(payload: AuthRequest, request: Request, response: Response):
    _enforce_trusted_origin(request)
    identifier = str(payload.email).strip()
    if not settings.is_production and identifier.lower() == DEMO_EMAIL and payload.password == DEMO_PASSWORD:
        _ensure_demo_user()
    if "@" in identifier:
        user = user_store.get_user_by_email(identifier)
    else:
        user = user_store.get_user_by_phone(identifier)
    if not user or not verify_password(payload.password, user.get("password_hash", "")):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email/phone or password",
        )
    return _issue_session(user, request, response)


@router.post("/signup", response_model=AuthResponse)
async def signup(payload: SignupRequest, request: Request, response: Response):
    _enforce_trusted_origin(request)
    if user_store.get_user_by_email(str(payload.email)):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")

    user = user_store.create_user(
        email=str(payload.email),
        password_hash=hash_password(payload.password),
        first_name=payload.first_name,
        last_name=payload.last_name,
        visa_status=payload.visa_status,
        experience_years=payload.experience_level,
    )

    profile_updates = {
        k: v for k, v in {
            "phone": payload.phone,
            "current_role": payload.current_role,
            "current_company": payload.current_company,
            "location": payload.location,
            "linkedin_url": payload.linkedin_url,
        }.items() if v
    }
    if profile_updates:
        user_store.update_user_profile(user["id"], profile_updates)
        user = user_store.get_user_by_id(user["id"]) or user

    target_roles = list(payload.target_roles or payload.targets or [])[:25]
    pref_updates: dict = {}
    if target_roles:
        pref_updates["target_roles"] = target_roles
    if payload.target_locations:
        pref_updates["target_locations"] = list(payload.target_locations)
    if payload.visa_status:
        pref_updates["visa_status"] = payload.visa_status
    if payload.experience_level:
        pref_updates["experience_level"] = payload.experience_level
    if pref_updates:
        user_store.update_preferences(user["id"], pref_updates)

    return _issue_session(user, request, response)


@router.get("/session", response_model=SessionResponse)
async def session(user_id: str | None = Depends(optional_user_id)):
    if not user_id:
        return SessionResponse(authenticated=False)
    user = user_store.get_user_by_id(user_id)
    if not user:
        return SessionResponse(authenticated=False)
    return SessionResponse(authenticated=True, user=_user_profile(user))


@router.post("/refresh", response_model=TokenRefreshResponse)
async def refresh_token(
    request: Request,
    response: Response,
    refresh_token_value: str = Depends(get_refresh_token_from_request),
):
    _enforce_trusted_origin(request)
    session = user_store.get_auth_session_by_refresh_hash(refresh_token_hash(refresh_token_value))
    if not session:
        _clear_refresh_cookie(response, request)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh session expired")
    user = user_store.get_user_by_id(session["user_id"])
    if not user:
        user_store.revoke_auth_session(session["id"])
        _clear_refresh_cookie(response, request)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh session user not found")

    new_refresh_token = generate_refresh_token()
    user_store.rotate_auth_session(
        session["id"],
        refresh_hash=refresh_token_hash(new_refresh_token),
        expires_at=_refresh_expiry(),
    )
    _set_refresh_cookie(response, new_refresh_token, request)
    access_token = create_access_token(
        user_id=user["id"],
        email=user["email"],
        plan=user.get("plan") or "Pro",
        session_id=session["id"],
    )
    return TokenRefreshResponse(access_token=access_token, expires_in=ACCESS_EXPIRES_SECONDS)


@router.post("/logout")
async def logout(
    request: Request,
    response: Response,
):
    _enforce_trusted_origin(request)
    refresh_token_value = request.cookies.get(REFRESH_COOKIE_NAME)
    if refresh_token_value:
        session = user_store.get_auth_session_by_refresh_hash(refresh_token_hash(refresh_token_value))
        if session:
            user_store.revoke_auth_session(session["id"])
    _clear_refresh_cookie(response, request)
    return {"ok": True}


@router.post("/logout-all")
async def logout_all(request: Request, response: Response, user_id: str | None = Depends(optional_user_id)):
    _enforce_trusted_origin(request)
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")
    revoked = user_store.revoke_user_sessions(user_id)
    _clear_refresh_cookie(response, request)
    return {"ok": True, "revoked": revoked}


@router.get("/oidc/providers")
async def oidc_providers():
    return {
        "google": bool(settings.oidc_google_client_id and settings.oidc_google_client_secret),
    }


@router.get("/oidc/google/start")
async def google_oidc_start(request: Request):
    if not settings.oidc_google_client_id or not settings.oidc_google_client_secret:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Google OIDC is not configured")
    state = secrets.token_urlsafe(32)
    params = {
        "client_id": settings.oidc_google_client_id,
        "redirect_uri": _google_redirect_uri(request),
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "prompt": "select_account",
    }
    response = RedirectResponse(f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}")
    response.set_cookie(
        OIDC_STATE_COOKIE,
        state,
        max_age=300,
        path="/api/auth",
        secure=_cookie_secure(request),
        httponly=True,
        samesite="lax",
    )
    return response


@router.get("/oidc/google/callback", name="google_oidc_callback")
async def google_oidc_callback(
    request: Request,
    code: str = Query(...),
    state: str = Query(...),
):
    expected_state = request.cookies.get(OIDC_STATE_COOKIE)
    if not expected_state or not secrets.compare_digest(expected_state, state):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid OIDC state")
    redirect_uri = _google_redirect_uri(request)
    async with httpx.AsyncClient(timeout=15) as client:
        token_response = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": code,
                "client_id": settings.oidc_google_client_id,
                "client_secret": settings.oidc_google_client_secret,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            },
        )
    if token_response.status_code >= 400:
        logger.warning("Google OIDC token exchange failed: %s", token_response.text[:300])
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Google sign-in failed")

    id_token = token_response.json().get("id_token")
    if not id_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Google sign-in missing identity token")
    try:
        key_client = jwt.PyJWKClient("https://www.googleapis.com/oauth2/v3/certs")
        signing_key = key_client.get_signing_key_from_jwt(id_token)
        claims = jwt.decode(
            id_token,
            signing_key.key,
            algorithms=["RS256"],
            audience=settings.oidc_google_client_id,
            issuer="https://accounts.google.com",
        )
    except jwt.InvalidTokenError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"Invalid Google identity token: {exc}")

    if not claims.get("email_verified"):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Google email is not verified")
    email = str(claims.get("email") or "").lower()
    if not email:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Google account has no email")

    user = user_store.get_user_by_email(email)
    if not user:
        user = user_store.create_user(
            email=email,
            password_hash=hash_password(secrets.token_urlsafe(48)),
            first_name=str(claims.get("given_name") or "PlaceUp"),
            last_name=str(claims.get("family_name") or "User"),
        )
    else:
        profile_updates: dict[str, str] = {}
        if claims.get("given_name") and not user.get("first_name"):
            profile_updates["first_name"] = str(claims["given_name"])
        if claims.get("family_name") and not user.get("last_name"):
            profile_updates["last_name"] = str(claims["family_name"])
        if profile_updates:
            user = user_store.update_user_profile(user["id"], profile_updates) or user

    response = _issue_redirect_session(user, request, _frontend_redirect("/dashboard"))
    response.delete_cookie(
        OIDC_STATE_COOKIE,
        path="/api/auth",
        secure=_cookie_secure(request),
        httponly=True,
        samesite="lax",
    )
    return response

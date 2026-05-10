"""
Production-grade authentication for PlaceUp Career.

Issues HS256 JWT access tokens after verifying credentials against the
SQLite-backed `users` table. Passwords are stored as bcrypt hashes via
`app.security.hash_password`.
"""
import logging
from fastapi import APIRouter, HTTPException, status

from app.config import settings
from app.db import user_store
from app.models.user import AuthRequest, AuthResponse, SignupRequest
from app.security import (
    create_access_token,
    hash_password,
    verify_password,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["Auth"])


DEMO_EMAIL = "demo@placeup.dev"
DEMO_PASSWORD = "Password123!"


def _build_auth_response(user: dict) -> AuthResponse:
    token = create_access_token(
        user_id=user["id"],
        email=user["email"],
        plan=user.get("plan") or "Pro",
    )
    return AuthResponse(
        access_token=token,
        user_id=user["id"],
        email=user["email"],
        first_name=user["first_name"],
        last_name=user["last_name"],
        plan=user.get("plan") or "Pro",
    )


def _ensure_demo_user() -> dict:
    """Idempotent demo-user seed. Returns the user row."""
    user = user_store.get_user_by_email(DEMO_EMAIL)
    if user:
        # If somehow the password was rotated, reset it so the published
        # demo creds always work in dev/staging.
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
    logger.info(f"Demo user seeded: {DEMO_EMAIL}")
    return user_store.get_user_by_email(DEMO_EMAIL)


@router.get("/demo")
async def get_demo_credentials():
    """Return demo credentials and seed the demo account if missing.

    Disabled in production (404). Idempotent — repeated calls just return
    the same creds. The frontend SignIn page calls this on mount and shows
    a one-click sign-in button if the response is 200.
    """
    if settings.is_production:
        raise HTTPException(status_code=404, detail="Not available in production")
    _ensure_demo_user()
    return {
        "email": DEMO_EMAIL,
        "password": DEMO_PASSWORD,
        "note": "Pre-seeded test account. Not available in production.",
    }


@router.post("/signin", response_model=AuthResponse)
async def signin(payload: AuthRequest):
    email = str(payload.email)
    # Self-heal: if the demo user is requested but missing/wrong-password
    # in dev, ensure it exists so the published creds always work.
    if not settings.is_production and email.lower() == DEMO_EMAIL and payload.password == DEMO_PASSWORD:
        _ensure_demo_user()
    user = user_store.get_user_by_email(email)
    if not user or not verify_password(payload.password, user.get("password_hash", "")):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )
    return _build_auth_response(user)


@router.post("/signup", response_model=AuthResponse)
async def signup(payload: SignupRequest):
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

    # Persist the richer profile fields collected during signup.
    profile_updates = {
        k: v for k, v in {
            "current_role": payload.current_role,
            "current_company": payload.current_company,
            "location": payload.location,
            "linkedin_url": payload.linkedin_url,
        }.items() if v
    }
    if profile_updates:
        user_store.update_user_profile(user["id"], profile_updates)
        user = user_store.get_user_by_id(user["id"]) or user

    # Persist preferences (top-5 target roles + target locations).
    target_roles = list(payload.target_roles or payload.targets or [])[:5]
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

    return _build_auth_response(user)

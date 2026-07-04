"""
Authentication primitives — bcrypt password hashing and HS256 JWT.

We call bcrypt directly (not via passlib) because passlib 1.7.x is
incompatible with bcrypt >= 4.x and triggers spurious "password cannot
be longer than 72 bytes" errors on perfectly normal passwords.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import secrets
from typing import Optional

import bcrypt
import jwt
from fastapi import Cookie, Header, HTTPException, Request, status

from app.db import user_store
from app.config import settings


# Bcrypt's hard limit is 72 bytes; truncate longer inputs deterministically
# so we never crash. Anything < 72 bytes (the typical case) is unaffected.
def _to_bytes(plain: str) -> bytes:
    data = plain.encode("utf-8")
    return data[:72]


def hash_password(plain: str) -> str:
    """Hash a plaintext password with bcrypt and return the encoded hash."""
    salt = bcrypt.gensalt(rounds=12)
    hashed = bcrypt.hashpw(_to_bytes(plain), salt)
    return hashed.decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """Constant-time compare of plaintext against a stored bcrypt hash."""
    if not plain or not hashed:
        return False
    try:
        return bcrypt.checkpw(_to_bytes(plain), hashed.encode("utf-8"))
    except Exception:
        return False


REFRESH_COOKIE_NAME = "placeup_refresh"


def refresh_token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def generate_refresh_token() -> str:
    return secrets.token_urlsafe(48)


def create_access_token(user_id: str, email: str, *, plan: str = "Pro", session_id: str | None = None) -> str:
    """Mint a signed JWT carrying the user identity and plan claim."""
    now = datetime.now(tz=timezone.utc)
    payload = {
        "sub": user_id,
        "email": email,
        "plan": plan,
        "typ": "access",
        "sid": session_id,
        "jti": secrets.token_urlsafe(16),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=settings.jwt_expires_minutes)).timestamp()),
        "iss": "placeup-career-api",
        "aud": "placeup-career-web",
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_invite_token() -> str:
    """Mint a short-lived signed token proving the bearer entered a valid
    invite code. The frontend holds it in sessionStorage and attaches it to
    the signup payload; /api/auth/signup refuses to create accounts without
    it while the invite gate is on. Because it's HMAC-signed server-side,
    scraping the frontend bundle reveals nothing."""
    now = datetime.now(tz=timezone.utc)
    payload = {
        "typ": "invite",
        "jti": secrets.token_urlsafe(16),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=settings.invite_token_ttl_minutes)).timestamp()),
        "iss": "placeup-career-api",
        "aud": "placeup-career-web",
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def verify_invite_token(token: str) -> bool:
    """True only for an unexpired, correctly signed invite token."""
    if not token:
        return False
    try:
        claims = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            audience="placeup-career-web",
            issuer="placeup-career-api",
        )
        return claims.get("typ") == "invite"
    except jwt.InvalidTokenError:
        return False


def decode_access_token(token: str) -> dict:
    """Decode + verify a token. Raises 401 if invalid or expired."""
    try:
        claims = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            audience="placeup-career-web",
            issuer="placeup-career-api",
        )
        if claims.get("typ") != "access":
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token type")
        return claims
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired")
    except jwt.InvalidTokenError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"Invalid token: {exc}")


async def current_user_id(
    authorization: Optional[str] = Header(default=None, alias="Authorization"),
) -> str:
    """FastAPI dependency: extract the user id from the bearer token."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid Authorization header",
        )
    token = authorization.split(" ", 1)[1].strip()
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Empty token")
    claims = decode_access_token(token)
    user_id = claims.get("sub")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token missing sub claim")
    if not user_store.get_user_by_id(str(user_id)):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User no longer exists")
    session_id = claims.get("sid")
    if session_id and not user_store.get_auth_session(str(session_id)):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired or revoked")
    return str(user_id)


def get_refresh_token_from_request(
    request: Request,
    refresh_cookie: Optional[str] = Cookie(default=None, alias=REFRESH_COOKIE_NAME),
) -> str:
    if refresh_cookie:
        return refresh_cookie
    bearer = request.headers.get("Authorization", "")
    if bearer.lower().startswith("bearer "):
        token = bearer.split(" ", 1)[1].strip()
        if token:
            return token
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing refresh token")


def require_internal_api_key(x_api_key: Optional[str] = Header(default=None, alias="X-API-Key")) -> None:
    if not settings.internal_api_key:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Internal API key is not configured")
    if not x_api_key or not secrets.compare_digest(x_api_key, settings.internal_api_key):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid internal API key")


async def optional_user_id(
    authorization: Optional[str] = Header(default=None, alias="Authorization"),
) -> Optional[str]:
    """FastAPI dependency: extract user id if a token is present, else None."""
    if not authorization or not authorization.lower().startswith("bearer "):
        return None
    try:
        return await current_user_id(authorization=authorization)
    except HTTPException:
        return None

"""Web server -> Application server internal client.

The only sanctioned way to talk to the application server. Mints a
short-lived service identity token (zero_trust.create_service_token) for
every call, so the app server's ServiceOnlyGateMiddleware can verify the
request really came from the web tier — network position is never trusted.

Usage (from a web-server route/worker):

    from app.services.internal_client import call_app_server

    resp = call_app_server("/api/admin/scrape/run", method="POST",
                           json={"country": "DE"}, scopes=("pipeline",))
"""

from __future__ import annotations

import logging
from typing import Any, Iterable, Optional

import httpx

from app.config import settings
from app.zero_trust import create_service_token

log = logging.getLogger("placeup.internal_client")

_SERVICE_NAME = "web-server"


class AppServerNotConfigured(RuntimeError):
    """Raised when APP_SERVER_URL is not set on this instance."""


def _base_url() -> str:
    url = (settings.app_server_url or "").rstrip("/")
    if not url:
        raise AppServerNotConfigured(
            "APP_SERVER_URL is not configured; web->app calls are disabled."
        )
    return url


def _headers(scopes: Iterable[str]) -> dict[str, str]:
    """Build Cloud Run IAM + application-level service identity headers."""
    service_token = create_service_token(_SERVICE_NAME, scopes=scopes)
    headers = {"X-Service-Token": service_token}
    if settings.app_server_iam_auth:
        try:
            from google.auth.transport.requests import Request
            from google.oauth2 import id_token

            headers["Authorization"] = f"Bearer {id_token.fetch_id_token(Request(), _base_url())}"
        except Exception as exc:  # noqa: BLE001
            log.warning("could not mint Cloud Run ID token for app-server call: %s", exc)
    else:
        headers["Authorization"] = f"Bearer {service_token}"
    return headers


def call_app_server(
    path: str,
    *,
    method: str = "POST",
    json: Optional[dict[str, Any]] = None,
    params: Optional[dict[str, Any]] = None,
    scopes: Iterable[str] = ("pipeline",),
    timeout_seconds: float = 30.0,
) -> httpx.Response:
    """Synchronous call to the application server with a fresh service token."""
    url = f"{_base_url()}/{path.lstrip('/')}"
    with httpx.Client(timeout=timeout_seconds) as client:
        response = client.request(
            method.upper(),
            url,
            json=json,
            params=params,
            headers=_headers(scopes),
        )
    if response.status_code >= 400:
        log.warning(
            "app-server call failed: %s %s -> %s", method, path, response.status_code
        )
    return response


async def call_app_server_async(
    path: str,
    *,
    method: str = "POST",
    json: Optional[dict[str, Any]] = None,
    params: Optional[dict[str, Any]] = None,
    scopes: Iterable[str] = ("pipeline",),
    timeout_seconds: float = 30.0,
) -> httpx.Response:
    """Async variant for FastAPI request handlers."""
    url = f"{_base_url()}/{path.lstrip('/')}"
    async with httpx.AsyncClient(timeout=timeout_seconds) as client:
        response = await client.request(
            method.upper(),
            url,
            json=json,
            params=params,
            headers=_headers(scopes),
        )
    if response.status_code >= 400:
        log.warning(
            "app-server call failed: %s %s -> %s", method, path, response.status_code
        )
    return response

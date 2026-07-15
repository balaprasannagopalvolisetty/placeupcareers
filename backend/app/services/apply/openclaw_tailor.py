"""Private client for the separately deployed OpenClaw tailoring service.

The public PlaceUp API never starts an OpenClaw gateway and never exposes its
port. Production calls use a Google-signed identity token for the private
Cloud Run service plus an application-level service token.
"""
from __future__ import annotations

import asyncio
import logging
from urllib.parse import urlparse

import httpx

from app.config import settings

log = logging.getLogger("placeup.apply.openclaw")


def _identity_token(audience: str) -> str:
    from google.auth.transport.requests import Request
    from google.oauth2 import id_token

    return id_token.fetch_id_token(Request(), audience)


async def tailor_with_openclaw(*, resume_text: str, job: dict, profile: dict) -> dict | None:
    """Return validated OpenClaw output or ``None`` for safe fallback."""
    url = settings.openclaw_tailor_url.strip().rstrip("/")
    if not settings.openclaw_tailor_enabled or not url or not resume_text.strip():
        return None

    headers = {"Content-Type": "application/json"}
    if settings.openclaw_tailor_token:
        headers["X-Service-Token"] = settings.openclaw_tailor_token
    if (urlparse(url).hostname or "").endswith(".run.app"):
        try:
            headers["Authorization"] = f"Bearer {await asyncio.to_thread(_identity_token, url)}"
        except Exception as exc:
            log.warning("OpenClaw identity token unavailable: %s", exc)
            return None

    payload = {
        "resume_text": resume_text[:150_000],
        "job": {
            "id": str(job.get("id") or job.get("job_id") or ""),
            "title": str(job.get("title") or ""),
            "company": str(job.get("company") or ""),
            "description": str(job.get("description") or job.get("job_description") or "")[:100_000],
        },
        "candidate": {
            "name": str(profile.get("full_name") or profile.get("name") or ""),
            "work_authorization": str(profile.get("visa_status") or profile.get("work_authorization") or ""),
        },
        "rules": {"truth_only": True, "no_new_numeric_claims": True, "output": "json"},
    }
    try:
        async with httpx.AsyncClient(timeout=settings.openclaw_tailor_timeout_seconds) as client:
            response = await client.post(f"{url}/v1/tailor", headers=headers, json=payload)
        response.raise_for_status()
        if len(response.content) > 2_000_000:
            raise ValueError("OpenClaw response exceeded size limit")
        data = response.json()
        spec = data.get("resume_spec")
        cover = data.get("cover_letter")
        from app.services.resume_tailor_llm import _valid

        if not isinstance(spec, dict) or not _valid(spec, resume_text):
            raise ValueError("OpenClaw returned an invalid or ungrounded resume spec")
        return {"resume_spec": spec, "cover_letter": str(cover or "").strip()}
    except Exception as exc:
        log.warning("OpenClaw tailoring unavailable; using standard fallback: %s", exc)
        return None

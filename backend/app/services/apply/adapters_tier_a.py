"""
Tier A candidate-facing ATS apply adapters.

Phase 0 ships Greenhouse, Ashby, SmartRecruiters, Workable, Recruitee — the
near-turnkey, near-zero-ban-risk platforms. Teamtailor, JazzHR and Phenom are
partner-auth adapters: their mapping logic is complete, but `submit` refuses
until a partner token is configured, so the orchestrator falls back to the
browser path instead of failing.

Each adapter's `build_payload` is a PURE function (no network) so the mapping
is unit-testable. `submit` is the only method that touches the network and only
runs after the human approval gate.

Verify against live docs before launch (see caveats in tiers.py).
"""
from __future__ import annotations

import logging
from typing import Optional
from urllib.parse import urlparse

from app.services.apply.base import (
    ApplyResult,
    BaseATSAdapter,
    PreparedPayload,
    register_adapter,
)

log = logging.getLogger("placeup.apply")

# Loaded lazily so importing this module never forces httpx at import time.
try:  # pragma: no cover - trivial import guard
    import httpx
except Exception:  # pragma: no cover
    httpx = None  # type: ignore

_HTTP_TIMEOUT = 20.0


def _base_contact(profile: dict, answers: dict[str, str]) -> dict:
    fields = {
        "first_name": profile.get("first_name") or "",
        "last_name": profile.get("last_name") or "",
        "email": profile.get("email") or "",
        "phone": profile.get("phone") or "",
        "linkedin_url": profile.get("linkedin_url") or "",
    }
    fields.update({k: v for k, v in (answers or {}).items() if v})
    return fields


def _require(payload: PreparedPayload, *names: str) -> None:
    for n in names:
        if not payload.fields.get(n):
            payload.missing_required.append(n)


@register_adapter("greenhouse")
class GreenhouseAdapter(BaseATSAdapter):
    endpoint_template = "https://boards-api.greenhouse.io/v1/boards/{token}/jobs/{id}"

    def build_payload(self, job, profile, answers, resume_url, cover_letter_url, schema=None):
        token = job.get("board_token") or job.get("company_slug") or ""
        job_ref = job.get("ats_job_id") or job.get("external_id") or ""
        p = PreparedPayload(
            ats_type=self.ats_type,
            endpoint=self.endpoint_template.format(token=token, id=job_ref),
        )
        p.fields = _base_contact(profile, answers)
        if resume_url:
            p.attachments["resume"] = resume_url          # sent Base64/multipart
        if cover_letter_url:
            p.attachments["cover_letter"] = cover_letter_url
        # Greenhouse does NOT validate required fields server-side — we must.
        _require(p, "first_name", "last_name", "email")
        p.notes.append(
            "Greenhouse Job Board API does not validate required fields "
            "server-side; validation enforced client-side here."
        )
        return p

    async def submit(self, payload: PreparedPayload) -> ApplyResult:  # pragma: no cover - network
        if httpx is None:
            return ApplyResult(ok=False, message="httpx unavailable")
        # Real submit posts multipart with Base64 resume + a Job Board API key.
        # Left as an explicit integration point; never auto-called without
        # approval by the orchestrator.
        raise NotImplementedError("Greenhouse submit requires a configured Job Board key")


@register_adapter("ashby")
class AshbyAdapter(BaseATSAdapter):
    endpoint_template = "https://api.ashbyhq.com/applicationForm.submit"

    def build_payload(self, job, profile, answers, resume_url, cover_letter_url, schema=None):
        p = PreparedPayload(ats_type=self.ats_type, endpoint=self.endpoint_template)
        p.fields = _base_contact(profile, answers)
        p.fields["jobPostingId"] = job.get("ats_job_id") or job.get("external_id") or ""
        if resume_url:
            p.attachments["resume"] = resume_url
        if cover_letter_url:
            p.attachments["cover_letter"] = cover_letter_url
        _require(p, "first_name", "last_name", "email")
        return p

    async def submit(self, payload: PreparedPayload) -> ApplyResult:  # pragma: no cover
        raise NotImplementedError("Ashby submit requires candidatesWrite credentials")


@register_adapter("smartrecruiters")
class SmartRecruitersAdapter(BaseATSAdapter):
    endpoint_template = "https://api.smartrecruiters.com/v1/postings/{uuid}/candidates"

    def build_payload(self, job, profile, answers, resume_url, cover_letter_url, schema=None):
        uuid = job.get("ats_job_id") or job.get("external_id") or ""
        p = PreparedPayload(
            ats_type=self.ats_type,
            endpoint=self.endpoint_template.format(uuid=uuid),
        )
        p.fields = _base_contact(profile, answers)
        if resume_url:
            p.attachments["resume"] = resume_url
        if cover_letter_url:
            p.attachments["cover_letter"] = cover_letter_url
        # SmartRecruiters: EEO/diversity questions must be presented AFTER all
        # others, and privacy-policy consent must be recorded.
        for k in list(p.fields.keys()):
            if k.startswith("eeo_") or k in ("gender", "race_ethnicity", "veteran_status", "disability_status"):
                p.eeo_fields[k] = p.fields.pop(k)
        p.notes.append("Record privacy-policy consent; render EEO fields last.")
        _require(p, "first_name", "last_name", "email")
        return p

    async def submit(self, payload: PreparedPayload) -> ApplyResult:  # pragma: no cover
        raise NotImplementedError("SmartRecruiters submit requires Application API auth")


@register_adapter("workable")
class WorkableAdapter(BaseATSAdapter):
    endpoint_template = "https://apply.workable.com/api/v3/accounts/{account}/jobs/{shortcode}/candidates"

    def build_payload(self, job, profile, answers, resume_url, cover_letter_url, schema=None):
        p = PreparedPayload(
            ats_type=self.ats_type,
            endpoint=self.endpoint_template.format(
                account=job.get("board_token") or job.get("company_slug") or "",
                shortcode=job.get("ats_job_id") or job.get("external_id") or "",
            ),
        )
        p.fields = _base_contact(profile, answers)
        if resume_url:
            p.attachments["resume"] = resume_url
        if cover_letter_url:
            p.attachments["cover_letter"] = cover_letter_url
        _require(p, "first_name", "last_name", "email")
        return p

    async def submit(self, payload: PreparedPayload) -> ApplyResult:  # pragma: no cover
        raise NotImplementedError("Workable submit requires candidate-create API auth")


@register_adapter("recruitee")
class RecruiteeAdapter(BaseATSAdapter):
    """The ideal case: fully open, no-auth, candidate-facing apply API."""

    endpoint_template = "https://{company}.recruitee.com/api/offers/{slug}/candidates"

    def build_payload(self, job, profile, answers, resume_url, cover_letter_url, schema=None):
        company = job.get("board_token") or job.get("company_slug") or ""
        slug = job.get("ats_slug") or job.get("ats_job_id") or job.get("external_id") or ""
        p = PreparedPayload(
            ats_type=self.ats_type,
            endpoint=self.endpoint_template.format(company=company, slug=slug),
        )
        p.fields = _base_contact(profile, answers)
        full = f"{p.fields.get('first_name','')} {p.fields.get('last_name','')}".strip()
        p.fields["name"] = full
        if resume_url:
            p.attachments["resume"] = resume_url
        if cover_letter_url:
            p.attachments["cover_letter"] = cover_letter_url
        # Recruitee requires name/email for every offer and defaults phone/CV
        # to required. Be conservative so review catches missing phone before
        # a real submission; BaseATSAdapter.validate enforces the resume.
        _require(p, "name", "email", "phone")
        p.notes.append("Recruitee public Careers Site API accepts no-auth candidate POSTs.")
        return p

    async def submit(self, payload: PreparedPayload) -> ApplyResult:
        """Submit the application to Recruitee's public Careers Site API
        (`POST /offers/{slug}/candidates`, no auth). Sends the candidate JSON;
        uploads the private GCS document as multipart `candidate[cv]`.

        Gated by APPLY_LIVE_SUBMIT_ENABLED: when off, everything is prepared and
        validated but no POST is made (dry-run), so a deploy can't fire real
        applications by accident.
        """
        if httpx is None:
            return ApplyResult(ok=False, message="httpx unavailable")

        from app.config import settings
        from app.services.apply import doc_storage

        parsed_endpoint = urlparse(payload.endpoint)
        host = (parsed_endpoint.hostname or "").lower()
        if (
            parsed_endpoint.scheme != "https"
            or not host.endswith(".recruitee.com")
            or host == "recruitee.com"
            or not parsed_endpoint.path.startswith("/api/offers/")
            or not parsed_endpoint.path.endswith("/candidates")
        ):
            return ApplyResult(ok=False, message="Invalid Recruitee candidate endpoint")

        f = payload.fields or {}
        candidate = {
            "name": (f.get("name") or f"{f.get('first_name','')} {f.get('last_name','')}").strip(),
            "email": f.get("email") or "",
            "phone": f.get("phone") or "",
        }
        if f.get("cover_letter"):
            candidate["cover_letter"] = f["cover_letter"]
        if not candidate["name"] or not candidate["email"] or not candidate["phone"]:
            return ApplyResult(ok=False, message="Recruitee requires name + email + phone")

        # Resolve the private CV server-side. Production attachments are gs://
        # references and are never exposed through public/signed URLs.
        resume_uri = (payload.attachments or {}).get("resume") or ""
        if not resume_uri:
            return ApplyResult(ok=False, message="Recruitee requires a tailored CV")

        # --- Dry-run (safety default) ---
        if not settings.apply_live_submit_enabled:
            return ApplyResult(
                ok=True,
                confirmation_ref="DRYRUN",
                message="Dry-run: validated, not submitted (APPLY_LIVE_SUBMIT_ENABLED=false).",
                dry_run=True,
            )

        # --- Live submission ---
        cv_bytes = doc_storage.read_document(resume_uri)
        if not cv_bytes:
            return ApplyResult(ok=False, message="Recruitee requires an accessible tailored CV")
        try:  # pragma: no cover - network
            async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
                data = {f"candidate[{k}]": v for k, v in candidate.items() if v not in (None, "")}
                files = {"candidate[cv]": ("resume.pdf", cv_bytes, "application/pdf")}
                # Recruitee recommends async=true for heavy files such as PDFs.
                endpoint = str(httpx.URL(payload.endpoint).copy_add_param("async", "true"))
                resp = await client.post(endpoint, data=data, files=files)
        except httpx.HTTPError as exc:  # pragma: no cover - network
            return ApplyResult(ok=False, message=f"Recruitee request failed: {exc}")

        if resp.status_code == 201:  # pragma: no cover - network
            try:
                data = resp.json()
                ref = str((data.get("candidate") or data).get("id") or "")
            except Exception:
                ref = ""
            return ApplyResult(ok=True, confirmation_ref=ref or "submitted", message="Submitted to Recruitee.")
        if resp.status_code == 422:  # pragma: no cover - network
            return ApplyResult(ok=False, message=f"Recruitee validation error: {resp.text[:300]}")
        return ApplyResult(ok=False, message=f"Recruitee returned {resp.status_code}: {resp.text[:200]}")


class _PartnerAuthAdapter(BaseATSAdapter):
    """Tier A but needs a partner/token relationship we may not hold. Mapping
    works; submit refuses so the orchestrator falls back to browser."""

    partner_auth = True

    async def submit(self, payload: PreparedPayload) -> ApplyResult:  # pragma: no cover
        return ApplyResult(
            ok=False,
            needs_you=False,
            message=f"{self.ats_type} is partner-auth; no token configured — route to browser worker.",
        )


@register_adapter("teamtailor")
class TeamtailorAdapter(_PartnerAuthAdapter):
    pass


@register_adapter("jazzhr")
class JazzHRAdapter(_PartnerAuthAdapter):
    pass


@register_adapter("phenom")
class PhenomAdapter(_PartnerAuthAdapter):
    endpoint_template = "https://.../apply/v2/applications"

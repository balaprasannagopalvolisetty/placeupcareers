"""
Tier A ATS adapter framework.

Each Tier A platform gets one adapter subclass. An adapter does three things:

    1. resolve_schema(job)   -> fetch the live application form / question set
    2. build_payload(...)    -> map the user's profile+answers onto that schema
    3. submit(payload)       -> POST to the candidate-facing apply API

`build_payload` is always run BEFORE the human review gate; `submit` only runs
after the user approves (orchestrator enforces this). Adapters must validate
required fields themselves — e.g. Greenhouse's Job Board endpoint does not
validate required fields server-side.

Adapters register themselves via `@register_adapter("greenhouse")`. The
registry is keyed by the same normalized ats_type used in `tiers.py`.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

log = logging.getLogger("placeup.apply")

# Registry of Tier A adapters, keyed by normalized ats_type.
TIER_A_ADAPTERS: dict[str, "BaseATSAdapter"] = {}


@dataclass
class PreparedPayload:
    """The exact thing an adapter intends to submit, shown verbatim in review."""

    ats_type: str
    endpoint: str = ""
    fields: dict[str, Any] = field(default_factory=dict)
    attachments: dict[str, str] = field(default_factory=dict)  # name -> url
    # Required fields we could NOT satisfy from the profile — surfaced to the
    # user in the review UI so they fill them before approving.
    missing_required: list[str] = field(default_factory=list)
    # EEO / voluntary questions, kept separate so the UI renders them last.
    eeo_fields: dict[str, Any] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)


@dataclass
class ApplyResult:
    ok: bool
    confirmation_ref: Optional[str] = None
    message: str = ""
    raw: Optional[dict] = None
    # If the API path hits something only a human can clear.
    needs_you: bool = False
    needs_you_reason: Optional[str] = None


class BaseATSAdapter:
    """Subclass per Tier A ATS. Network calls are isolated so tests can run the
    mapping logic (`build_payload`) without any I/O."""

    ats_type: str = ""
    endpoint_template: str = ""
    # Set True when the ATS requires a partner token we may not hold yet; the
    # orchestrator will fall back to the browser path if so.
    partner_auth: bool = False

    def resolve_schema(self, job: dict) -> dict:
        """Fetch the live application form for this job. Default: no dynamic
        schema (adapters that need it override). Returns a plain dict."""
        return {}

    def build_payload(
        self,
        job: dict,
        profile: dict,
        answers: dict[str, str],
        resume_url: Optional[str],
        cover_letter_url: Optional[str],
        schema: Optional[dict] = None,
    ) -> PreparedPayload:
        """Map profile + answers onto the ATS form. Pure function — no I/O.
        Subclasses override; this base builds a sensible generic payload."""
        p = PreparedPayload(ats_type=self.ats_type)
        first = profile.get("first_name") or ""
        last = profile.get("last_name") or ""
        p.fields = {
            "first_name": first,
            "last_name": last,
            "email": profile.get("email") or "",
            "phone": profile.get("phone") or "",
            "linkedin_url": profile.get("linkedin_url") or "",
        }
        p.fields.update({k: v for k, v in (answers or {}).items() if v})
        if resume_url:
            p.attachments["resume"] = resume_url
        if cover_letter_url:
            p.attachments["cover_letter"] = cover_letter_url
        for req in ("first_name", "last_name", "email"):
            if not p.fields.get(req):
                p.missing_required.append(req)
        return p

    async def submit(self, payload: PreparedPayload) -> ApplyResult:  # pragma: no cover - network
        """Actually POST the application. Overridden per adapter. The base
        refuses to submit so a half-built adapter can never silently no-op."""
        raise NotImplementedError(f"{self.ats_type} adapter has no submit()")

    # --- shared validation used by the orchestrator before approval ---
    def validate(self, payload: PreparedPayload) -> list[str]:
        """Return a list of blocking problems (client-side validation, since
        several Tier A APIs do not validate required fields server-side)."""
        problems: list[str] = []
        if payload.missing_required:
            problems.append(
                "Missing required fields: " + ", ".join(payload.missing_required)
            )
        if not payload.attachments.get("resume"):
            problems.append("No resume attached")
        return problems


def register_adapter(ats_type: str) -> Callable[[type], type]:
    """Class decorator that instantiates and registers a Tier A adapter."""

    def _wrap(cls: type) -> type:
        instance = cls()
        instance.ats_type = ats_type
        TIER_A_ADAPTERS[ats_type] = instance
        log.debug("registered Tier A adapter: %s", ats_type)
        return cls

    return _wrap


def get_adapter(ats_type: str | None) -> Optional[BaseATSAdapter]:
    from app.services.apply.tiers import _normalize

    # Importing the adapters module registers all built-in adapters.
    from app.services.apply import adapters_tier_a  # noqa: F401

    return TIER_A_ADAPTERS.get(_normalize(ats_type))

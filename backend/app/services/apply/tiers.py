"""
ATS platform categorization — the table from the architecture doc (section C).

Every ATS PlaceUp scrapes falls into one of three intake tiers. The tier is the
single most important routing decision in the apply subsystem:

  Tier A  candidate-facing submission API, no employer key  -> API adapter
  Tier B  API exists but employer-key-only                  -> treat as web form
  Tier C  web-form-only                                     -> browser worker

`ATS_TIERS` maps an ats_type (matching the keys used in
`careers_ats.ATS_DISPATCH`) to its intake facts. `resolve_tier` is the public
entry point the orchestrator calls; it normalizes aliases and defaults unknown
platforms to Tier C (browser) — the safe, always-available path.

Caveat carried from the doc: verify each Tier A adapter against live ATS docs
before launch. Greenhouse Harvest v1/v2 are deprecated after 2026-08-31
(migrate to v3); Gem/Polymer/Join write-capability were unconfirmed.
"""
from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse

from app.models.application import ATSTier


@dataclass(frozen=True)
class ATSTierInfo:
    ats_type: str
    tier: ATSTier
    intake_method: str
    difficulty: str            # "low" | "low-medium" | "medium" | "high" | "very-high"
    captcha_likely: bool = False
    partner_auth: bool = False  # Tier A but needs a partner/token relationship


def _a(ats, method, diff="low", partner=False):
    return ATSTierInfo(ats, ATSTier.A, method, diff, partner_auth=partner)


def _b(ats, method, diff="high"):
    # Employer-key-only: recorded as its "real" tier B, but the resolver hands
    # these to the browser path because we never hold employer credentials.
    return ATSTierInfo(ats, ATSTier.B, method, diff)


def _c(ats, method, diff="high", captcha=False):
    return ATSTierInfo(ats, ATSTier.C, method, diff, captcha_likely=captcha)


# Keyed by normalized ats_type. Mirrors the ~28-row table in the doc.
ATS_TIERS: dict[str, ATSTierInfo] = {
    # ---- Tier A: candidate-facing apply APIs (lowest risk) ----
    "greenhouse": _a("greenhouse", "Job Board API POST /v1/boards/{token}/jobs/{id}", "low"),
    "ashby": _a("ashby", "applicationForm.submit (candidatesWrite)", "low-medium"),
    "smartrecruiters": _a("smartrecruiters", "Application API POST /postings/:uuid/candidates", "low-medium"),
    "workable": _a("workable", "Public jobs API + candidate-create API", "low-medium"),
    "recruitee": _a("recruitee", "Public Careers Site API POST /offers/:slug/candidates (no auth)", "low"),
    # ---- Tier A but partner/token relationship required ----
    "teamtailor": _a("teamtailor", "Public API add-candidate (token)", "medium", partner=True),
    "jazzhr": _a("jazzhr", "Partner apply API", "medium", partner=True),
    "phenom": _a("phenom", "Apply API POST /apply/v2/applications (partner auth)", "medium", partner=True),
    # ---- Tier C: web-form-only, browser automation ----
    "lever": _c("lever", "postForm web form (postings API read-only)", "medium"),
    "workday": _c("workday", "Web form; bot-detection fingerprinting", "very-high", captcha=True),
    "rippling": _c("rippling", "push_candidate is onboarding-only; apply via form", "high"),
    "bamboohr": _c("bamboohr", "Careers page web form", "medium-high"),
    "jobvite": _c("jobvite", "Web form (employer API only)", "high"),
    "breezyhr": _c("breezyhr", "Web form (employer API only)", "medium"),
    "paylocity": _c("paylocity", "Read-only job feed; web form", "medium-high"),
    "dayforce": _c("dayforce", "Career-site web form / Indeed Apply", "high"),
    "join": _c("join", "Web form (account-token write unconfirmed)", "medium"),
    "hireology": _c("hireology", "Web form (read-only integrations)", "medium"),
    "polymer": _c("polymer", "Web form (customer API mostly read)", "medium"),
    # ---- Tier B: employer-key-only -> forced to browser path ----
    "icims": _b("icims", "Apply Framework API (partner/employer creds)"),
    "oracle": _b("oracle", "Fusion HCM REST (employer OAuth); else web form", "very-high"),
    "taleo": _b("taleo", "Oracle/Taleo employer OAuth; else web form", "very-high"),
    "successfactors": _b("successfactors", "Employer API; web form", "very-high"),
    "ukg": _b("ukg", "Create Application API (UKG-issued creds)"),
    "ultipro": _b("ultipro", "UKG Create Application API (issued creds)"),
    "adp": _b("adp", "Job Applications V2 (practitioner scope)"),
    "zohorecruit": _b("zohorecruit", "addRecord + associateJobopening (account OAuth)"),
    "dover": _b("dover", "External API add-candidate (employer key)"),
    "gem": _b("gem", "ATS API (employer key); apply-write unconfirmed"),
    "pinpoint": _b("pinpoint", "REST create-record (employer key)", "medium-high"),
}

# Normalize the many aliases used across the scraper into a canonical ats_type.
_ALIASES = {
    "oracle recruiting": "oracle",
    "oracle cloud hcm": "oracle",
    "oracle_recruiting": "oracle",
    "sap successfactors": "successfactors",
    "sap_successfactors": "successfactors",
    "ukg pro": "ukg",
    "ukg pro recruiting": "ukg",
    "ultipro/ukg": "ukg",
    "zoho recruit": "zohorecruit",
    "zoho": "zohorecruit",
    "breezy": "breezyhr",
    "breezy hr": "breezyhr",
    "bamboo": "bamboohr",
    "bamboo hr": "bamboohr",
    "smart recruiters": "smartrecruiters",
    "team tailor": "teamtailor",
    "jazz hr": "jazzhr",
}


def _normalize(ats_type: str | None) -> str:
    key = (ats_type or "").strip().lower().replace("-", "").replace(" ", "")
    # Try the space/dash-preserving alias map first, then the squashed key.
    raw = (ats_type or "").strip().lower()
    if raw in _ALIASES:
        return _ALIASES[raw]
    if key in ATS_TIERS:
        return key
    # a few squashed aliases
    squashed = {a.replace(" ", ""): v for a, v in _ALIASES.items()}
    return squashed.get(key, key)


def tier_for_ats(ats_type: str | None) -> ATSTierInfo | None:
    """Return the full tier info for an ats_type, or None if unknown."""
    return ATS_TIERS.get(_normalize(ats_type))


def resolve_tier(ats_type: str | None) -> ATSTier:
    """The routing decision. Unknown platforms default to browser (Tier C).

    Tier B is *effectively* Tier C for a candidate-side tool — we never hold
    employer credentials — so callers that want "can I use an API?" should
    check `is_api_submittable` instead of the raw tier.
    """
    info = tier_for_ats(ats_type)
    if info is None:
        return ATSTier.C
    return info.tier


# Tier A platforms with a live, no-partner-token candidate apply adapter — the
# Phase 0 set that can be submitted via API. Partner-auth Tier A platforms
# (teamtailor/jazzhr/phenom) are deliberately excluded: without a partner token
# they must fall back to the browser path. Kept as a static set so the routing
# decision never depends on adapter import order / registry state.
API_SUBMITTABLE_ATS: frozenset[str] = frozenset(
    {"greenhouse", "ashby", "smartrecruiters", "workable", "recruitee"}
)


def is_api_submittable(ats_type: str | None) -> bool:
    """True only for Tier A platforms that have a working, no-partner-token
    candidate API adapter. Tier B (employer-key-only) and partner-auth Tier A
    platforms are excluded on purpose."""
    info = tier_for_ats(ats_type)
    if info is None or info.tier is not ATSTier.A:
        return False
    return _normalize(ats_type) in API_SUBMITTABLE_ATS


_ATS_HOST_HINTS: tuple[tuple[str, str], ...] = (
    ("greenhouse.io", "greenhouse"),
    ("lever.co", "lever"),
    ("ashbyhq.com", "ashby"),
    ("smartrecruiters.com", "smartrecruiters"),
    ("workable.com", "workable"),
    ("recruitee.com", "recruitee"),
    ("teamtailor.com", "teamtailor"),
    ("myworkdayjobs.com", "workday"),
    ("myworkdaysite.com", "workday"),
    ("icims.com", "icims"),
    ("bamboohr.com", "bamboohr"),
    ("jobvite.com", "jobvite"),
    ("rippling.com", "rippling"),
    ("successfactors.com", "successfactors"),
)


def infer_ats_type(job: dict) -> str:
    """Resolve the ATS from normalized metadata, source, or posting URL.

    Scraper fan-out sources often store ``source_name=tier1_ats`` while the
    real platform lives in metadata or the canonical URL. Application routing
    must use the real platform, never the fan-out worker name.
    """
    metadata = job.get("extra_metadata") if isinstance(job.get("extra_metadata"), dict) else {}
    candidates = (
        job.get("ats_type"), metadata.get("ats_type"), metadata.get("ats"),
        metadata.get("platform"), metadata.get("source_platform"),
    )
    for candidate in candidates:
        normalized = _normalize(str(candidate or ""))
        if normalized in ATS_TIERS:
            return normalized

    for key in ("job_url", "source_url", "url", "apply_url"):
        raw = str(job.get(key) or "").strip()
        host = (urlparse(raw).hostname or "").lower() if raw else ""
        for hint, ats_type in _ATS_HOST_HINTS:
            if hint in host:
                return ats_type

    source = _normalize(str(job.get("source") or job.get("source_name") or ""))
    return source if source in ATS_TIERS else ""

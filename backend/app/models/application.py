"""
PlaceUp Career — Automated Application System data models.

These models back the apply-orchestration subsystem described in
`MASTER_DOCUMENTATION.md` › "Automated Application System". They cover the
full lifecycle: an `Application` record, the reusable `ApplicationProfile`
(structured answers shared across ATS forms), cached `TailoredDocs`, captured
`InboxMessage`s from the dedicated inbox, and per-ATS `ATSAdapterConfig`.

Design rules that mirror the architecture doc:
  * Submission NEVER happens without an explicit human approval gate.
  * Sensitive answers (EEO, credentials) are minimized and, in production,
    encrypted at the application layer before they reach Firestore.
  * ATS "tier" drives the whole flow: Tier A = candidate-facing API,
    Tier B = employer-key-only (treated as web-form), Tier C = browser only.
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


class ATSTier(str, Enum):
    """How an application can be submitted for a given ATS.

    A — legitimate candidate-facing submission API, no employer key needed.
    B — API exists but needs the employer's OAuth/API key (unusable candidate
        side); treated as web-form-only in practice.
    C — web-form-only, headless browser automation required.
    """

    A = "A"
    B = "B"
    C = "C"


class SubmissionMethod(str, Enum):
    API = "api"
    BROWSER = "browser"
    MANUAL = "manual"


class ApplicationStatus(str, Enum):
    """Kanban lifecycle. Ordered roughly from creation to terminal state.

    The `NEEDS_REVIEW` and `NEEDS_YOU` states are the human gates: the system
    fills everything up to — but never including — the final submit, then waits
    for the user (review-before-submit, and live handoff for CAPTCHA/OTP).
    """

    PREPARING = "preparing"          # tailoring + form resolution in flight
    NEEDS_REVIEW = "needs_review"    # payload/screenshot ready, awaiting approval
    QUEUED = "queued"                # approved, enqueued on the per-ATS queue
    IN_FLIGHT = "in_flight"          # adapter/browser actively submitting
    NEEDS_YOU = "needs_you"          # CAPTCHA / OTP / bot-check handoff
    APPLIED = "applied"              # confirmed submitted
    FAILED = "failed"                # unrecoverable submission error
    SKIPPED = "skipped"             # user declined
    GHOSTED = "ghosted"              # no employer response after threshold
    INTERVIEWING = "interviewing"
    REJECTED = "rejected"
    OFFER = "offer"


# States a user can move a card into manually on the tracker board.
USER_SETTABLE_STATUSES = {
    ApplicationStatus.SKIPPED,
    ApplicationStatus.GHOSTED,
    ApplicationStatus.INTERVIEWING,
    ApplicationStatus.REJECTED,
    ApplicationStatus.OFFER,
    ApplicationStatus.APPLIED,
}

# Terminal states — no further automation runs.
TERMINAL_STATUSES = {
    ApplicationStatus.APPLIED,
    ApplicationStatus.FAILED,
    ApplicationStatus.SKIPPED,
    ApplicationStatus.REJECTED,
    ApplicationStatus.OFFER,
}


class InboxClassification(str, Enum):
    CONFIRMATION = "confirmation"
    STATUS = "status"
    OTP = "otp"
    OTHER = "other"


class ApplicationEvent(BaseModel):
    """One entry in an application's audit history."""

    at: datetime = Field(default_factory=_utcnow)
    kind: str                              # e.g. "created", "tailored", "approved"
    detail: str = ""
    status: Optional[ApplicationStatus] = None


class ApplyRequest(BaseModel):
    """Body for POST /api/apply — start preparing an application for a job."""

    job_id: str
    resume_id: Optional[str] = None        # defaults to the user's active resume
    generate_cover_letter: bool = True
    notes: str = Field(default="", max_length=2000)


class ReviewDecision(BaseModel):
    """Body for POST /api/apply/{id}/approve — the human gate.

    `answers` lets the user correct any mapped field before submission; it is
    merged over the adapter's field map. `confirm` MUST be true — an approval
    without explicit confirmation is rejected server-side.
    """

    confirm: bool = False
    answers: dict[str, str] = Field(default_factory=dict)
    edited_resume_url: Optional[str] = None
    edited_cover_letter_url: Optional[str] = None


class TailoredDocs(BaseModel):
    """Cached per (user, company) tailored artifacts — see pipeline section D."""

    user_id: str
    company: str
    resume_url: Optional[str] = None
    cover_letter_url: Optional[str] = None
    jd_signals: dict = Field(default_factory=dict)
    match_score: int = 0
    ats_score: int = 0
    diff: Optional[dict] = None             # base vs tailored, for the review UI
    created_at: datetime = Field(default_factory=_utcnow)


class ApplicationProfile(BaseModel):
    """Structured answers reused across every ATS form for a user.

    EEO answers stay optional and, per SmartRecruiters rules, are always
    presented after all other questions in the review UI. Nothing here is
    auto-submitted without the user's approval.
    """

    uid: str
    sponsorship_needed: Optional[bool] = None
    work_authorization: Optional[str] = None       # e.g. "OPT", "H-1B"
    addresses: list[dict] = Field(default_factory=list)
    education: list[dict] = Field(default_factory=list)
    employment: list[dict] = Field(default_factory=list)
    # EEO / voluntary self-identification — encrypted at rest in production.
    eeo: dict = Field(default_factory=dict)
    # Hash of a normalized question -> the user's saved answer.
    custom_answers: dict[str, str] = Field(default_factory=dict)
    updated_at: datetime = Field(default_factory=_utcnow)


class Application(BaseModel):
    """One application attempt for one (user, job)."""

    id: Optional[str] = None
    uid: str
    job_id: str
    title: str = ""
    company: str = ""
    location: str = ""
    job_url: str = ""
    ats_type: str = ""                      # e.g. "greenhouse", "workday"
    tier: ATSTier = ATSTier.C
    status: ApplicationStatus = ApplicationStatus.PREPARING
    submission_method: SubmissionMethod = SubmissionMethod.MANUAL
    match_score: int = 0
    ats_score: int = 0
    tailored_resume_url: Optional[str] = None
    tailored_cover_letter_url: Optional[str] = None
    # Payload the adapter intends to submit — shown verbatim in review.
    prepared_payload: dict = Field(default_factory=dict)
    confirmation_screenshot_url: Optional[str] = None
    confirmation_ref: Optional[str] = None
    needs_you_reason: Optional[str] = None  # "captcha" | "otp" | "bot_check"
    handoff_session_id: Optional[str] = None
    error: Optional[str] = None
    notes: str = ""
    history: list[ApplicationEvent] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)
    submitted_at: Optional[datetime] = None
    last_event_at: Optional[datetime] = None


class InboxMessage(BaseModel):
    """A captured message from the dedicated inbox (SES → S3 → webhook)."""

    id: Optional[str] = None
    uid: str
    app_id: Optional[str] = None
    from_addr: str = ""
    subject: str = ""
    received_at: datetime = Field(default_factory=_utcnow)
    s3_key: Optional[str] = None
    parsed_text: str = ""
    extracted_otp: Optional[str] = None
    classification: InboxClassification = InboxClassification.OTHER


class ATSAdapterConfig(BaseModel):
    """Config that drives a Tier C browser adapter (selectors + step graph).

    Persisted per ats_type so a form change can be fixed as data rather than
    code. Tier A adapters resolve their schema from the ATS API at runtime and
    do not need this.
    """

    ats_type: str
    intake_method: str = ""
    selectors: dict = Field(default_factory=dict)
    step_graph: list[dict] = Field(default_factory=list)
    field_map: dict = Field(default_factory=dict)
    captcha_likely: bool = False
    updated_at: datetime = Field(default_factory=_utcnow)

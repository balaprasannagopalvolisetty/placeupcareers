from datetime import datetime
from pydantic import BaseModel, EmailStr, Field
from typing import Optional


# Visa status options surfaced in the signup dropdown.
VISA_STATUSES = (
    "F1", "F1-OPT", "F1-STEM OPT", "H-1B", "O-1", "H-4 EAD",
    "Green Card", "US Citizen", "Other",
)


class AuthRequest(BaseModel):
    email: str
    password: str


class SignupRequest(BaseModel):
    """Expanded signup payload. Most fields are optional so the basic
    sign-up still works; the frontend collects them in a multi-step form."""
    first_name: str
    last_name: str
    email: EmailStr
    password: str
    phone: Optional[str] = None
    # Career details
    visa_status: Optional[str] = None
    experience_level: Optional[str] = None        # e.g. "0-1 years"
    current_role: Optional[str] = None
    current_company: Optional[str] = None
    location: Optional[str] = None                # current location
    country: Optional[str] = None                 # country (drives visa options)
    visa_status_other: Optional[str] = None       # free text when visa_status == "Other"
    linkedin_url: Optional[str] = None
    # Preferences
    target_roles: list[str] = Field(default_factory=list, max_length=25)
    target_locations: list[str] = Field(default_factory=list)
    # Legacy alias kept for older clients.
    targets: list[str] = Field(default_factory=list)
    # Legal agreement captured at signup (Terms + Privacy acceptance).
    agreement_accepted: bool = False
    agreement_version: Optional[str] = None
    # Payment marker from the pre-account checkout step. payment_reference is
    # whatever the hosted-checkout / Stripe session hands back (may be blank
    # until webhooks are connected).
    payment_plan: Optional[str] = None
    payment_reference: Optional[str] = None
    # Private beta: server-issued token from POST /api/invite/validate.
    # Required while INVITE_GATE_ENABLED; ignored afterwards.
    invite_token: Optional[str] = None


class AuthResponse(BaseModel):
    access_token: str
    expires_in: int = 900
    token_type: str = "bearer"
    user_id: str
    email: EmailStr
    first_name: str
    last_name: str
    plan: str = "pro"


class UserProfile(BaseModel):
    id: str
    first_name: str
    last_name: str
    email: EmailStr
    phone: Optional[str] = None
    location: Optional[str] = None
    country: Optional[str] = None
    visa_status: Optional[str] = None
    visa_status_other: Optional[str] = None
    experience_years: Optional[str] = None
    current_role: Optional[str] = None
    current_company: Optional[str] = None
    plan: str = "Pro"
    summary: Optional[str] = None
    linkedin_url: Optional[str] = None
    github_url: Optional[str] = None
    portfolio_url: Optional[str] = None
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class TokenRefreshResponse(BaseModel):
    access_token: str
    expires_in: int = 900
    token_type: str = "bearer"
    user: Optional[UserProfile] = None


class SessionResponse(BaseModel):
    authenticated: bool
    user: Optional[UserProfile] = None


class UserPreferences(BaseModel):
    job_preferences: str = ""
    notification_new_jobs: bool = True
    notification_daily_digest: bool = True
    notification_weekly_summary: bool = False
    notification_ats_updates: bool = True
    notification_marketing_emails: bool = False
    visa_status: Optional[str] = None
    experience_level: Optional[str] = None
    target_roles: list[str] = Field(default_factory=list, max_length=25)
    target_locations: list[str] = Field(default_factory=list)


class NotificationItem(BaseModel):
    id: str
    text: str
    time: str
    unread: bool = True


class DashboardSummaryAlert(BaseModel):
    id: str
    title: str
    company: str = ""
    match_score: int = 0
    message: Optional[str] = None
    time: str
    unread: bool = True


class DashboardSummary(BaseModel):
    resume_score: int = 0
    has_resume: bool = False
    active_resume_name: Optional[str] = None
    total_resumes: int = 0
    total_jobs: int = 0
    total_applications: int = 0
    recent_alerts: list[DashboardSummaryAlert] = Field(default_factory=list)
    featured_jobs: list[dict] = Field(default_factory=list)


class ResumeMetadata(BaseModel):
    id: str
    name: str
    uploaded_at: datetime
    score: int
    size_bytes: int
    active: bool = False


class UserApplication(BaseModel):
    job_id: str
    title: str = ""
    company: str = ""
    location: str = ""
    job_url: str = ""
    description: str = ""
    match_score: int = 0
    status: str = "applied"
    not_applied_reason: Optional[str] = None
    heard_back: Optional[bool] = None
    position_open: Optional[bool] = None
    salary_offered: Optional[str] = None
    notes: Optional[str] = None

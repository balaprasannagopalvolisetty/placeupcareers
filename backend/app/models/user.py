from datetime import datetime
from pydantic import BaseModel, EmailStr, Field
from typing import Optional


# Visa status options surfaced in the signup dropdown.
VISA_STATUSES = (
    "F1", "F1-OPT", "F1-STEM OPT", "H-1B", "O-1", "H-4 EAD",
    "Green Card", "US Citizen", "Other",
)


class AuthRequest(BaseModel):
    email: EmailStr
    password: str


class SignupRequest(BaseModel):
    """Expanded signup payload. Most fields are optional so the basic
    sign-up still works; the frontend collects them in a multi-step form."""
    first_name: str
    last_name: str
    email: EmailStr
    password: str
    # Career details
    visa_status: Optional[str] = None
    experience_level: Optional[str] = None        # e.g. "0-1 years"
    current_role: Optional[str] = None
    current_company: Optional[str] = None
    location: Optional[str] = None                # current location
    linkedin_url: Optional[str] = None
    # Preferences
    target_roles: list[str] = Field(default_factory=list, max_length=5)
    target_locations: list[str] = Field(default_factory=list)
    # Legacy alias kept for older clients.
    targets: list[str] = Field(default_factory=list)


class AuthResponse(BaseModel):
    access_token: str
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
    visa_status: Optional[str] = None
    experience_years: Optional[str] = None
    current_role: Optional[str] = None
    current_company: Optional[str] = None
    plan: str = "Pro"
    summary: Optional[str] = None
    linkedin_url: Optional[str] = None
    github_url: Optional[str] = None
    portfolio_url: Optional[str] = None
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class UserPreferences(BaseModel):
    job_preferences: str = ""
    notification_new_jobs: bool = True
    notification_daily_digest: bool = True
    notification_weekly_summary: bool = False
    notification_ats_updates: bool = True
    notification_marketing_emails: bool = False
    visa_status: Optional[str] = None
    experience_level: Optional[str] = None
    target_roles: list[str] = Field(default_factory=list, max_length=5)
    target_locations: list[str] = Field(default_factory=list)


class NotificationItem(BaseModel):
    id: str
    text: str
    time: str
    unread: bool = True


class ResumeMetadata(BaseModel):
    id: str
    name: str
    uploaded_at: datetime
    score: int
    size_bytes: int
    active: bool = False

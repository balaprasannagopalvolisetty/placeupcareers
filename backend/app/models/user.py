from datetime import datetime
from pydantic import BaseModel, EmailStr, Field
from typing import Optional


class AuthRequest(BaseModel):
    email: EmailStr
    password: str


class SignupRequest(BaseModel):
    first_name: str
    last_name: str
    email: EmailStr
    password: str
    visa_status: Optional[str] = None
    experience_level: Optional[str] = None
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
    plan: str = "Pro"
    summary: Optional[str] = None
    linkedin_url: Optional[str] = None
    github_url: Optional[str] = None
    portfolio_url: Optional[str] = None
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class UserPreferences(BaseModel):
    job_preferences: str = "Senior Frontend / Full Stack Engineer roles at mid-to-large tech companies. Open to remote and SF/NY offices."
    notification_new_jobs: bool = True
    notification_daily_digest: bool = True
    notification_weekly_summary: bool = False
    notification_ats_updates: bool = True
    notification_marketing_emails: bool = False
    visa_status: Optional[str] = "F1-OPT"
    experience_level: Optional[str] = "3-5 years"


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

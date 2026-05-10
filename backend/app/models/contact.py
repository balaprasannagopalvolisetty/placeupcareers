"""PlaceUp Career - Contact / Recruiter Models."""
from __future__ import annotations
from datetime import datetime
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class ContactSource(str, Enum):
    # Free harvesters (zero ongoing cost)
    ATS_METADATA = "ats_metadata"
    DOL_LCA = "dol_lca"
    TEAM_PAGE = "team_page"
    GITHUB = "github"
    CROWDSOURCED = "crowdsourced"
    LINKEDIN_SEARCH_URL = "linkedin_search_url"
    # Paid (only via BYOK or platform-enabled)
    APOLLO = "apollo"
    HUNTER = "hunter"
    FINALSCOUT = "finalscout"
    GOOGLE_XRAY = "google_xray"
    # Misc
    MANUAL = "manual"


class ContactConfidence(str, Enum):
    VERIFIED = "verified"
    PATTERN = "pattern"
    GUESSED = "guessed"
    UNKNOWN = "unknown"


class ContactRole(str, Enum):
    RECRUITER = "recruiter"
    HIRING_MANAGER = "hiring_manager"
    TALENT_ACQUISITION = "talent_acquisition"
    HEAD_OF_PEOPLE = "head_of_people"
    ENGINEERING_MANAGER = "engineering_manager"
    TEAM_LEAD = "team_lead"
    OTHER = "other"


class Contact(BaseModel):
    id: str
    full_name: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    title: Optional[str] = None
    role: ContactRole = ContactRole.OTHER
    company: str
    company_domain: Optional[str] = None
    email: Optional[str] = None
    linkedin_url: Optional[str] = None
    linkedin_search_url: Optional[str] = None
    source: ContactSource
    confidence: ContactConfidence = ContactConfidence.UNKNOWN
    source_payload: dict = Field(default_factory=dict)
    related_job_id: Optional[str] = None
    discovered_at: datetime = Field(default_factory=datetime.utcnow)
    last_verified_at: Optional[datetime] = None


class ContactSearchRequest(BaseModel):
    """Free-first by default. Paid sources only run if user opts in + provides BYOK key."""
    company: str
    role_query: Optional[str] = None
    domain: Optional[str] = None
    job_id: Optional[str] = None

    # Free sources (default ON)
    use_dol_lca: bool = True
    use_team_page: bool = True
    use_github: bool = True
    use_crowdsourced: bool = True
    use_ats_metadata: bool = True

    # Paid sources (default OFF)
    use_apollo: bool = False
    use_hunter: bool = False
    use_google_xray: bool = False
    use_finalscout: bool = False

    # BYOK
    byok_apollo_key: Optional[str] = None
    byok_hunter_key: Optional[str] = None
    byok_serpapi_key: Optional[str] = None
    byok_finalscout_key: Optional[str] = None

    max_contacts: int = Field(default=10, ge=1, le=50)
    force_refresh: bool = False


class ContactContribution(BaseModel):
    """User-submitted contact for crowdsourced pool."""
    company: str
    full_name: Optional[str] = None
    title: Optional[str] = None
    email: Optional[str] = None
    linkedin_url: Optional[str] = None
    role: ContactRole = ContactRole.OTHER
    submitted_by: Optional[str] = None
    notes: Optional[str] = Field(default=None, max_length=1000)


class EnrichmentResult(BaseModel):
    company: str
    role_query: Optional[str] = None
    contacts: list[Contact] = []
    sources_used: list[ContactSource] = []
    cache_hit: bool = False
    api_credits_used: dict[str, int] = Field(default_factory=dict)
    duration_seconds: float = 0.0
    notes: list[str] = Field(default_factory=list)

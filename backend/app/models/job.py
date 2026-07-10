"""
PlaceUp Career — Job Data Models
Defines Pydantic schemas for job postings, filters, and API responses.
Aligned with frontend mock data shapes and Firestore document structure.
"""

from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from enum import Enum

from app.scrape_constants import DEFAULT_SCRAPE_SEARCH_TERMS


class JobSource(str, Enum):
    """Job scraping source identifier."""
    LINKEDIN = "linkedin"
    INDEED = "indeed"
    GLASSDOOR = "glassdoor"
    ZIPRECRUITER = "ziprecruiter"
    GOOGLE = "google"
    USAJOBS = "usajobs"
    RAPIDAPI = "rapidapi"
    DICE = "dice"
    MONSTER = "monster"
    JOOBLE = "jooble"
    # Free, clean-200 global job boards (remote / English-friendly / international).
    # Public JSON or RSS endpoints — no auth, no anti-bot. Owned by
    # app/etl/sources/free_boards.py.
    REMOTEOK = "remoteok"
    REMOTIVE = "remotive"
    ARBEITNOW = "arbeitnow"
    JOBICY = "jobicy"
    WEWORKREMOTELY = "weworkremotely"
    # Official government job-portal APIs (clean 200, country-tagged).
    # Owned by app/etl/sources/official_portals.py.
    JOBTECH = "jobtech"            # Sweden — Platsbanken / JobTech Dev open API
    EURES = "eures"
    UK_FIND_A_JOB = "uk_findajob"
    NHS_JOBS = "nhs_jobs"
    JOBBANK_CA = "jobbank_ca"
    BA_JOBSUCHE = "ba_jobsuche"
    FRANCE_TRAVAIL = "france_travail"
    MYCAREERSFUTURE = "mycareersfuture"
    TYOMARKKINATORI = "tyomarkkinatori"
    NAV_ARBEIDSPLASSEN = "nav_arbeidsplassen"
    # ATS career boards (direct from company)
    GREENHOUSE = "greenhouse"
    LEVER = "lever"
    ASHBY = "ashby"
    SMARTRECRUITERS = "smartrecruiters"
    WORKDAY = "workday"
    RECRUITEE = "recruitee"
    PERSONIO = "personio"
    TEAMTAILOR = "teamtailor"
    JAZZHR = "jazzhr"
    RIPPLING = "rippling"
    BAMBOOHR = "bamboohr"
    WORKABLE = "workable"
    # Extended ATS coverage (public career-site endpoints, no auth).
    # Owned by app/services/careers_ats.py.
    ICIMS = "icims"
    JOBVITE = "jobvite"
    BREEZYHR = "breezyhr"
    ORACLE_RECRUITING = "oracle_recruiting"
    PAYLOCITY = "paylocity"
    UKG = "ukg"                          # UltiPro / UKG Pro Recruiting
    ZOHO_RECRUIT = "zoho_recruit"
    ADP = "adp"                          # ADP Workforce Now career center
    DOVER = "dover"
    GEM = "gem"
    SUCCESSFACTORS = "successfactors"    # SAP SuccessFactors Career Site Builder
    PINPOINT = "pinpoint"
    POLYMER = "polymer"
    PHENOM = "phenom"
    DAYFORCE = "dayforce"
    JOIN_COM = "join"
    HIREOLOGY = "hireology"
    # Aggregated H1B sponsor pipeline (multi-ATS, all curated H1B sponsors)
    H1B_SPONSOR = "h1b_sponsor"
    # Tier-1 ATS aggregate (Greenhouse/Lever/Ashby/SmartRecruiters/Workable/Recruitee)
    # filtered down to the taxonomy roles. Owned by app/etl/sources/tier1_ats.py.
    TIER1_ATS = "tier1_ats"
    # AI-assisted discovery for direct career pages, Google Jobs, and public
    # LinkedIn job search pages. Owned by app/services/scrapegraph_discovery.py.
    SCRAPEGRAPH_DISCOVERY = "scrapegraph_discovery"
    # Scrapling-powered HTML discovery for direct company career/search pages.
    # This is a best-effort fallback around blocked/JS-heavy sources and H1B
    # sponsor pages not covered by structured ATS APIs.
    SCRAPLING_DISCOVERY = "scrapling_discovery"


class JobCategory(str, Enum):
    """Job category classification."""
    TECHNOLOGY = "Technology"
    HEALTHCARE = "Healthcare"
    FINANCE = "Finance"
    ENGINEERING = "Engineering"
    EDUCATION = "Education"
    GOVERNMENT = "Government"
    NONPROFIT = "Nonprofit"
    OTHER = "Other"


class VisaType(str, Enum):
    """Visa sponsorship type flags."""
    H1B = "H-1B"
    OPT = "OPT"
    STEM_OPT = "STEM OPT"
    GREEN_CARD = "Green Card"
    NO_SPONSORSHIP = "No Sponsorship"


class VisaBadges(BaseModel):
    """Visa compatibility flags for a job posting."""
    visa_opt: bool = False
    visa_stem_opt: bool = False
    visa_h1b: bool = False
    h1b_verified: bool = False
    no_sponsorship: bool = False
    visa_score: int = Field(default=0, ge=0, le=100)
    visa_country: Optional[str] = None
    visa_country_name: Optional[str] = None
    visa_programs: list[str] = Field(default_factory=list)
    visa_program_names: list[str] = Field(default_factory=list)
    sponsor_verified: bool = False
    sponsor_source: Optional[str] = None
    english_friendly: bool = False


class SalaryRange(BaseModel):
    """Salary information for a job posting."""
    min_salary: Optional[float] = None
    max_salary: Optional[float] = None
    currency: str = "USD"
    period: str = "yearly"  # yearly, monthly, hourly

    @property
    def display(self) -> str:
        """Format salary for display (e.g., '$120K - $160K')."""
        if self.min_salary and self.max_salary:
            return f"${self.min_salary/1000:.0f}K - ${self.max_salary/1000:.0f}K"
        elif self.min_salary:
            return f"${self.min_salary/1000:.0f}K+"
        elif self.max_salary:
            return f"Up to ${self.max_salary/1000:.0f}K"
        return "Not specified"


class JobPost(BaseModel):
    """Core job posting data model.

    Matches the Firestore 'jobs' collection document structure
    and the frontend JobCard component data shape.
    """
    id: str = Field(description="Unique job identifier (hash of title+company+location)")
    title: str
    company: str
    location: str
    description: str = ""
    job_url: str = ""

    # Classification
    category: JobCategory = JobCategory.OTHER
    job_type: str = ""  # Full-time, Part-time, Contract, Internship
    experience_level: str = ""  # Entry, Mid, Senior, Executive
    industry: str = ""

    # Compensation
    salary: Optional[SalaryRange] = None

    # Visa / Sponsorship
    visa: VisaBadges = Field(default_factory=VisaBadges)

    # Metadata
    source: JobSource = JobSource.LINKEDIN
    source_job_id: str = ""
    posted_at: Optional[datetime] = None
    scraped_at: datetime = Field(default_factory=datetime.utcnow)
    status: str = "active"  # "active" or "inactive"
    expires_at: Optional[datetime] = None

    # Matching (populated per-user)
    match_score: Optional[int] = Field(default=None, ge=0, le=100)
    score_type: Optional[str] = None
    score_guarded: Optional[bool] = None

    # Deduplication
    content_hash: str = ""

    # Hiring manager (from Apollo enrichment)
    hiring_manager_name: Optional[str] = None
    hiring_manager_email: Optional[str] = None
    hiring_manager_linkedin: Optional[str] = None

    # Rich portal fields (JobSpy / ATS feeds)
    is_remote: Optional[bool] = None
    salary_source: Optional[str] = None
    listing_type: Optional[str] = None
    job_function: Optional[str] = None
    vacancy_count: Optional[int] = None
    skills: Optional[str] = None
    job_url_direct: Optional[str] = None
    company_url: Optional[str] = None
    company_logo: Optional[str] = None
    company_description: Optional[str] = None
    company_rating: Optional[float] = None
    company_reviews_count: Optional[int] = None
    extra_metadata: dict = Field(
        default_factory=dict,
        description="Additional structured portal fields (departments, office lists, ATS metadata, …)",
    )

    class Config:
        json_schema_extra = {
            "example": {
                "id": "a1b2c3d4",
                "title": "Senior Software Engineer",
                "company": "Google",
                "location": "Mountain View, CA",
                "description": "Build scalable distributed systems...",
                "job_url": "https://careers.google.com/jobs/123",
                "category": "Technology",
                "job_type": "Full-time",
                "experience_level": "Senior",
                "salary": {"min_salary": 185000, "max_salary": 280000},
                "visa": {"visa_h1b": True, "h1b_verified": True, "visa_score": 92},
                "source": "linkedin",
                "match_score": 87,
            }
        }


class JobFilter(BaseModel):
    """Query parameters for filtering job listings."""
    search: Optional[str] = None
    location: Optional[str] = None
    category: Optional[JobCategory] = None
    visa_type: Optional[VisaType] = None
    visa_only: bool = False
    min_salary: Optional[float] = None
    source: Optional[JobSource] = None
    hours_old: Optional[int] = Field(default=72, description="Max hours since posting")
    job_type: Optional[str] = None
    experience_level: Optional[str] = None

    # Pagination
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


class JobListResponse(BaseModel):
    """Paginated job listing API response."""
    jobs: list[JobPost]
    total: int
    page: int
    page_size: int
    total_pages: int
    filters_applied: dict = {}


class JobStats(BaseModel):
    """Aggregated job statistics for dashboard."""
    total_jobs: int = 0
    by_category: dict[str, int] = {}
    by_visa_type: dict[str, int] = {}
    by_source: dict[str, int] = {}
    by_location: dict[str, int] = {}
    avg_salary: Optional[float] = None
    new_today: int = 0
    new_this_week: int = 0


def _default_search_terms_factory() -> list[str]:
    return list(DEFAULT_SCRAPE_SEARCH_TERMS)


class ScrapeRequest(BaseModel):
    """Request body for triggering a manual scrape cycle."""

    search_terms: list[str] = Field(
        default_factory=_default_search_terms_factory,
        description="Job titles to search for",
    )
    locations: list[str] = Field(
        default=["United States", "Canada"],
        description="Locations to search in. Global expansion uses target-country codes/labels as source support is added."
    )
    sources: list[JobSource] = Field(
        default=[
            JobSource.LINKEDIN,
            JobSource.INDEED,
            JobSource.GLASSDOOR,
            JobSource.ZIPRECRUITER,
            JobSource.GOOGLE,
            # RAPIDAPI removed from defaults: its /active-jb-24h feed was
            # failing (403/429 -> cooldown) and its tasks starved other
            # sources via the shared concurrency + single-slot semaphore.
            # Re-enable explicitly per request if the provider quota is fixed.
            JobSource.USAJOBS,
            JobSource.DICE,
            JobSource.MONSTER,
            JobSource.JOOBLE,
            JobSource.REMOTEOK,
            JobSource.REMOTIVE,
            JobSource.ARBEITNOW,
            JobSource.JOBICY,
            JobSource.WEWORKREMOTELY,
            JobSource.JOBTECH,
            JobSource.EURES,
            JobSource.UK_FIND_A_JOB,
            JobSource.NHS_JOBS,
            JobSource.JOBBANK_CA,
            JobSource.BA_JOBSUCHE,
            JobSource.FRANCE_TRAVAIL,
            JobSource.MYCAREERSFUTURE,
            JobSource.TYOMARKKINATORI,
            JobSource.NAV_ARBEIDSPLASSEN,
            JobSource.H1B_SPONSOR,
            JobSource.TIER1_ATS,
            JobSource.SCRAPLING_DISCOVERY,
        ],
        description="Broad multi-source scraping defaults, including job boards, APIs, official portals, H1B sponsors, and direct career pages.",
    )
    h1b_sponsor_tiers: list[str] = Field(
        default=["T1", "T2"],
        description="H1B tiers to scrape when H1B_SPONSOR is enabled (T1=top 100, T2=top 500, T3=active)",
    )
    h1b_sponsor_max_jobs: int = Field(
        default=500,
        ge=10,
        le=5000,
        description="Per-sponsor cap on jobs pulled from H1B_SPONSOR pipeline",
    )
    h1b_sponsor_concurrency: int = Field(
        default=8,
        ge=1,
        le=32,
        description="Max parallel ATS scrapes during the H1B_SPONSOR pipeline",
    )
    results_per_source: int = Field(
        default=120,
        ge=10,
        le=800,
        description="Target max jobs collected per portal × query × location (JobSpy may return fewer)",
    )
    jobspy_hours_old: Optional[int] = Field(
        default=336,
        description="Maximum listing age for JobSpy scrapes (hours). None = portal default.",
    )
    jobspy_page_size: int = Field(default=35, ge=10, le=120, description="Batch size each JobSpy request")
    jobspy_max_pages: int = Field(
        default=15,
        ge=1,
        le=80,
        description="Max pagination steps per portal × query × location",
    )
    greenhouse_board_tokens: list[str] = Field(
        default_factory=list,
        description="Explicit Greenhouse board tokens (falls back to GREENHOUSE_BOARD_TOKENS env)",
    )


class ScrapeResult(BaseModel):
    """Result summary from a scrape cycle."""
    total_scraped: int = 0
    new_jobs: int = 0
    duplicates_skipped: int = 0
    errors: list[str] = []
    duration_seconds: float = 0.0
    sources_used: list[str] = []
    source_breakdown: dict[str, dict[str, int]] = {}

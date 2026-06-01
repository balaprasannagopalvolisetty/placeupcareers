"""
PlaceUp Career — Visa & H1B Data Models
Defines Pydantic schemas for H1B sponsor data, visa classification, and salary info.
Data sourced from USCIS CSV, h1bdata.info, and myVisaJobs.com.
"""

from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class H1BSponsor(BaseModel):
    """H1B sponsor data from USCIS annual CSV.

    Represents an employer's historical H1B petition activity,
    used for verifying visa sponsorship claims in job postings.
    """
    id: str = ""
    employer_name: str
    city: str = ""
    state: str = ""
    zip_code: str = ""

    # Petition counts
    initial_approvals: int = 0
    initial_denials: int = 0
    continuing_approvals: int = 0
    continuing_denials: int = 0
    total_petitions: int = 0
    fiscal_year: int = 0

    @property
    def approval_rate(self) -> float:
        """Calculate overall approval rate as a percentage."""
        total = self.initial_approvals + self.initial_denials + self.continuing_approvals + self.continuing_denials
        if total == 0:
            return 0.0
        approved = self.initial_approvals + self.continuing_approvals
        return round((approved / total) * 100, 1)

    @property
    def is_active_sponsor(self) -> bool:
        """Whether this employer actively sponsors H1B (5+ petitions)."""
        return self.total_petitions >= 5


class H1BSalaryData(BaseModel):
    """H1B salary data scraped from h1bdata.info.

    Provides salary ranges for specific job titles at specific employers,
    based on Labor Condition Application (LCA) filings.
    """
    employer: str
    job_title: str
    location: str = ""
    base_salary: Optional[float] = None
    median_salary: Optional[float] = None
    top_salary: Optional[float] = None
    case_count: int = 0
    year: int = 0


class LCARecord(BaseModel):
    """Labor Condition Application record for visa salary verification."""
    case_number: str = ""
    employer_name: str
    job_title: str
    worksite_city: str = ""
    worksite_state: str = ""
    wage_rate: Optional[float] = None
    wage_unit: str = "Year"  # Year, Month, Hour
    prevailing_wage: Optional[float] = None
    case_status: str = ""  # Certified, Denied, Withdrawn
    submit_date: Optional[str] = None
    start_date: Optional[str] = None
    visa_class: str = "H-1B"


class VisaScore(BaseModel):
    """Visa classification result for a job posting.

    Port of the JavaScript classifier from backend-pipeline.md.
    Uses keyword scoring matrix + USCIS cross-reference.
    """
    score: int = Field(default=0, ge=0, le=100)
    visa_opt: bool = False
    visa_stem_opt: bool = False
    visa_h1b: bool = False
    h1b_verified: bool = False
    green_card: bool = False
    country_code: Optional[str] = None
    country_name: Optional[str] = None
    visa_programs: list[str] = Field(default_factory=list)
    visa_program_names: list[str] = Field(default_factory=list)
    sponsor_verified: bool = False
    sponsor_source: Optional[str] = None
    english_friendly: bool = False

    # Scoring details
    keyword_hits: list[str] = Field(
        default=[], description="Visa-related keywords found in job description"
    )
    negative_hits: list[str] = Field(
        default=[], description="Negative keywords (e.g., 'US citizen only')"
    )
    uscis_match: bool = Field(
        default=False, description="Whether employer was found in USCIS H1B data"
    )
    uscis_petition_count: int = Field(
        default=0, description="Number of H1B petitions filed by employer"
    )

    # Classification
    should_discard: bool = Field(
        default=False, description="True if job is not visa-friendly (score < 10)"
    )
    confidence: str = Field(
        default="low", description="high | medium | low confidence in visa classification"
    )


class VisaClassifyRequest(BaseModel):
    """Request to classify a job description for visa compatibility."""
    title: str
    company: str
    description: str
    location: str = ""


class H1BSearchRequest(BaseModel):
    """Query parameters for searching H1B data."""
    employer: Optional[str] = None
    job_title: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    year: Optional[int] = None
    min_petitions: int = 1

    # Pagination
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)


class H1BSearchResponse(BaseModel):
    """Paginated H1B search results."""
    sponsors: list[H1BSponsor] = []
    salary_data: list[H1BSalaryData] = []
    total: int = 0
    page: int = 1
    page_size: int = 20


class VisaStatsResponse(BaseModel):
    """Aggregated visa statistics for dashboard."""
    total_sponsors: int = 0
    top_sponsors: list[dict] = []  # [{employer, petition_count, approval_rate}]
    avg_salary_by_role: dict[str, float] = {}
    approval_rate_trend: list[dict] = []  # [{year, rate}]
    last_updated: Optional[datetime] = None

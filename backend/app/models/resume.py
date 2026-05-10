"""
PlaceUp Career — Resume & ATS Data Models
Defines Pydantic schemas for resume parsing, ATS scoring, and keyword analysis.
Inspired by resume_screener (Instructor structured outputs) and Resume-Matcher.
"""

from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


# ─── Parsed Resume Models ─────────────────────────────────────


class SkillEntry(BaseModel):
    """A skill extracted from a resume."""
    name: str
    category: str = ""  # e.g., "Programming", "Framework", "Soft Skill"
    proficiency: str = ""  # e.g., "Expert", "Intermediate", "Beginner"


class ExperienceEntry(BaseModel):
    """A work experience entry from a resume."""
    title: str
    company: str
    location: str = ""
    start_date: str = ""
    end_date: str = ""  # "Present" if current
    duration_months: int = 0
    description: str = ""
    highlights: list[str] = []


class EducationEntry(BaseModel):
    """An education entry from a resume."""
    degree: str
    institution: str
    field_of_study: str = ""
    graduation_year: str = ""
    gpa: Optional[float] = None
    honors: str = ""


class ProjectEntry(BaseModel):
    """A project entry from a resume."""
    name: str
    description: str = ""
    technologies: list[str] = []
    url: Optional[str] = None


class CertificationEntry(BaseModel):
    """A certification from a resume."""
    name: str
    issuer: str = ""
    date: str = ""
    expiry: Optional[str] = None


class ParsedResume(BaseModel):
    """Structured resume data extracted by LLM via Instructor.

    This model is used as the response_model for the Instructor call,
    ensuring the LLM returns perfectly typed, validated data.
    """
    name: str = ""
    email: str = ""
    phone: str = ""
    location: str = ""
    linkedin_url: str = ""
    portfolio_url: str = ""
    summary: str = ""

    skills: list[SkillEntry] = []
    experience: list[ExperienceEntry] = []
    education: list[EducationEntry] = []
    projects: list[ProjectEntry] = []
    certifications: list[CertificationEntry] = []

    total_experience_years: float = 0.0
    languages: list[str] = []

    class Config:
        json_schema_extra = {
            "example": {
                "name": "John Smith",
                "email": "john@example.com",
                "summary": "Senior full-stack engineer with 8+ years...",
                "skills": [
                    {"name": "Python", "category": "Programming", "proficiency": "Expert"},
                    {"name": "React", "category": "Framework", "proficiency": "Expert"},
                ],
                "experience": [
                    {
                        "title": "Senior Software Engineer",
                        "company": "Google",
                        "duration_months": 36,
                        "highlights": ["Led team of 5", "Reduced latency by 40%"],
                    }
                ],
                "total_experience_years": 8.5,
            }
        }


# ─── ATS Scoring Models ───────────────────────────────────────


class KeywordWithImpact(BaseModel):
    """A keyword with its impact assessment for ATS analysis."""
    keyword: str
    impact: str = "medium"  # high, medium, low
    category: str = ""  # technical, soft-skill, industry, certification
    suggestion: str = ""  # How to add this keyword to resume


class KeywordAnalysis(BaseModel):
    """Detailed keyword comparison between resume and job description."""
    strong_keywords: list[str] = Field(
        default=[], description="Keywords present in both resume and JD"
    )
    missing_keywords: list[KeywordWithImpact] = Field(
        default=[], description="Important JD keywords missing from resume"
    )
    additional_keywords: list[str] = Field(
        default=[], description="Resume keywords not in JD (potential extras)"
    )
    keyword_density_score: float = Field(
        default=0.0, ge=0, le=100, description="Percentage of JD keywords found in resume"
    )


class SkillMatch(BaseModel):
    """Skill matching analysis between resume and job."""
    matched_skills: list[str] = []
    missing_skills: list[str] = []
    additional_skills: list[str] = []
    match_percentage: float = Field(default=0.0, ge=0, le=100)


class ATSResult(BaseModel):
    """Complete ATS scoring result.

    Structured output from Instructor + Groq LLM call.
    Covers all dimensions used by modern ATS systems.
    """
    # Overall
    overall_score: float = Field(ge=0, le=100, description="Composite ATS score")
    recommendation: str = Field(
        description="Strong Match | Potential Match | Weak Match | Not Recommended"
    )

    # Category scores
    skill_match: SkillMatch = Field(default_factory=SkillMatch)
    experience_score: float = Field(default=0.0, ge=0, le=100)
    education_score: float = Field(default=0.0, ge=0, le=100)
    projects_score: float = Field(default=0.0, ge=0, le=100)
    certifications_score: float = Field(default=0.0, ge=0, le=100)
    cultural_fit_score: float = Field(default=0.0, ge=0, le=100)

    # Analysis
    strengths: list[str] = Field(default=[], description="Key strengths of the candidate")
    concerns: list[str] = Field(default=[], description="Potential concerns or gaps")
    keyword_analysis: KeywordAnalysis = Field(default_factory=KeywordAnalysis)
    improvement_suggestions: list[str] = Field(
        default=[], description="Specific suggestions to improve resume for this role"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "overall_score": 82.5,
                "recommendation": "Strong Match",
                "skill_match": {
                    "matched_skills": ["Python", "React", "AWS"],
                    "missing_skills": ["Kubernetes", "GraphQL"],
                    "match_percentage": 75.0,
                },
                "experience_score": 90.0,
                "education_score": 85.0,
                "strengths": ["Strong technical background", "Leadership experience"],
                "concerns": ["No Kubernetes experience mentioned"],
                "improvement_suggestions": [
                    "Add Kubernetes to skills section",
                    "Quantify impact metrics in experience bullets",
                ],
            }
        }


# ─── API Request/Response Models ──────────────────────────────


class ResumeParseRequest(BaseModel):
    """Metadata for a resume parse request. File is sent as multipart form data."""
    extract_skills: bool = True
    extract_experience: bool = True
    extract_education: bool = True
    extract_projects: bool = True


class ResumeScoreRequest(BaseModel):
    """Request body for ATS scoring. Resume file sent as multipart; JD as text."""
    job_description: str = Field(description="Full job description text")
    job_title: Optional[str] = Field(default=None, description="Job title for context")
    company: Optional[str] = Field(default=None, description="Company name for context")


class ResumeParseResponse(BaseModel):
    """Response from resume parsing endpoint."""
    success: bool = True
    resume: ParsedResume
    word_count: int = 0
    page_count: int = 0
    parse_time_ms: float = 0.0


class ResumeScoreResponse(BaseModel):
    """Response from ATS scoring endpoint."""
    success: bool = True
    ats_result: ATSResult
    parsed_resume: ParsedResume
    job_title: str = ""
    company: str = ""
    scored_at: datetime = Field(default_factory=datetime.utcnow)
    processing_time_ms: float = 0.0

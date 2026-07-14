"""Tests for the scraper/scoring quality fixes (A3, A4, A5, B)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.dialects import postgresql

from app.utils.glued_words import deglue_text, looks_glued
from app.utils.job_quality import job_description_text
from app.services.employer_normalizer import (
    normalize_employer, resolve_approval_rate, build_registry,
)
from app.services.staffing_filter import classify_staffing, apply_staffing_flag
from app.services.jd_quality_gate import assess_jd, strip_boilerplate
from app.services.resume_parser import RESUME_SCHEMA_VERSION, resume_text_to_json
from app.services.job_filters import is_target_experience, parse_years
from app.workers.job_liveness_checker import classify_job_page
from app.api.jobs import _projection_sort_key
from app.db.postgres import PostgresClient
from app.db.schema import MasterJob


# ---------------------------------------------------------------- A3: de-glue
def test_deglue_fixes_scrape_artifacts():
    assert "What You'll Do" in deglue_text("WhatYou'llDo")
    out = deglue_text("Responsibilities:Design and build gplugins")
    assert "Responsibilities: Design" in out


@pytest.mark.parametrize("token", ["JavaScript", "GitHub", "PyTorch", "GraphQL", "iOS", "gRPC", "APIs"])
def test_deglue_preserves_tech_tokens(token):
    # Tech identifiers must survive untouched even inside glued context.
    assert deglue_text(token) == token


def test_deglue_preserves_clean_prose():
    clean = "Build scalable distributed systems and mentor engineers."
    assert deglue_text(clean) == clean


def test_looks_glued_gate():
    assert looks_glued("WhatYou'llDoResponsibilities:Design")
    assert not looks_glued("A normal clean sentence about engineering.")


def test_job_description_text_degluing_integration():
    glued = "About the job WhatYou'llDo: Design systems.You will also build APIs."
    out = job_description_text(glued)
    assert "What You'll Do" in out
    assert "APIs" in out  # preserved


# ----------------------------------------------------- A4: employer normalize
@pytest.mark.parametrize("raw,expected", [
    ("Yoh - A Day & Zimmerman Company", "yoh"),
    ("TEKsystems c/o Allegis Group", "teksystems"),
    ("Amtex System Inc.", "amtex system"),
    ("Google LLC", "google"),
    ("Kforce Technology Staffing, LLC", "kforce technology staffing"),
])
def test_normalize_employer(raw, expected):
    assert normalize_employer(raw) == expected


def test_approval_rate_null_vs_zero():
    registry = build_registry([
        {"employer": "Google LLC", "approvals": 90, "denials": 10},
        {"employer": "Zero Co", "approvals": 0, "denials": 5},
    ])
    # Match with real data.
    hit = resolve_approval_rate("Google, Inc.", registry)
    assert hit.matched and hit.rate == 90.0
    # Genuine 0% (matched, all denied) — rate computed, not None.
    z = resolve_approval_rate("Zero Co", registry)
    assert z.matched and z.rate == 0.0
    # Miss => None, NOT 0 (this is the bug fix).
    miss = resolve_approval_rate("Unknown Staffing LLC", registry)
    assert miss.matched is False and miss.rate is None


# ------------------------------------------------------- A5: staffing downrank
def test_staffing_flag_downranks_not_blocks():
    flag = classify_staffing("TEKsystems c/o Allegis Group")
    assert flag.is_staffing and flag.penalty > 0 and flag.hard_block is False


def test_real_company_not_flagged():
    assert classify_staffing("Google").is_staffing is False


def test_apply_staffing_flag_is_non_destructive():
    job = {"company": "Kforce Technology Staffing", "status": "active", "description": ""}
    apply_staffing_flag(job)
    assert job["status"] == "active"               # never blocked
    assert job["extra_metadata"]["staffing_agency"] is True
    assert job["rank_penalty"] > 0


# ---------------------------------------------------------- B: JD-quality gate
def test_thin_jd_is_not_scoreable():
    thin = "At Visa, you'll have the opportunity to make an impact on the world."
    q = assess_jd(thin)
    assert q.scoreable is False
    assert "insufficient_jd" in q.reason


def test_rich_jd_is_scoreable():
    rich = (
        "Responsibilities: Design and build scalable services in Python and Go. "
        "Requirements: 5+ years experience with Kubernetes, Docker, AWS, and "
        "PostgreSQL. Preferred qualifications: Terraform, Kafka, CI/CD pipelines."
    )
    q = assess_jd(rich)
    assert q.scoreable is True
    assert q.depth in {"moderate", "rich"}
    assert q.keyword_count >= 2


def test_strip_boilerplate_removes_marketing():
    jd = (
        "At Visa, you'll change the world.\n"
        "We are an equal opportunity employer.\n"
        "Requirements: Python, AWS, 3+ years experience."
    )
    out = strip_boilerplate(jd)
    assert "Requirements: Python" in out
    assert "equal opportunity" not in out


def test_resume_projects_split_when_pdf_glues_next_header_to_bullet():
    resume = """
PROJECTS
AI-Powered Vulnerability Detection Framework Tools: FastAPI, React, PostgreSQL
• Built a vulnerability scanning platform.
• Surfaced remediation guidance. AI-Powered Malware Analysis Scanner Tools: Python, FastAPI, Docker
• Built a file-triage tool for suspicious payloads.
EDUCATION
Master of Science in Cybersecurity
"""

    parsed = resume_text_to_json(resume)

    assert parsed["schema_version"] == RESUME_SCHEMA_VERSION
    assert parsed["projects"] == [
        "AI-Powered Vulnerability Detection Framework Tools: FastAPI, React, PostgreSQL",
        "• Built a vulnerability scanning platform.",
        "• Surfaced remediation guidance.",
        "AI-Powered Malware Analysis Scanner Tools: Python, FastAPI, Docker",
        "• Built a file-triage tool for suspicious payloads.",
    ]


def test_resume_skills_are_preserved_and_activities_do_not_leak_into_projects():
    resume = """
TECHNICAL SKILLS
Security Operations: SIEM (Splunk), incident response, EDR (Microsoft Defender, SentinelOne)
Identity & Access Management: Microsoft Entra ID (Azure AD), MFA, Conditional Access, RBAC
PROJECTS
AI-Powered Vulnerability Detection Framework Tools: FastAPI, React, PostgreSQL
- Built a vulnerability scanning platform. SECURITY RESEARCH & COMMUNITY
- Active hands-on security practice across TryHackMe and Hack The Box.
EDUCATION
Master of Science in Cybersecurity
"""

    parsed = resume_text_to_json(resume)

    lowered_skills = {skill.lower() for skill in parsed["skills"]}
    assert {"splunk", "sentinelone", "conditional access", "microsoft entra id"} <= lowered_skills
    assert all("tryhackme" not in line.lower() for line in parsed["projects"])
    assert any("tryhackme" in line.lower() for line in parsed["activities"])


def test_tight_experience_filter_rejects_any_explicit_higher_requirement():
    description = "Requires 2+ years with Python and 8+ years of security operations experience."

    assert parse_years(description)[0] == 8
    assert not is_target_experience(
        "Security Analyst",
        years_min=2,
        years_max=None,
        max_years=2,
        description=description,
    )


def test_job_liveness_classifier_only_closes_high_confidence_pages():
    assert classify_job_page(404, "") == "closed"
    assert classify_job_page(200, "This job is no longer available.") == "closed"
    assert classify_job_page(403, "Access denied") == "unknown"
    assert classify_job_page(429, "Too many requests") == "unknown"
    assert classify_job_page(200, "Apply for this Security Analyst position") == "active"


def test_match_sort_never_lifts_a_lower_score_for_freshness():
    older_high_match = {
        "id": "high",
        "match_score": 91,
        "relevance_tier": 0,
        "posted_at": "2026-07-01T12:00:00+00:00",
        "source_name": "linkedin",
    }
    fresh_lower_match = {
        "id": "lower",
        "match_score": 84,
        "relevance_tier": 0,
        "posted_at": "2026-07-11T12:00:00+00:00",
        "source_name": "greenhouse",
    }

    ranked = sorted([fresh_lower_match, older_high_match], key=_projection_sort_key)
    assert [job["id"] for job in ranked] == ["high", "lower"]


def test_effective_job_date_does_not_make_old_post_current_when_reverified():
    from app.api.jobs import _job_effective_datetime

    job = {
        "posted_at": "2026-01-12T12:00:00+00:00",
        "first_seen_at": "2026-01-12T12:00:00+00:00",
        "last_seen_at": "2026-07-12T12:00:00+00:00",
    }

    assert _job_effective_datetime(job) == datetime(2026, 1, 12, 12, 0, tzinfo=timezone.utc)


def test_effective_job_date_uses_first_collected_when_ats_omits_posted_date():
    from app.api.jobs import _job_effective_datetime

    job = {
        "posted_at": None,
        "first_seen_at": "2026-07-12T12:00:00+00:00",
        "last_seen_at": "2026-07-12T13:00:00+00:00",
    }

    assert _job_effective_datetime(job) == datetime(2026, 7, 12, 12, 0, tzinfo=timezone.utc)


def test_default_jobs_visibility_is_a_rolling_24_hours():
    from app.api.jobs import _visible_jobs_cutoff

    before = datetime.now(timezone.utc)
    cutoff = _visible_jobs_cutoff()
    after = datetime.now(timezone.utc)

    assert before - timedelta(hours=24, seconds=1) <= cutoff
    assert cutoff <= after - timedelta(hours=23, minutes=59, seconds=59)


def test_explicit_24h_filter_is_a_rolling_window():
    from app.api.jobs import _posted_window

    before = datetime.now(timezone.utc)
    cutoff, end = _posted_window("24h")
    after = datetime.now(timezone.utc)

    assert end is None
    assert cutoff is not None
    assert before - timedelta(hours=24, seconds=1) <= cutoff
    assert cutoff <= after - timedelta(hours=23, minutes=59, seconds=59)


def test_jobs_endpoint_default_page_size_matches_frontend_contract():
    import inspect

    from app.api.jobs import list_jobs

    page_size_query = inspect.signature(list_jobs).parameters["page_size"].default

    assert page_size_query.default == 40
    assert "40-per-page" in page_size_query.description


def test_exact_country_query_avoids_redundant_scope_and_coalesce_scan():
    client = PostgresClient.__new__(PostgresClient)
    stmt = client._apply_master_job_filters(select(MasterJob.id), {
        "status": "active",
        "country": "IN",
        "effective_since": datetime(2026, 7, 1, tzinfo=timezone.utc),
        "title_terms": ["security analyst", "systems engineer"],
    })
    sql = str(stmt.compile(dialect=postgresql.dialect())).lower()

    assert "upper(master_jobs.country)" not in sql
    assert "coalesce(master_jobs.posted_at" not in sql
    assert "master_jobs.country =" in sql
    assert "master_jobs.last_seen_at" in sql


def test_honest_freshness_filter_uses_first_seen_only_when_posted_date_is_missing():
    client = PostgresClient.__new__(PostgresClient)
    cutoff = datetime(2026, 7, 12, tzinfo=timezone.utc)
    stmt = client._apply_master_job_filters(select(MasterJob.id), {
        "status": "active",
        "seen_since": cutoff,
        "honest_since": cutoff,
    })
    sql = str(stmt.compile(dialect=postgresql.dialect())).lower()

    assert "master_jobs.posted_at >=" in sql
    assert "master_jobs.posted_at is null" in sql
    assert "master_jobs.first_seen_at >=" in sql
    assert "coalesce(master_jobs.posted_at" not in sql


def test_frontend_complete_jd_filter_is_enforced_in_sql_and_loads_full_text():
    client = PostgresClient.__new__(PostgresClient)
    filters = {"status": "active", "complete_jd_only": True, "full_description": True}
    stmt = client._apply_master_job_filters(select(MasterJob.id), filters)
    compiled = stmt.compile(dialect=postgresql.dialect())
    sql = str(compiled).lower()

    assert "length(trim(coalesce(master_jobs.description" in sql
    assert "jd_complete" in compiled.params.values()
    assert "master_jobs.description ilike" in sql
    assert 1800 in compiled.params.values()
    assert client._needs_full_description(filters) is True

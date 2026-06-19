"""Tests for the scraper/scoring quality fixes (A3, A4, A5, B)."""

from __future__ import annotations

import pytest

from app.utils.glued_words import deglue_text, looks_glued
from app.utils.job_quality import job_description_text
from app.services.employer_normalizer import (
    normalize_employer, resolve_approval_rate, build_registry,
)
from app.services.staffing_filter import classify_staffing, apply_staffing_flag
from app.services.jd_quality_gate import assess_jd, strip_boilerplate


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

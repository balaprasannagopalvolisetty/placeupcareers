import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.etl.api_sources.connectors import adzuna, greenhouse
from app.etl.api_sources.connectors.career_site_feed import detect_portal
from app.etl.api_sources.schema import stable_job_id


def test_adzuna_normalize_outputs_shared_schema():
    job = adzuna._normalize(
        {
            "id": "adz-123",
            "title": "Software Engineer",
            "company": {"display_name": "ExampleCo"},
            "redirect_url": "https://example.com/jobs/adz-123",
            "location": {"display_name": "New York, NY"},
            "description": "<p>Build remote-friendly APIs.</p>",
            "created": "2026-06-01T12:00:00Z",
            "category": {"label": "IT Jobs"},
            "salary_min": 100000,
            "salary_max": 140000,
        },
        "us",
    )

    assert job is not None
    assert job.job_id == stable_job_id("adzuna", "adz-123")
    assert job.source == "adzuna"
    assert job.company == "ExampleCo"
    assert job.country == "US"
    assert job.remote is True
    assert "Build remote-friendly APIs." in job.description


def test_greenhouse_normalize_outputs_shared_schema():
    job = greenhouse._normalize(
        {
            "id": 456,
            "title": "Data Engineer",
            "absolute_url": "https://boards.greenhouse.io/example/jobs/456",
            "offices": [{"name": "London, United Kingdom"}],
            "departments": [{"name": "Engineering"}],
            "content": "<div>Own data pipelines.</div>",
            "updated_at": "2026-06-01T08:30:00Z",
        },
        "example-company",
    )

    assert job is not None
    assert job.job_id == stable_job_id("greenhouse", "456")
    assert job.source == "greenhouse"
    assert job.company == "Example Company"
    assert job.country == "GB"
    assert "Own data pipelines." in job.description


def test_career_site_feed_detects_requested_ats_platforms():
    samples = {
        "https://company.wd5.myworkdayjobs.com/External": "Workday",
        "https://careers.icims.com/jobs/123": "iCIMS",
        "https://workforcenow.adp.com/jobs/apply/posting.html": "ADP",
        "https://boards.greenhouse.io/example": "Greenhouse",
        "https://jobs.oraclecloud.com/jobs/123": "Oracle Cloud HCM",
        "https://recruiting.paylocity.com/recruiting/jobs/List/123": "Paylocity",
        "https://recruiting.ultipro.com/company": "UKG / UltiPro",
        "https://jobs.lever.co/example": "Lever",
        "https://jobs.smartrecruiters.com/Example/123": "SmartRecruiters",
        "https://example.bamboohr.com/careers": "BambooHR",
        "https://apply.workable.com/example": "Workable",
        "https://jobs.ashbyhq.com/example": "Ashby",
        "https://ats.rippling.com/example/jobs": "Rippling",
        "https://www.dayforcehcm.com/CandidatePortal/en-US/example": "Dayforce",
        "https://example.zohorecruit.com/jobs": "Zoho Recruit",
        "https://jobs.jobvite.com/example": "Jobvite",
        "https://example.breezy.hr": "BreezyHR",
        "https://example.careers-page.com": "Recruitee",
        "https://jobs.example.successfactors.com": "SAP SuccessFactors",
        "https://example.pinpointhq.com": "Pinpoint",
        "https://jobs.polymer.co/example": "Polymer",
        "https://example.phenompeople.com": "Phenom",
        "https://app.dover.com/jobs/example": "Dover",
        "https://jobs.gem.com/example": "Gem",
        "https://join.com/companies/example": "JOIN",
        "https://app.hireology.com/jobs": "Hireology",
    }
    for url, expected in samples.items():
        assert detect_portal(url) == expected

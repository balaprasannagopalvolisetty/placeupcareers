import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.etl.api_sources.connectors import adzuna, greenhouse
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

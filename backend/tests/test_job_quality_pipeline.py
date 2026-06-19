from app.etl.normalizers.jobs import normalize_job_payload
from app.utils.job_quality import has_usable_job_description, sanitize_job_description_html


def _full_description() -> str:
    return (
        "<h2>Responsibilities</h2><ul><li>Build reliable data services for global users.</li>"
        "<li>Collaborate with product and security teams on production releases.</li></ul>"
        "<h2>Qualifications</h2><p>Five years of Python, SQL, cloud infrastructure, "
        "testing, monitoring, incident response, and API design experience are required. "
        "The engineer will own architecture reviews, documentation, deployment quality, "
        "and measurable improvements to performance and availability.</p>"
    )


def test_normalizer_preserves_safe_html_and_text() -> None:
    normalized = normalize_job_payload({
        "id": "job-1",
        "title": "Platform Engineer",
        "company": "Example Corp",
        "location": "Chicago, IL",
        "description": _full_description() + "<script>alert('x')</script>",
        "job_url": "https://example.com/jobs/1",
        "source": "greenhouse",
    })

    assert normalized["status"] == "active"
    assert "Responsibilities" in normalized["description"]
    assert "<li>" not in normalized["description"]
    assert "<ul>" in normalized["extra_metadata"]["description_html"]
    assert "script" not in normalized["extra_metadata"]["description_html"]


def test_incomplete_job_is_quarantined_and_zero_salary_is_null() -> None:
    normalized = normalize_job_payload({
        "id": "job-2",
        "title": "Engineer",
        "company": "Example Corp",
        "location": "",
        "description": "Short description.",
        "job_url": "",
        "salary": {"min_salary": 0, "max_salary": "0"},
        "source": "linkedin",
    })

    assert normalized["status"] == "quarantined"
    assert normalized["salary_min"] is None
    assert normalized["salary_max"] is None
    assert set(normalized["extra_metadata"]["validation_errors"]) >= {
        "thin or missing job description",
        "missing apply URL",
        "missing location",
    }


def test_quality_gate_requires_250_clean_characters() -> None:
    assert not has_usable_job_description("Responsibilities: " + "build systems " * 10)
    assert has_usable_job_description(_full_description())
    assert sanitize_job_description_html("plain text only") is None

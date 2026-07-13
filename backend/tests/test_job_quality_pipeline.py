from app.etl.normalizers.jobs import normalize_job_payload
from app.etl.loaders.jobs import _enforce_complete_jd_policy
from app.utils.job_quality import (
    COMPLETE_JD_POLICY_VERSION,
    complete_job_description_reason,
    has_complete_job_description,
    has_usable_job_description,
    sanitize_job_description_html,
)


def _full_description() -> str:
    core = (
        "<h2>Responsibilities</h2><ul><li>Build reliable data services for global users.</li>"
        "<li>Collaborate with product and security teams on production releases.</li></ul>"
        "<h2>Qualifications</h2><p>Five years of Python, SQL, cloud infrastructure, "
        "testing, monitoring, incident response, and API design experience are required. "
        "The engineer will own architecture reviews, documentation, deployment quality, "
        "and measurable improvements to performance and availability.</p>"
    )
    detail = " The role includes architecture, implementation, testing, documentation, monitoring, security reviews, stakeholder collaboration, incident response, mentoring, deployment, performance analysis, and continuous improvement."
    return core + detail * 8


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
    assert normalized["extra_metadata"]["jd_complete"] is True
    assert normalized["extra_metadata"]["jd_completeness_policy"] == COMPLETE_JD_POLICY_VERSION


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
        "incomplete job description: job description below 1200 characters",
        "missing apply URL",
        "missing location",
    }


def test_quality_gate_requires_250_clean_characters() -> None:
    assert not has_usable_job_description("Responsibilities: " + "build systems " * 10)
    assert has_usable_job_description(_full_description())
    assert sanitize_job_description_html("plain text only") is None


def test_locked_complete_jd_contract_rejects_long_truncated_snippets() -> None:
    truncated = "Responsibilities: " + ("Build reliable production systems with Python and cloud services. " * 30) + "Read more"
    assert not has_complete_job_description(truncated)
    assert complete_job_description_reason(truncated) == "job description has a truncation marker"


def test_locked_complete_jd_contract_accepts_full_structured_posting() -> None:
    assert has_complete_job_description(_full_description())
    assert complete_job_description_reason(_full_description()) is None


def test_loader_cannot_be_bypassed_by_pre_normalized_api_sources() -> None:
    row = _enforce_complete_jd_policy({
        "description": "A short API summary",
        "status": "active",
        "extra_metadata": {"api_source_schema": True},
    })
    assert row["status"] == "quarantined"
    assert row["extra_metadata"]["jd_complete"] is False
    assert row["extra_metadata"]["jd_completeness_policy"] == COMPLETE_JD_POLICY_VERSION


def test_loader_marks_repaired_complete_jd_active() -> None:
    row = _enforce_complete_jd_policy({
        "description": _full_description(),
        "status": "quarantined",
        "extra_metadata": {
            "validation_errors": ["incomplete job description: old rule"],
        },
    })
    assert row["status"] == "active"
    assert row["extra_metadata"]["jd_complete"] is True
    assert "validation_errors" not in row["extra_metadata"]

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from app.api.health import ats_coverage
from app.etl.api_sources.runner import _filter_requested_countries
from app.etl.api_sources.schema import NormalizedJob
from app.middleware.security import _is_public_read
from app.services.apply import tailoring_pipeline
from app.services.apply.tailoring_pipeline import TAILORING_PIPELINE_VERSION
from app.services import resume_tailor_llm


def _job(country: str, location: str, source_id: str) -> NormalizedJob:
    return NormalizedJob(
        job_id=source_id,
        source="greenhouse",
        source_job_id=source_id,
        title="Security Engineer",
        company="Example",
        location=location,
        country=country,
        url=f"https://example.test/{source_id}",
        description="Responsibilities and qualifications " * 20,
    )


def test_whole_board_connectors_are_isolated_to_matrix_country():
    rows = [
        _job("US", "Austin, TX, US", "us"),
        _job("DE", "Berlin, DE", "de"),
        _job("", "Remote", "unknown"),
    ]

    assert [row.job_id for row in _filter_requested_countries(rows, ["US"])] == ["us"]
    assert [row.job_id for row in _filter_requested_countries(rows, ["US", "DE"])] == ["us", "de", "unknown"]


def test_tailoring_score_calls_real_async_services(monkeypatch):
    from app.services import ats_scorer, match_engine

    async def match(*_args, **_kwargs):
        return SimpleNamespace(overall_match_score=73)

    async def ats(*_args, **_kwargs):
        return SimpleNamespace(overall_score=81.4)

    monkeypatch.setattr(match_engine, "compute_match_score", match)
    monkeypatch.setattr(ats_scorer, "score_resume_against_job", ats)
    result = asyncio.run(tailoring_pipeline._score(
        "Experience and education with security engineering. " * 8,
        {"title": "Security Engineer", "company": "Example", "description": "Requirements " * 30},
    ))
    assert result == (73, 81)


def test_tailoring_regenerates_broken_cache_and_uses_deterministic_fallback(monkeypatch):
    async def no_llm(**_kwargs):
        return None

    async def no_cover(**_kwargs):
        return None

    scores = iter([(42, 51), (68, 76)])

    async def score(*_args, **_kwargs):
        return next(scores)

    monkeypatch.setattr(resume_tailor_llm, "tailor_resume", no_llm)
    monkeypatch.setattr(resume_tailor_llm, "generate_cover_letter", no_cover)
    monkeypatch.setattr(tailoring_pipeline, "_score", score)

    class Store:
        saved = None

        def get_tailored_docs(self, *_args):
            return {"pipeline_version": 1, "resume_url": None, "match_score": 0}

        def render_and_store_tailored(self, _uid, _company, spec, cover, _position):
            assert spec["resume"]["experience"]
            assert cover.startswith("Dear Hiring Team,")
            return {
                "resume_url": "gs://docs/resume.pdf",
                "cover_letter_url": "gs://docs/cover.pdf",
            }

        def save_tailored_docs(self, _uid, _company, data, _position):
            self.saved = data

    store = Store()
    resume = """Bala Example
bala@example.com | Austin, TX
SUMMARY
Security engineer with cloud security experience.
SKILLS
Python, AWS, SIEM, Incident Response
EXPERIENCE
Security Engineer | Example Corp | Austin, TX | Jan 2022 - Present
Improved incident response using SIEM and Python automation.
EDUCATION
BS Computer Science | Example University | 2021
"""
    result = asyncio.run(tailoring_pipeline.run_tailoring(
        uid="u1",
        job={"id": "j1", "title": "Security Engineer", "company": "Acme", "description": "AWS SIEM incident response requirements " * 20},
        profile={"first_name": "Bala", "last_name": "Example", "email": "bala@example.com"},
        resume_id="r1",
        generate_cover_letter=True,
        store=store,
        resume_text=resume,
    ))

    assert result["pipeline_version"] == TAILORING_PIPELINE_VERSION
    assert result["resume_url"] == "gs://docs/resume.pdf"
    assert result["cover_letter_url"] == "gs://docs/cover.pdf"
    assert result["diff"]["tailoring_method"] == "deterministic"
    assert result["diff"]["score_before"] == {"match": 42, "ats": 51}
    assert result["diff"]["score_after"] == {"match": 68, "ats": 76}
    assert store.saved is result


def test_cover_letter_rejects_ungrounded_numeric_claim(monkeypatch):
    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"choices": [{"message": {"content": (
                "Dear Hiring Team,\n\nI improved security operations by 99% using Python and SIEM. "
                "My experience aligns with this role and I welcome a conversation.\n\nSincerely,\nBala"
            )}}]}

    class Client:
        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def post(self, *_args, **_kwargs):
            return Response()

    monkeypatch.setattr(resume_tailor_llm.httpx, "AsyncClient", Client)
    result = asyncio.run(resume_tailor_llm.generate_cover_letter(
        resume_text="Security engineer using Python and SIEM with documented operational improvements.",
        job_title="Security Engineer",
        job_company="Acme",
        job_description="Python and SIEM required",
        api_key="test-key",
    ))
    assert result is None


def test_ats_coverage_flags_low_direct_share(monkeypatch):
    from app.db import postgres

    class Client:
        def source_coverage_sync(self, hours=24):
            assert hours == 24
            return [
                {"source": "greenhouse", "count": 4},
                {"source": "indeed", "count": 96},
            ]

    monkeypatch.setattr(postgres, "PostgresClient", Client)
    monkeypatch.setenv("ATS_COVERAGE_MIN_FIRST_PARTY_SHARE", "0.05")
    result = asyncio.run(ats_coverage(hours=24))
    assert result["first_party_share"] == 0.04
    assert result["direct_ats_healthy"] is False
    assert result["supply_status"] == "degraded"


def test_ats_coverage_health_endpoint_is_public():
    assert _is_public_read("/api/health/ats-coverage") is True

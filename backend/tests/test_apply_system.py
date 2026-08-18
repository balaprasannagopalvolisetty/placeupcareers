"""
Tests for the automated application system (apply orchestration).

Covers the pure, deterministic logic — tier routing, adapter field mapping,
the orchestrator's review-before-submit state machine, and inbox OTP
extraction/classification — without any Firestore, network, or browser.
"""
from __future__ import annotations

import asyncio

import pytest

from app.models.application import ApplicationStatus, ATSTier, SubmissionMethod
from app.services.apply import tiers
from app.services.apply.base import get_adapter
from app.services.apply import orchestrator
from app.services.apply.inbox_ingest import (
    classify,
    extract_otp,
    link_to_application,
    parse_webhook,
)
from app.models.application import InboxClassification
from app.api.apply import _assert_profile_minimized, one_click_feed
from app.scrape_constants import FIRST_PARTY_ATS_SOURCES
from app.models.application import ApplicationProfile
from fastapi import HTTPException


# --------------------------- tier routing ---------------------------

def test_tier_a_platforms_resolve_to_api():
    for ats in ("greenhouse", "ashby", "smartrecruiters", "workable", "recruitee"):
        assert tiers.resolve_tier(ats) is ATSTier.A
        assert tiers.is_api_submittable(ats) is True


def test_partner_auth_tier_a_not_api_submittable():
    # Tier A but needs a partner token -> must fall back to the browser path.
    for ats in ("teamtailor", "jazzhr", "phenom"):
        assert tiers.resolve_tier(ats) is ATSTier.A
        assert tiers.is_api_submittable(ats) is False


def test_tier_c_and_unknown_go_to_browser():
    assert tiers.resolve_tier("workday") is ATSTier.C
    assert tiers.is_api_submittable("workday") is False
    # Unknown ATS defaults to the always-available browser path.
    assert tiers.resolve_tier("some-brand-new-ats") is ATSTier.C
    assert tiers.is_api_submittable("some-brand-new-ats") is False


def test_tier_b_employer_key_not_api_submittable():
    for ats in ("workday", "oracle", "successfactors", "adp", "icims"):
        assert tiers.is_api_submittable(ats) is False


def test_alias_normalization():
    assert tiers.resolve_tier("Oracle Recruiting") is ATSTier.B
    assert tiers.resolve_tier("SAP SuccessFactors") is ATSTier.B
    assert tiers.resolve_tier("Zoho Recruit") is ATSTier.B


def test_ats_inference_uses_metadata_and_canonical_url():
    assert tiers.infer_ats_type({"source_name": "tier1_ats", "extra_metadata": {"ats": "ashby"}}) == "ashby"
    assert tiers.infer_ats_type({"source_name": "tier1_ats", "source_url": "https://jobs.lever.co/acme/123"}) == "lever"
    assert tiers.infer_ats_type({"source_url": "https://acme.wd5.myworkdayjobs.com/en-US/jobs/job/1"}) == "workday"


def test_one_click_feed_filters_direct_ats_sources_in_database(monkeypatch):
    from app.api import jobs as jobs_api

    async def no_resume(_uid):
        return None

    monkeypatch.setattr(jobs_api, "_preference_terms", lambda _uid: ([], []))
    monkeypatch.setattr(jobs_api, "_active_resume_text", no_resume)

    class FakeJobsDb:
        def __init__(self):
            self.filters = None

        async def get_jobs(self, *, filters, limit, offset):
            self.filters = filters
            return [{
                "id": "job-1",
                "title": "Security Engineer",
                "company": "Acme",
                "location": "New York, NY",
                "source_name": "recruitee",
                "source_url": "https://acme.recruitee.com/o/security-engineer",
            }]

    fake_db = FakeJobsDb()
    result = asyncio.run(one_click_feed(limit=60, page=1, page_size=40, ready_only=False, uid="u1", db=fake_db))

    assert fake_db.filters["sources"] == sorted(FIRST_PARTY_ATS_SOURCES)
    assert [job["job_id"] for job in result["jobs"]] == ["job-1"]
    assert result["jobs"][0]["ats_type"] == "recruitee"
    assert result["total"] == 1
    assert result["total_pages"] == 1


def test_one_click_feed_personalizes_scores_and_paginates(monkeypatch):
    from app.api import jobs as jobs_api

    async def active_resume(_uid):
        return "Security engineer with Python, AWS, SIEM, and incident response experience."

    monkeypatch.setattr(
        jobs_api,
        "_preference_terms",
        lambda _uid: (["security engineer"], ["united states"]),
    )
    monkeypatch.setattr(jobs_api, "_active_resume_text", active_resume)
    monkeypatch.setattr(jobs_api, "_prepare_resume_tokens", lambda _text: {})
    monkeypatch.setattr(
        jobs_api,
        "_cached_score_job_against_resume",
        lambda _resume, job_text, **_kw: 91 if "Cloud" in job_text else (78 if "Product" in job_text else 66),
    )

    class FakeJobsDb:
        def __init__(self):
            self.filters = None

        async def get_jobs(self, *, filters, limit, offset):
            self.filters = filters
            return [
                {"id": "j1", "title": "Security Engineer", "company": "A", "country": "", "location": "New York, NY", "source": "greenhouse", "job_url": "https://boards.greenhouse.io/a/jobs/1", "description": "security role"},
                {"id": "j2", "title": "Cloud Security Engineer", "company": "B", "country": "US", "source": "ashby", "job_url": "https://jobs.ashbyhq.com/b/2", "description": "cloud role"},
                {"id": "j3", "title": "Product Security Engineer", "company": "C", "country": "US", "source": "smartrecruiters", "job_url": "https://jobs.smartrecruiters.com/c/3", "description": "product role"},
            ]

        async def get_job_descriptions(self, job_ids):
            return {job_id: f"Complete responsibilities and qualifications for {job_id}. " * 30 for job_id in job_ids}

    fake_db = FakeJobsDb()
    result = asyncio.run(one_click_feed(limit=None, page=1, page_size=2, ready_only=False, uid="u1", db=fake_db))

    # Country is resolved from each ATS posting's location after the query so
    # rows with "New York, NY" and a blank country column are not lost.
    assert "country" not in fake_db.filters
    assert "security engineer" in [term.lower() for term in fake_db.filters["title_terms"]]
    assert result["total"] == 3
    assert result["total_pages"] == 2
    assert [job["job_id"] for job in result["jobs"]] == ["j2", "j3"]
    assert [job["match_score"] for job in result["jobs"]] == [91, 78]
    assert result["jobs"][0]["job_url"].startswith("https://")


def test_prepare_rejects_missing_job_instead_of_creating_empty_application():
    store = FakeStore({})
    with pytest.raises(ValueError, match="job not found"):
        asyncio.run(orchestrator.prepare_application(store, "u1", "missing", None, True, "", _fake_tailor))


# --------------------------- adapter mapping ---------------------------

def test_greenhouse_payload_builds_endpoint_and_validates_client_side():
    adapter = get_adapter("greenhouse")
    payload = adapter.build_payload(
        job={"board_token": "duolingo", "ats_job_id": "123"},
        profile={"first_name": "Bala", "last_name": "V", "email": "b@x.com"},
        answers={},
        resume_url="resume.pdf",
        cover_letter_url=None,
    )
    assert payload.endpoint == "https://boards-api.greenhouse.io/v1/boards/duolingo/jobs/123"
    assert payload.missing_required == []
    assert adapter.validate(payload) == []


def test_adapter_flags_missing_required_and_no_resume():
    adapter = get_adapter("greenhouse")
    payload = adapter.build_payload(
        job={"board_token": "acme", "ats_job_id": "1"},
        profile={"first_name": "", "last_name": "", "email": ""},
        answers={},
        resume_url=None,
        cover_letter_url=None,
    )
    problems = adapter.validate(payload)
    assert any("Missing required" in p for p in problems)
    assert any("No resume" in p for p in problems)


def test_smartrecruiters_moves_eeo_fields_last():
    adapter = get_adapter("smartrecruiters")
    payload = adapter.build_payload(
        job={"ats_job_id": "uuid-1"},
        profile={"first_name": "A", "last_name": "B", "email": "a@b.com"},
        answers={"gender": "F", "veteran_status": "No"},
        resume_url="r.pdf",
        cover_letter_url=None,
    )
    assert "gender" in payload.eeo_fields
    assert "veteran_status" in payload.eeo_fields
    assert "gender" not in payload.fields


def test_recruitee_builds_full_name():
    adapter = get_adapter("recruitee")
    payload = adapter.build_payload(
        job={"board_token": "hello", "ats_slug": "eng"},
        profile={"first_name": "Bala", "last_name": "V", "email": "b@x.com", "phone": "555-0100"},
        answers={},
        resume_url="r.pdf",
        cover_letter_url=None,
    )
    assert payload.fields["name"] == "Bala V"
    assert payload.endpoint == "https://hello.recruitee.com/api/offers/eng/candidates"


def test_recruitee_submit_dry_run_when_live_disabled():
    """With APPLY_LIVE_SUBMIT_ENABLED off, submit validates but does not POST."""
    from app.config import settings
    from app.services.apply.base import PreparedPayload

    adapter = get_adapter("recruitee")
    payload = PreparedPayload(
        ats_type="recruitee",
        endpoint="https://hello.recruitee.com/api/offers/eng/candidates",
        fields={"name": "Bala V", "email": "b@x.com", "phone": "555-0100"},
        attachments={"resume": "gs://private-bucket/tailored/u/job/resume.pdf"},
    )
    prev = settings.apply_live_submit_enabled
    settings.apply_live_submit_enabled = False
    try:
        result = asyncio.run(adapter.submit(payload))
    finally:
        settings.apply_live_submit_enabled = prev
    assert result.ok is True
    assert result.dry_run is True
    assert result.confirmation_ref == "DRYRUN"


def test_recruitee_submit_requires_name_and_email():
    """Even with live submit on, a missing email is rejected before any POST."""
    from app.config import settings
    from app.services.apply.base import PreparedPayload

    adapter = get_adapter("recruitee")
    payload = PreparedPayload(
        ats_type="recruitee",
        endpoint="https://hello.recruitee.com/api/offers/eng/candidates",
        fields={"name": "Bala V", "email": ""},
        attachments={},
    )
    prev = settings.apply_live_submit_enabled
    settings.apply_live_submit_enabled = True
    try:
        result = asyncio.run(adapter.submit(payload))
    finally:
        settings.apply_live_submit_enabled = prev
    assert result.ok is False


# --------------------------- orchestrator state machine ---------------------------

class FakeStore:
    def __init__(self, job):
        self._job = job
        self.apps: dict[str, dict] = {}

    def get_job(self, job_id):
        return dict(self._job)

    def get_profile(self, uid):
        return {"first_name": "Bala", "last_name": "V", "email": "b@x.com", "custom_answers": {}}

    def save_application(self, app):
        app.setdefault("id", "app-1")
        self.apps[app["id"]] = app
        return app

    def get_application(self, app_id):
        return self.apps.get(app_id)


async def _fake_tailor(**kwargs):
    return {"resume_url": "tailored.pdf", "match_score": 82, "ats_score": 71}


def test_production_document_storage_never_falls_back_to_local(tmp_path):
    from app.config import settings
    from app.services.apply import doc_storage

    previous = (settings.app_env, settings.apply_docs_bucket, settings.apply_docs_local_dir)
    settings.app_env = "production"
    settings.apply_docs_bucket = ""
    settings.apply_docs_local_dir = str(tmp_path)
    try:
        uri = doc_storage.store_document("u1", "Acme", "resume.pdf", b"pdf", position_key="job-1")
    finally:
        settings.app_env, settings.apply_docs_bucket, settings.apply_docs_local_dir = previous

    assert uri is None
    assert list(tmp_path.rglob("*")) == []


def test_dev_document_storage_round_trip_and_content_type(tmp_path):
    from app.config import settings
    from app.services.apply import doc_storage

    previous = (settings.app_env, settings.apply_docs_bucket, settings.apply_docs_local_dir)
    settings.app_env = "development"
    settings.apply_docs_bucket = ""
    settings.apply_docs_local_dir = str(tmp_path)
    try:
        uri = doc_storage.store_document(
            "u1", "Acme", "resume.pdf", b"%PDF-test", position_key="job-1"
        )
        assert uri is not None
        assert doc_storage.read_document(uri) == b"%PDF-test"
        assert doc_storage.content_type_for(uri) == "application/pdf"
    finally:
        settings.app_env, settings.apply_docs_bucket, settings.apply_docs_local_dir = previous


def test_resume_renderer_produces_pdf_and_docx_bytes():
    from app.services.apply.resume_renderer import render_all

    files = render_all({
        "name": "Bala V",
        "contact": ["b@example.com"],
        "summary": "Operations analyst.",
        "skills": [{"category": "Tools", "items": ["Excel", "SQL"]}],
        "experience": [],
        "education": [],
        "certifications": [],
        "projects": [],
    }, "Dear Hiring Team,\n\nThank you.\n\nSincerely,\nBala V")

    assert files["resume.pdf"].startswith(b"%PDF")
    assert files["resume.docx"].startswith(b"PK")
    assert files["cover_letter.pdf"].startswith(b"%PDF")
    assert files["cover_letter.docx"].startswith(b"PK")


def test_tailored_cache_key_is_per_position():
    from app.db.firestore_apply_store import _company_key

    assert _company_key("u1", "Acme", "job-1") != _company_key("u1", "Acme", "job-2")


def test_uncredentialed_tier_a_is_not_mislabeled_as_live_api_submit():
    store = FakeStore({
        "title": "SWE", "company": "Duolingo", "ats_type": "greenhouse",
        "board_token": "duolingo", "ats_job_id": "99", "job_url": "https://x",
        "description": "python fastapi",
    })
    app = asyncio.run(
        orchestrator.prepare_application(
            store, "u1", "job1", None, True, "note", _fake_tailor
        )
    )
    # Preparation-time handoff signals no longer dead-end the flow: the app
    # stays reviewable (Step 2 approve button) and the honest handoff happens
    # during the queued submit instead.
    assert app["status"] == ApplicationStatus.NEEDS_REVIEW.value
    assert app["submission_method"] == SubmissionMethod.BROWSER.value
    assert app["needs_you_reason"]
    assert app["match_score"] == 82


def test_unavailable_submit_path_cannot_be_approved_as_if_live():
    store = FakeStore({
        "title": "SWE", "company": "Duolingo", "ats_type": "greenhouse",
        "board_token": "duolingo", "ats_job_id": "99", "job_url": "https://x",
        "description": "python",
    })
    app = asyncio.run(
        orchestrator.prepare_application(store, "u1", "job1", None, True, "", _fake_tailor)
    )

    # confirm=False is rejected.
    with pytest.raises(ValueError):
        asyncio.run(
            orchestrator.approve_application(store, "u1", app["id"], False, {}, _noop_enqueue)
        )

    # A technically API-capable ATS without a configured working adapter can
    # be approved (the review gate still runs), but the submission must never
    # be faked as a live API success — the browser path hands off honestly.
    approved = asyncio.run(
        orchestrator.approve_application(store, "u1", app["id"], True, {"phone": "555"}, _inline_enqueue)
    )
    final = store.get_application(approved["id"]) or approved
    assert final["status"] != ApplicationStatus.APPLIED.value
    assert not final.get("confirmation_ref")


def test_prepare_tier_c_routes_to_browser_and_handoff():
    store = FakeStore({
        "title": "PM", "company": "Acme", "ats_type": "workday",
        "job_url": "https://wd", "description": "x",
    })
    app = asyncio.run(
        orchestrator.prepare_application(store, "u1", "job2", None, False, "", _fake_tailor)
    )
    assert app["submission_method"] == SubmissionMethod.BROWSER.value
    # No browser available in tests -> the handoff is recorded, but the app
    # remains reviewable so the user always reaches the Step 2 approve gate.
    assert app["status"] == ApplicationStatus.NEEDS_REVIEW.value
    assert app["needs_you_reason"]


async def _noop_enqueue(app_id, ats_type, coro_factory):
    return True


async def _inline_enqueue(app_id, ats_type, coro_factory):
    await coro_factory()  # run the submit immediately for the test
    return True


# --------------------------- inbox ingestion ---------------------------

def test_extract_otp_variants():
    assert extract_otp("Your verification code is 483920") == "483920"
    assert extract_otp("OTP: 1234 expires soon") == "1234"
    assert extract_otp("123456 is your security code") == "123456"
    assert extract_otp("no codes here, just text") is None


def test_classify_messages():
    assert classify("Application received", "Thank you for applying to Duolingo") is InboxClassification.CONFIRMATION
    assert classify("Next steps", "We'd like to schedule an interview") is InboxClassification.STATUS
    assert classify("Login", "Your verification code is 998877") is InboxClassification.OTP
    assert classify("Newsletter", "Weekly product updates") is InboxClassification.OTHER


def test_parse_webhook_and_link():
    msg = parse_webhook(
        {
            "to": "bala.v@mail.placeupcareer.com",
            "from": "jobs@duolingo.com",
            "subject": "Application received",
            "text": "Thank you for applying",
        },
        resolve_uid=lambda local: "u1" if local == "bala.v" else None,
    )
    assert msg is not None
    assert msg.uid == "u1"
    assert msg.classification is InboxClassification.CONFIRMATION
    linked = link_to_application(msg, [{"id": "app-1", "company": "Duolingo"}])
    assert linked == "app-1"


def test_parse_webhook_rejects_foreign_recipient():
    msg = parse_webhook(
        {"to": "someone@gmail.com", "from": "x@y.com", "subject": "s", "text": "t"},
        resolve_uid=lambda local: None,
    )
    assert msg is None


def test_application_profile_refuses_unencrypted_eeo_storage():
    with pytest.raises(HTTPException):
        _assert_profile_minimized(ApplicationProfile(uid="u1", eeo={"veteran_status": "No"}))
    _assert_profile_minimized(ApplicationProfile(uid="u1", work_authorization="OPT"))

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
from app.api.apply import _assert_profile_minimized
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
        profile={"first_name": "Bala", "last_name": "V", "email": "b@x.com"},
        answers={},
        resume_url="r.pdf",
        cover_letter_url=None,
    )
    assert payload.fields["name"] == "Bala V"
    assert payload.endpoint == "https://hello.recruitee.com/api/offers/eng/candidates"


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


def test_prepare_tier_a_reaches_needs_review_with_api_payload():
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
    assert app["status"] == ApplicationStatus.NEEDS_REVIEW.value
    assert app["submission_method"] == SubmissionMethod.API.value
    assert app["prepared_payload"]["endpoint"].startswith("https://boards-api.greenhouse.io")
    assert app["match_score"] == 82


def test_approve_requires_confirmation_then_submits():
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

    # confirm=True enqueues + runs the submit (Greenhouse submit is a configured
    # integration point -> NotImplementedError -> NEEDS_YOU/manual, never FAILED).
    asyncio.run(
        orchestrator.approve_application(store, "u1", app["id"], True, {"phone": "555"}, _inline_enqueue)
    )
    final = store.get_application(app["id"])
    assert final["status"] in (
        ApplicationStatus.NEEDS_YOU.value,
        ApplicationStatus.APPLIED.value,
    )
    kinds = [h["kind"] for h in final["history"]]
    assert "approved" in kinds


def test_prepare_tier_c_routes_to_browser_and_handoff():
    store = FakeStore({
        "title": "PM", "company": "Acme", "ats_type": "workday",
        "job_url": "https://wd", "description": "x",
    })
    app = asyncio.run(
        orchestrator.prepare_application(store, "u1", "job2", None, False, "", _fake_tailor)
    )
    assert app["submission_method"] == SubmissionMethod.BROWSER.value
    # No browser available in tests -> honest handoff to the user.
    assert app["status"] == ApplicationStatus.NEEDS_YOU.value


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

"""
Isolated tests for the clean-200 global board connectors.

No live network: HTTP is faked with httpx.MockTransport, and parsers are
exercised as pure functions on sample payloads. Run:
    pytest backend/tests/test_free_boards.py -q
"""
import asyncio
from datetime import datetime, timezone, timedelta

import httpx

from app.etl.sources import free_boards as fb
from app.etl.sources.free_boards_pipeline import dedupe, _is_recent, run_free_boards
from app.etl.sources.source_base import SourceHealth, guarded_source, safe_get_json, safe_get_text


# ─── pure parser tests ───────────────────────────────────────────────────────

def test_remoteok_skips_legal_header_and_parses_job():
    legal = {"legal": "RemoteOK API terms..."}
    job = {"id": "123", "position": "Backend Engineer", "company": "Acme",
           "location": "Worldwide", "url": "https://remoteok.com/x", "tags": ["python"],
           "epoch": 1748000000}
    assert fb.remoteok_item_to_jobpost(legal) is None
    jp = fb.remoteok_item_to_jobpost(job)
    assert jp is not None
    assert jp.title == "Backend Engineer"
    assert jp.company == "Acme"
    assert jp.is_remote is True
    assert jp.extra_metadata["english_friendly"] is True
    assert jp.content_hash  # dedup key present


def test_remotive_arbeitnow_jobicy_parse():
    assert fb.remotive_item_to_jobpost({"title": "Data Eng", "company_name": "Globex",
        "url": "u", "candidate_required_location": "Europe"}).company == "Globex"
    an = fb.arbeitnow_item_to_jobpost({"title": "Dev", "company_name": "Berlin GmbH",
        "slug": "dev-1", "url": "u", "remote": True, "tags": ["visa sponsorship"]})
    assert an.is_remote is True and an.extra_metadata["visa_mentioned"] is True
    assert fb.jobicy_item_to_jobpost({"jobTitle": "PM", "companyName": "Remote Co",
        "url": "u", "jobGeo": "Anywhere"}).title == "PM"


def test_wwr_rss_splits_company_and_title():
    xml = """<rss><channel>
      <item><title>Acme Corp: Senior Rust Engineer</title>
        <region>Anywhere</region><link>https://wwr/x</link>
        <pubDate>Mon, 02 Jun 2026 12:00:00 +0000</pubDate>
        <description>Great role</description></item>
    </channel></rss>"""
    jobs = fb.parse_wwr_rss(xml)
    assert len(jobs) == 1
    assert jobs[0].company == "Acme Corp"
    assert jobs[0].title == "Senior Rust Engineer"
    assert jobs[0].posted_at is not None


def test_missing_required_fields_returns_none():
    assert fb.remoteok_item_to_jobpost({"company": "NoTitle"}) is None
    assert fb.remotive_item_to_jobpost({"title": "", "company_name": ""}) is None


# ─── dedup + recency ─────────────────────────────────────────────────────────

def test_dedupe_collapses_identical_content():
    a = fb.remoteok_item_to_jobpost({"id": "1", "position": "Eng", "company": "X", "location": "Remote", "url": "u1"})
    b = fb.remoteok_item_to_jobpost({"id": "2", "position": "Eng", "company": "X", "location": "Remote", "url": "u2"})
    assert a.content_hash == b.content_hash       # same title/company/location → same hash
    assert len(dedupe([a, b])) == 1


def test_recency_window():
    now = datetime.now(timezone.utc)
    fresh = fb.remoteok_item_to_jobpost({"id": "1", "position": "Eng", "company": "X", "url": "u",
                                         "epoch": int(now.timestamp())})
    old = fb.remoteok_item_to_jobpost({"id": "2", "position": "Old", "company": "Y", "url": "u",
                                       "epoch": int((now - timedelta(hours=48)).timestamp())})
    cutoff = now - timedelta(hours=8)
    assert _is_recent(fresh, cutoff=cutoff) is True
    assert _is_recent(old, cutoff=cutoff) is False


# ─── circuit breaker + guarded source ────────────────────────────────────────

def test_circuit_breaker_trips_after_threshold():
    h = SourceHealth(threshold=3)
    for _ in range(2):
        h.record_fail("remoteok", "boom")
    assert h.is_open("remoteok") is False
    h.record_fail("remoteok", "boom")
    assert h.is_open("remoteok") is True          # 3rd consecutive failure opens it


def test_guarded_source_swallows_exceptions():
    h = SourceHealth()
    async def _boom():
        raise RuntimeError("network down")
    out = asyncio.run(guarded_source("x", _boom, health=h))
    assert out == []                               # never raises into the pipeline
    assert "fail" in h.summary()["x"]


# ─── safe_get_* only accepts 200 ─────────────────────────────────────────────

def _client_returning(status: int, body: str):
    def handler(request):
        return httpx.Response(status, text=body)
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def test_safe_get_json_returns_data_on_200():
    async def go():
        async with _client_returning(200, '{"ok": true}') as c:
            return await safe_get_json("https://x", client=c)
    assert asyncio.run(go()) == {"ok": True}


def test_safe_get_text_returns_none_on_403_404_500():
    async def go(status):
        async with _client_returning(status, "blocked") as c:
            return await safe_get_text("https://x", client=c, retries=0)
    for status in (403, 404, 500, 999):
        assert asyncio.run(go(status)) is None     # only 200 is accepted


def test_full_pipeline_with_mocked_sources(monkeypatch):
    """run_free_boards de-dupes, applies recency, and survives a failing source."""
    now = datetime.now(timezone.utc)
    good = fb.remoteok_item_to_jobpost({"id": "1", "position": "Eng", "company": "X", "url": "u",
                                        "epoch": int(now.timestamp())})

    async def ok_source(**kwargs):
        return [good]

    async def bad_source(**kwargs):
        raise RuntimeError("429 storm")

    monkeypatch.setattr(fb, "scrape_remoteok", ok_source)
    monkeypatch.setattr(fb, "scrape_remotive", bad_source)
    # point the pipeline registry at our two fakes
    import app.etl.sources.free_boards_pipeline as pipe
    monkeypatch.setattr(pipe, "FREE_BOARD_SOURCES", {"remoteok": ok_source, "remotive": bad_source})

    jobs, status = asyncio.run(run_free_boards(hours=8))
    assert len(jobs) == 1
    assert status["remotive"].startswith("fail")
    assert status["remoteok"] == "ok"

import asyncio

from app.models.job import JobSource
from app.services import careers_ats


def test_freshteam_public_feed_normalizes_full_job(monkeypatch):
    async def fake_json(url, **kwargs):
        assert url == "https://acme.freshteam.com/hire/widgets/jobs.json"
        return {"jobs": [{
            "id": 42,
            "title": "Platform Engineer",
            "url": "https://acme.freshteam.com/jobs/42",
            "description": "<p>Build reliable systems.</p>",
            "created_at": "2026-07-12T09:30:00Z",
            "branch": {"city": "Berlin", "country_code": "DE"},
        }]}

    monkeypatch.setattr(careers_ats, "_http_json", fake_json)
    jobs = asyncio.run(careers_ats.scrape_freshteam_board("acme"))

    assert len(jobs) == 1
    assert jobs[0].source == JobSource.FRESHTEAM
    assert jobs[0].description == "Build reliable systems."
    assert jobs[0].location == "Berlin, DE"
    assert jobs[0].posted_at is not None


def test_jobylon_public_feed_preserves_company_and_description(monkeypatch):
    async def fake_json(url, **kwargs):
        assert kwargs["params"] == {"format": "json"}
        return [{
            "id": "job-7",
            "title": "Data Scientist",
            "company": {"name": "Example AB"},
            "locations": [{"location": {"text": "Stockholm, Sweden"}}],
            "urls": {"ad": "https://example.jobylon.com/jobs/7"},
            "descr": "<div>Model customer demand.</div>",
            "from_date": "2026-07-12T08:00:00Z",
        }]

    monkeypatch.setattr(careers_ats, "_http_json", fake_json)
    jobs = asyncio.run(careers_ats.scrape_jobylon_board("example-feed"))

    assert len(jobs) == 1
    assert jobs[0].source == JobSource.JOBYLON
    assert jobs[0].company == "Example AB"
    assert jobs[0].description == "Model customer demand."


def test_server_rendered_new_ats_boards_dispatch_jobs(monkeypatch):
    pages = {
        "https://www.comeet.com/jobs/acme": (
            '<a href="/jobs/acme/ABC123">Backend Engineer</a>'
        ),
        "https://acme.homerun.co": (
            '<a href="/senior-product-designer">Senior Product Designer</a>'
        ),
        "https://acme.catsone.com/careers": (
            '<a href="/careers/987-general-manager">General Manager</a>'
        ),
    }

    async def fake_text(url, **kwargs):
        return pages[url]

    monkeypatch.setattr(careers_ats, "_http_text", fake_text)
    comeet = asyncio.run(careers_ats.scrape_comeet_board("acme"))
    homerun = asyncio.run(careers_ats.scrape_homerun_board("acme"))
    cats = asyncio.run(careers_ats.scrape_catsone_board("acme"))

    assert comeet[0].source == JobSource.COMEET
    assert comeet[0].job_url == "https://www.comeet.com/jobs/acme/ABC123"
    assert homerun[0].source == JobSource.HOMERUN
    assert cats[0].source == JobSource.CATSONE


def test_all_new_platform_aliases_are_dispatchable():
    expected = {"freshteam", "jobylon", "comeet", "homerun", "catsone", "eightfold"}
    assert expected <= set(careers_ats.ATS_DISPATCH)

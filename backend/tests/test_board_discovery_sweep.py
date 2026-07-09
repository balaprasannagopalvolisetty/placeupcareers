from app.services.careers_page_ingest import _WORKDAY_URL_RE, detect_ats_from_url
from app.services.careers_ats import ATS_DISPATCH
from app.services.company_career_resolver import PROBE_ATS
from app.services.company_career_resolver import _slug_candidates
from app.workers.board_discovery_sweep import _is_credible_company_name


def test_numbered_company_names_are_not_used_as_ats_tokens():
    assert not _is_credible_company_name("1295416 Alberta Ltd")
    assert _slug_candidates("1295416 Alberta Ltd") == []


def test_workday_url_detector_supports_jobs_and_site_domains():
    jobs_match = _WORKDAY_URL_RE.search("https://nvidia.wd5.myworkdayjobs.com/External")
    site_match = _WORKDAY_URL_RE.search("https://foo.wd1.myworkdaysite.com/en-US/recruiting/bar/External/jobs")

    assert jobs_match is not None
    assert jobs_match.groups() == ("nvidia", "wd5", "myworkdayjobs", "External")
    assert site_match is not None
    assert site_match.groups() == ("foo", "wd1", "myworkdaysite", "External")


def test_company_resolver_probes_all_slug_based_ats_platforms():
    # Workday needs a (tenant, site) tuple and is discovered from URLs/page HTML.
    assert set(PROBE_ATS) == set(ATS_DISPATCH)


def test_careers_page_ingest_detects_direct_structured_ats_urls():
    samples = {
        "https://boards.greenhouse.io/example": ("greenhouse", "example"),
        "https://boards.greenhouse.io/embed/job_board?for=example": ("greenhouse", "example"),
        "https://jobs.lever.co/example": ("lever", "example"),
        "https://jobs.ashbyhq.com/example": ("ashby", "example"),
        "https://apply.workable.com/example": ("workable", "example"),
        "https://example.recruitee.com": ("recruitee", "example"),
        "https://example.teamtailor.com": ("teamtailor", "example"),
        "https://example.bamboohr.com/careers": ("bamboohr", "example"),
        "https://example.applytojob.com/apply": ("jazzhr", "example"),
        "https://example.jobs.personio.de": ("personio", "example"),
        "https://ats.rippling.com/api/v1/companies/example/jobs": ("rippling", "example"),
    }
    for url, expected in samples.items():
        assert detect_ats_from_url(url) == expected

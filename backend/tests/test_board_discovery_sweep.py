from app.services.careers_page_ingest import _WORKDAY_URL_RE
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

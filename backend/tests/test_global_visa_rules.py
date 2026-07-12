from app.services.global_visa_rules import (
    TARGET_COUNTRIES,
    classify_global_visa,
    country_options,
    in_target_country,
    normalize_country_code,
)
from app.etl.jobs_scraper_6h import (
    JOBSPY_RECENCY_HOURS,
    PUBLIC_MAX_BATCHES_PER_RUN,
    _base_args,
    _selected_target_countries,
    _target_locations,
)
from app.models.job import JobSource
from app.services.job_scraper import _jobspy_indeed_country, _source_supports_location


def test_india_is_target_country_with_city_aliases():
    assert "IN" in TARGET_COUNTRIES
    assert normalize_country_code("IN") == "IN"
    assert in_target_country("Bengaluru, India") == (True, "IN")
    assert in_target_country("Hyderabad") == (True, "IN")


def test_france_and_italy_remain_target_countries():
    assert normalize_country_code("FR") == "FR"
    assert normalize_country_code("IT") == "IT"
    assert in_target_country("Paris, France") == (True, "FR")
    assert in_target_country("Milan, Italy") == (True, "IT")


def test_india_country_and_visa_options_are_exposed():
    countries = {item["code"]: item["name"] for item in country_options()}
    assert countries["IN"] == "India"

    result = classify_global_visa(
        title="Software Engineer",
        company="Acme",
        location="Pune, India",
        description="We offer relocation support and employment visa assistance for qualified candidates.",
    )
    assert result["country_code"] == "IN"
    assert "employment_visa" in result["visa_programs"]


def test_scraper_targets_all_countries_with_a_bounded_rotating_role_slice():
    locations = _target_locations().split("~")
    expected_countries = {
        "AE", "AT", "AU", "BE", "CA", "CH", "CZ", "DE", "DK", "EE", "ES",
        "FI", "FR", "GB", "HK", "IE", "IN", "IT", "JP", "KR", "LU", "NL",
        "NO", "NZ", "PL", "PT", "QA", "SA", "SE", "SG", "TW", "US",
    }

    assert set(TARGET_COUNTRIES) == expected_countries
    assert len(locations) == len(TARGET_COUNTRIES)
    assert 1 <= PUBLIC_MAX_BATCHES_PER_RUN <= 16
    assert JOBSPY_RECENCY_HOURS == 24
    assert _base_args().jobspy_hours_old == 24


def test_country_scraper_can_isolate_one_country(monkeypatch):
    monkeypatch.setenv("SCRAPER_TARGET_COUNTRIES", "DE")

    assert _selected_target_countries() == ["DE"]
    assert _target_locations() == "Germany"


def test_jobspy_uses_the_requested_international_indeed_market():
    assert _jobspy_indeed_country("Germany") == "Germany"
    assert _jobspy_indeed_country("United Kingdom") == "UK"
    assert _jobspy_indeed_country("India") == "India"


def test_usa_only_sources_are_not_called_for_other_countries():
    assert _source_supports_location(JobSource.USAJOBS, "United States")
    assert not _source_supports_location(JobSource.USAJOBS, "Germany")
    assert not _source_supports_location(JobSource.DICE, "India")
    assert not _source_supports_location(JobSource.ZIPRECRUITER, "France")
    assert _source_supports_location(JobSource.ZIPRECRUITER, "Canada")

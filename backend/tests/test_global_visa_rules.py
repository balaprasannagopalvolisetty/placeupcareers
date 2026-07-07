from app.services.global_visa_rules import (
    TARGET_COUNTRIES,
    classify_global_visa,
    country_options,
    in_target_country,
    normalize_country_code,
)
from app.etl.jobs_scraper_6h import PUBLIC_MAX_BATCHES_PER_RUN, _target_locations


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


def test_scraper_targets_all_configured_countries_by_default():
    locations = _target_locations().split("~")

    assert len(TARGET_COUNTRIES) >= 30
    assert len(locations) == len(TARGET_COUNTRIES)
    assert PUBLIC_MAX_BATCHES_PER_RUN == 0

"""
Tests for official-portal connectors + the English-only language filter (B4).

JobTech field shapes are taken from a live API sample. No network is used.
    pytest backend/tests/test_official_portals.py -q
"""
import asyncio

from app.etl.sources import official_portals as op
from app.etl.sources.source_base import is_probably_english
from app.etl.sources.global_sources import run_all_clean_sources

# Trimmed real-shape JobTech hits (one English, one Swedish).
_HIT_EN = {
    "id": "1001",
    "headline": "Senior Backend Engineer",
    "webpage_url": "https://arbetsformedlingen.se/platsbanken/annonser/1001",
    "publication_date": "2026-06-02T08:00:00",
    "application_deadline": "2026-06-30T23:59:59",
    "number_of_vacancies": 2,
    "description": {"text": "We are looking for a backend engineer to join our team. "
                            "You will work with Python and cloud infrastructure."},
    "employer": {"name": "Globex AB", "workplace": "Globex"},
    "workplace_address": {"municipality": "Stockholm", "city": "Stockholm",
                          "country": "Sverige", "country_code": "199"},
    "occupation_field": {"label": "Data/IT"},
}
_HIT_SV = {
    "id": "1002",
    "headline": "Systemutvecklare till vårt team",
    "webpage_url": "https://arbetsformedlingen.se/platsbanken/annonser/1002",
    "publication_date": "2026-06-02T09:00:00",
    "description": {"text": "Vi söker en erfaren systemutvecklare som vill arbeta "
                            "med vidareutveckling och förvaltning av våra tjänster."},
    "employer": {"name": "Thalamus IT"},
    "workplace_address": {"city": "Göteborg", "country": "Sverige"},
}


def test_is_probably_english():
    assert is_probably_english("We are looking for an engineer to join our team with experience") is True
    assert is_probably_english("Vi söker en erfaren systemutvecklare som vill arbeta med våra") is False
    assert is_probably_english("") is False


def test_jobtech_parser_tags_country_and_language():
    en = op.jobtech_hit_to_jobpost(_HIT_EN)
    assert en is not None
    assert en.company == "Globex AB"
    assert en.location == "Stockholm, Sweden"
    assert en.source.value == "jobtech"
    assert en.extra_metadata["visa_country"] == "SE"        # hard-tagged Sweden
    assert en.extra_metadata["english_friendly"] is True
    assert en.content_hash and en.posted_at is not None

    sv = op.jobtech_hit_to_jobpost(_HIT_SV)
    assert sv.extra_metadata["visa_country"] == "SE"
    assert sv.extra_metadata["english_friendly"] is False   # Swedish posting flagged


def test_jobtech_parser_rejects_incomplete():
    assert op.jobtech_hit_to_jobpost({"headline": "", "employer": {}}) is None
    assert op.jobtech_hit_to_jobpost("not a dict") is None


def test_english_only_filter_drops_local_language(monkeypatch):
    """run_all_clean_sources(english_only=True) keeps EN, drops SV."""
    en = op.jobtech_hit_to_jobpost(_HIT_EN)
    sv = op.jobtech_hit_to_jobpost(_HIT_SV)

    async def fake_jobtech(**kwargs):
        return [en, sv]

    import app.etl.sources.global_sources as gs
    monkeypatch.setattr(gs, "ALL_CLEAN_SOURCES", {"jobtech": fake_jobtech})

    kept_all, _ = asyncio.run(run_all_clean_sources(hours=0, english_only=False))
    kept_en, _ = asyncio.run(run_all_clean_sources(hours=0, english_only=True))
    assert len(kept_all) == 2
    assert len(kept_en) == 1
    assert kept_en[0].extra_metadata["english_friendly"] is True

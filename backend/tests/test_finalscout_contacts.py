import csv
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from app.models.contact import Contact, ContactConfidence, ContactSource
from app.services import contact_csv_importer, finalscout_enrichment


def test_sample_user_csv_normalizes_linkedin_and_ignores_export_garbage_last_name():
    sample_path = Path(__file__).resolve().parents[1] / "sample user.csv"
    with sample_path.open("r", encoding="utf-8-sig", newline="") as f:
        first_row = next(csv.DictReader(f))

    contact = contact_csv_importer._row_to_contact(first_row)

    assert contact["first_name"] == "Jordan"
    assert contact["last_name"] is None
    assert contact["full_name"] == "Jordan"
    assert contact["linkedin_url"] == "https://www.linkedin.com/in/jmesches"
    assert contact["email"] is None


def test_finalscout_result_parser_accepts_nested_email_shapes():
    parsed = finalscout_enrichment._result_to_contact({
        "person": {
            "full_name": "Jordan Mesches",
            "headline": "Engineering Manager",
            "current_company": {"name": "FileScience"},
            "profile_url": "linkedin.com/in/jmesches?trk=abc",
            "emails": [{"value": "Jordan@Example.com", "status": "valid", "score": 95}],
        }
    })

    assert parsed.email == "jordan@example.com"
    assert parsed.company == "FileScience"
    assert parsed.linkedin_url == "https://www.linkedin.com/in/jmesches"
    assert parsed.confidence == ContactConfidence.VERIFIED


class FakeDb:
    def __init__(self):
        self.rows = [{
            "id": "csv-1",
            "full_name": "Jordan",
            "first_name": "Jordan",
            "last_name": None,
            "title": "Engineering Manager",
            "role": "engineering_manager",
            "company": "FileScience",
            "email": None,
            "linkedin_url": "https://www.linkedin.com/in/jmesches",
            "source": "csv_import",
            "confidence": "verified",
            "source_payload": {},
        }]
        self.upserts = []

    async def get_contacts(self, **kwargs):
        return self.rows

    async def upsert_contacts(self, contacts):
        self.upserts.extend(contacts)
        return len(contacts)


@pytest.mark.asyncio
async def test_enrich_missing_emails_updates_original_csv_contact(monkeypatch):
    async def fake_find_by_linkedin(*args, **kwargs):
        return Contact(
            id="finalscout-generated-id",
            full_name="Jordan Mesches",
            first_name="Jordan",
            last_name="Mesches",
            title="Engineering Manager",
            role="engineering_manager",
            company="FileScience",
            email="jordan@example.com",
            linkedin_url="https://www.linkedin.com/in/jmesches",
            source=ContactSource.FINALSCOUT,
            confidence=ContactConfidence.VERIFIED,
            source_payload={"email_status": "valid"},
        )

    monkeypatch.setattr(finalscout_enrichment, "find_by_linkedin", fake_find_by_linkedin)
    db = FakeDb()

    result = await contact_csv_importer.enrich_missing_emails(
        db,
        limit=1,
        byok_finalscout_key="test-key",
    )

    assert result["enriched"] == 1
    assert result["finalscout_found"] == 1
    assert db.upserts[0]["id"] == "csv-1"
    assert db.upserts[0]["email"] == "jordan@example.com"
    assert db.upserts[0]["source"] == "finalscout"
    assert db.upserts[0]["source_payload"]["enrichment"]["source"] == "finalscout"

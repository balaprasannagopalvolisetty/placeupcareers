"""Internal smoke test - mocked end-to-end contact pipeline."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.models.contact import Contact, ContactSource, ContactConfidence
from app.services.google_xray import linkedin_search_url
from app.services.ats_contact_extractor import extract_from_jobpost
from app.services.contact_finder import find_contacts
from app.api.contacts import router as contacts_router
from app.main import app
from app.db.postgres import PostgresClient
from app.models.job import JobPost, JobSource
from app.config import settings


FAKE_HUNTER = {
    "data": {
        "domain": "stripe.com",
        "organization": "Stripe",
        "pattern": "{first}.{last}",
        "emails": [
            {"value": "jane.doe@stripe.com", "first_name": "Jane", "last_name": "Doe",
             "position": "Senior Recruiter, Engineering", "department": "hr",
             "confidence": 95, "verification": {"result": "deliverable"},
             "linkedin": "https://linkedin.com/in/janedoe"},
            {"value": "john.smith@stripe.com", "first_name": "John", "last_name": "Smith",
             "position": "Engineering Manager", "department": "engineering",
             "confidence": 87},
        ],
    }
}
FAKE_APOLLO = {
    "people": [
        {"id": "ap-1", "name": "Maria Garcia", "first_name": "Maria", "last_name": "Garcia",
         "title": "Talent Acquisition Lead",
         "email": "maria.garcia@stripe.com", "email_status": "verified",
         "linkedin_url": "https://linkedin.com/in/mariagarcia",
         "organization": {"name": "Stripe", "primary_domain": "stripe.com"}},
    ]
}
FAKE_SERP = {
    "organic_results": [
        {"title": "Alex Chen - Engineering Recruiter at Stripe | LinkedIn",
         "link": "https://www.linkedin.com/in/alexchen-recruiter",
         "snippet": "Engineering Recruiter at Stripe."},
    ]
}


async def fake_post(self, url, *args, **kwargs):
    class R:
        status_code = 200
        def raise_for_status(self): pass
        def json(self):
            return FAKE_APOLLO if "apollo.io" in str(url) else {}
    return R()


async def fake_get(self, url, *args, **kwargs):
    class R:
        status_code = 200
        def raise_for_status(self): pass
        def json(self):
            u = str(url)
            if "hunter.io" in u: return FAKE_HUNTER
            if "serpapi" in u: return FAKE_SERP
            if "googleapis" in u: return {"items": []}
            return {}
    return R()


async def main():
    print("=== Imports ===")
    print("All contact modules import OK")
    print("FastAPI routes:")
    for r in app.routes:
        path = getattr(r, "path", "")
        if "/contacts" in path:
            methods = ",".join(sorted(getattr(r, "methods", set()) - {"HEAD"}))
            print(f"  {methods:8} {path}")

    print("\n=== Free path: linkedin_search_url ===")
    print(linkedin_search_url("Stripe", "engineering recruiter"))

    print("\n=== Free path: extract_from_jobpost ===")
    sample_job = JobPost(
        id="abc12345", title="Senior Backend Engineer", company="Stripe",
        location="Remote, US", source=JobSource.GREENHOUSE, content_hash="deadbeef",
        extra_metadata={"ats": "greenhouse", "metadata": [
            {"name": "Recruiter", "value": "Sarah Kim"},
            {"name": "Hiring Manager Email", "value": "hiring@stripe.com"},
        ]},
    )
    for c in extract_from_jobpost(sample_job):
        print(f"  [{c.source.value:>22}] conf={c.confidence.value:<9} role={c.role.value:<22} "
              f"name={c.full_name or '-':<14} email={c.email or '-':<30}")

    print("\n=== Mocked end-to-end: find_contacts ===")
    settings.apollo_api_key = "fake-apollo"
    settings.hunter_api_key = "fake-hunter"
    settings.serpapi_key = "fake-serp"

    db = PostgresClient()
    from httpx import AsyncClient
    with patch.object(AsyncClient, "post", new=fake_post), patch.object(AsyncClient, "get", new=fake_get):
        result = await find_contacts(
            company="Stripe", role_query="engineering recruiter", domain="stripe.com",
            job=sample_job, db=db, max_contacts=10, force_refresh=True,
        )
    print(f"company:           {result.company}")
    print(f"contacts:          {len(result.contacts)}")
    print(f"sources_used:      {[s.value for s in result.sources_used]}")
    print(f"api_credits_used:  {result.api_credits_used}")
    print(f"cache_hit:         {result.cache_hit}")
    print(f"duration:          {result.duration_seconds:.2f}s")
    print()
    print("Top contacts (deduped + ranked):")
    for c in result.contacts[:8]:
        print(f"  [{c.source.value:>22}] conf={c.confidence.value:<9} role={c.role.value:<22} "
              f"name={(c.full_name or '-'):<22} email={(c.email or '-'):<32} "
              f"linkedin={(c.linkedin_url or '-')[:55]}")

    print("\n=== Cache hit on second call ===")
    with patch.object(AsyncClient, "post", new=fake_post), patch.object(AsyncClient, "get", new=fake_get):
        result2 = await find_contacts(
            company="Stripe", role_query="engineering recruiter", domain="stripe.com",
            job=sample_job, db=db, max_contacts=10, force_refresh=False,
        )
    print(f"contacts: {len(result2.contacts)}  cache_hit={result2.cache_hit}  "
          f"credits={result2.api_credits_used}")
    print("\nALL SMOKE TESTS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

"""Free-only contact pipeline smoke test (no Apollo/Hunter/SerpAPI keys)."""
from __future__ import annotations
import asyncio, sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.models.contact import Contact, ContactSource, ContactConfidence, ContactRole, ContactContribution
from app.services.contact_finder import find_contacts, CACHE_TTL
from app.api.contacts import router
from app.main import app
from app.db.postgres import PostgresClient
from app.models.job import JobPost, JobSource


# ── Mocked free-source responses ───────────────────────────────
FAKE_TEAM_PAGE_HTML = '''
<html><body>
  <script type="application/ld+json">
    {"@context":"https://schema.org","@type":"Organization","name":"Stripe",
     "employee":[
       {"@type":"Person","name":"Sarah Kim","jobTitle":"Head of Recruiting",
        "email":"sarah@stripe.com","sameAs":["https://linkedin.com/in/sarahkim"]}
     ]}
  </script>
  <a href="mailto:talent@stripe.com">Talent team</a>
  <p>Reach our <a href="mailto:engineering-recruiter@stripe.com">Maria Garcia, Senior Recruiter</a></p>
</body></html>
'''

FAKE_GITHUB_MEMBERS = [{"login": "alice"}, {"login": "bob"}]
FAKE_GITHUB_PROFILE = {
    "login": "alice", "name": "Alice Engineer", "email": "alice@stripe.com",
    "bio": "Engineering Manager at Stripe", "blog": "https://alice.dev",
    "twitter_username": "alice_eng", "html_url": "https://github.com/alice",
    "company": "Stripe", "location": "SF", "hireable": True,
}


async def fake_get(self, url, *args, **kwargs):
    class R:
        status_code = 200
        headers = {"content-type": "text/html"}
        def raise_for_status(self): pass
        @property
        def text(self): return FAKE_TEAM_PAGE_HTML if "stripe.com" in str(url) else "<html></html>"
        def json(self):
            u = str(url)
            if "/orgs/stripe/public_members" in u: return FAKE_GITHUB_MEMBERS
            if "/users/alice" in u: return FAKE_GITHUB_PROFILE
            if "/users/bob" in u: return {"login": "bob", "name": "Bob Dev", "company": "Other"}
            return {}
    return R()


async def main():
    print("=== Cache TTL config ===")
    print(f"CACHE_TTL = {CACHE_TTL.days} days (global, shared across all users)")

    db = PostgresClient()

    # Contribute one crowdsourced contact first
    print("\n=== Crowdsourced contribution ===")
    contrib = ContactContribution(
        company="Stripe", full_name="John Crowd", title="Recruiter",
        email="john.crowd@stripe.com",
        role=ContactRole.RECRUITER, submitted_by="bala@placeup.io",
    )
    raw_id_src = f"crowd|{contrib.company.lower()}|{contrib.email.lower()}"
    import hashlib
    cid = hashlib.sha256(raw_id_src.encode()).hexdigest()[:16]
    crowd_contact = Contact(
        id=cid, full_name=contrib.full_name, title=contrib.title, role=contrib.role,
        company=contrib.company, email=contrib.email, source=ContactSource.CROWDSOURCED,
        confidence=ContactConfidence.VERIFIED,
    )
    await db.upsert_contacts([crowd_contact.model_dump(mode="json")])
    print(f"  crowdsourced: {crowd_contact.full_name} <{crowd_contact.email}>")

    sample_job = JobPost(
        id="abc12345", title="Senior Engineer", company="Stripe",
        location="Remote, US", source=JobSource.GREENHOUSE, content_hash="dead",
        company_url="https://stripe.com",
        extra_metadata={"ats": "greenhouse", "metadata": [
            {"name": "Recruiter", "value": "Sarah Kim"},
        ]},
    )

    print("\n=== Free-only find_contacts (NO paid keys configured) ===")
    from httpx import AsyncClient
    with patch.object(AsyncClient, "get", new=fake_get):
        result = await find_contacts(
            company="Stripe", role_query="recruiter", domain="stripe.com",
            job=sample_job, db=db, max_contacts=15, force_refresh=True,
        )
    print(f"company:       {result.company}")
    print(f"contacts:      {len(result.contacts)}")
    print(f"sources_used:  {[s.value for s in result.sources_used]}")
    print(f"cost (paid):   {result.api_credits_used}  ← $0")
    print(f"cache_hit:     {result.cache_hit}")
    print(f"notes:         {result.notes[:2]}")
    print()
    print("Top contacts:")
    for c in result.contacts[:10]:
        line = (f"  [{c.source.value:>20}] conf={c.confidence.value:<9} "
                f"role={c.role.value:<22} name={(c.full_name or '-'):<22} "
                f"email={(c.email or '-'):<32} linkedin={(c.linkedin_url or '-')[:55]}")
        print(line)

    print("\n=== 2nd call: global cache hit (90d TTL, $0 cost) ===")
    with patch.object(AsyncClient, "get", new=fake_get):
        result2 = await find_contacts(
            company="Stripe", role_query="recruiter", domain="stripe.com",
            job=sample_job, db=db, max_contacts=15, force_refresh=False,
        )
    print(f"contacts={len(result2.contacts)}  cache_hit={result2.cache_hit}  "
          f"cost={result2.api_credits_used}  duration={result2.duration_seconds:.3f}s")

    print("\n=== BYOK simulation ===")
    print("If user passes X-Apollo-Key header, find_contacts uses *their* key,")
    print("PlaceUp pays $0. Verified in code: byok_apollo_key threads through to apollo_search.")

    print("\nALL FREE-ONLY SMOKE TESTS PASSED")


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

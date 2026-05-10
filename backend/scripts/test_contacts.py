"""
PlaceUp - Contact Extractor CLI Tester

Run any of the contact-discovery sources against a real company so you can
see what they actually return. Designed for manual smoke-testing on your
own machine where you have internet access.

Usage examples:
    # 1. Test team-page crawler on a real company website
    python scripts/test_contacts.py team-page Stripe https://stripe.com

    # 2. Test GitHub miner (pulls public org members + profiles)
    python scripts/test_contacts.py github Stripe

    # 3. Test ATS metadata extractor on a real Greenhouse board
    python scripts/test_contacts.py ats Stripe stripe       # last arg = greenhouse token

    # 4. Test the FULL pipeline (cache + all free sources)
    python scripts/test_contacts.py all Stripe https://stripe.com

    # 5. With BYOK (your own Apollo/Hunter free-tier keys)
    python scripts/test_contacts.py all Stripe https://stripe.com \\
        --apollo-key=YOUR_APOLLO_FREE_TIER_KEY \\
        --hunter-key=YOUR_HUNTER_FREE_TIER_KEY

    # 6. Test the LinkedIn search-URL fallback (always free, no API needed)
    python scripts/test_contacts.py linkedin "Stripe" "engineering recruiter"

What you'll see for each contact:
    [source] confidence  role           name              email                linkedin
"""
from __future__ import annotations

import argparse
import asyncio
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Use a temp DB so we don't pollute your real placeup.db
import app.db.local_db as _ldb
_TMP = Path(tempfile.gettempdir()) / "placeup_test_contacts.db"
if _TMP.exists():
    _TMP.unlink()
_ldb.DB_PATH = _TMP

from app.db.local_db import SQLiteClient
from app.models.job import JobPost, JobSource
from app.services.team_page_crawler import crawl_company_team_pages
from app.services.github_miner import mine_company_github
from app.services.ats_contact_extractor import extract_from_jobpost
from app.services.contact_finder import find_contacts
from app.services.google_xray import linkedin_search_url
from app.services.careers_ats import scrape_greenhouse_board, scrape_lever_board


def _print_contacts(contacts, label="Contacts"):
    print(f"\n>>> {label} ({len(contacts)} found):")
    if not contacts:
        print("   (no contacts found by this source)")
        return
    for i, c in enumerate(contacts, 1):
        src = c.source.value if hasattr(c.source, "value") else str(c.source)
        conf = c.confidence.value if hasattr(c.confidence, "value") else str(c.confidence)
        role = c.role.value if hasattr(c.role, "value") else str(c.role)
        name = c.full_name or "-"
        email = c.email or "-"
        linkedin = c.linkedin_url or c.linkedin_search_url or "-"
        print(f"  {i:2}. [{src:<20}] conf={conf:<9} role={role:<22}")
        print(f"      name:     {name}")
        print(f"      email:    {email}")
        print(f"      linkedin: {linkedin[:80]}")
        if c.title:
            print(f"      title:    {c.title[:80]}")


async def cmd_team_page(args):
    print(f"\n=== Team-page crawler: {args.company} ({args.base_url}) ===")
    contacts = await crawl_company_team_pages(
        company=args.company,
        base_url=args.base_url,
        max_contacts=args.max_contacts,
    )
    _print_contacts(contacts, "Team-page extractor")


async def cmd_github(args):
    print(f"\n=== GitHub miner: {args.company} ===")
    print("(Set GITHUB_TOKEN env var for 5K req/hr instead of 60/hr unauthenticated)")
    contacts = await mine_company_github(
        company=args.company,
        max_members=args.max_contacts,
    )
    _print_contacts(contacts, "GitHub org members")


async def cmd_ats(args):
    """Test ATS metadata extraction by pulling a few real Greenhouse jobs and parsing them."""
    print(f"\n=== ATS metadata extractor: {args.company} (greenhouse: {args.token}) ===")
    print("Step 1: fetching first few Greenhouse jobs for this company...")
    jobs = await scrape_greenhouse_board(args.token, max_jobs=5)
    print(f"   pulled {len(jobs)} jobs from Greenhouse")
    if not jobs:
        print("   (board returned no jobs; check the token)")
        return
    all_contacts = []
    for job in jobs:
        cs = extract_from_jobpost(job)
        for c in cs:
            all_contacts.append(c)
    _print_contacts(all_contacts, "ATS-extracted contacts")


async def cmd_linkedin(args):
    print(f"\n=== LinkedIn search-URL generator (zero API cost) ===")
    url = linkedin_search_url(args.company, args.role_query)
    print(f"  Click this URL to search LinkedIn as yourself:")
    print(f"  {url}")


async def cmd_all(args):
    """Run the FULL find_contacts() pipeline."""
    print(f"\n=== Full pipeline: {args.company} ===")
    print("Sources that will run:")
    print(f"  Free:  ats_metadata, dol_lca, team_page, github, crowdsourced, linkedin_url")
    print(f"  Paid:  apollo={bool(args.apollo_key)}, hunter={bool(args.hunter_key)}, "
          f"serpapi={bool(args.serpapi_key)}  (BYOK)")

    db = SQLiteClient()

    # Build a fake JobPost so ats_metadata and team_page have a base_url
    fake_job = JobPost(
        id="test123",
        title=args.role_query or "Software Engineer",
        company=args.company,
        location="USA",
        source=JobSource.GREENHOUSE,
        content_hash="test",
        company_url=args.base_url or f"https://{args.company.lower().replace(' ', '')}.com",
    )

    result = await find_contacts(
        company=args.company,
        role_query=args.role_query,
        domain=args.domain,
        job=fake_job,
        db=db,
        # Free toggles (all on)
        use_ats_metadata=True,
        use_dol_lca=True,
        use_team_page=True,
        use_github=True,
        use_crowdsourced=True,
        # Paid toggles
        use_apollo=bool(args.apollo_key),
        use_hunter=bool(args.hunter_key),
        use_google_xray=bool(args.serpapi_key),
        # BYOK keys
        byok_apollo_key=args.apollo_key,
        byok_hunter_key=args.hunter_key,
        byok_serpapi_key=args.serpapi_key,
        max_contacts=args.max_contacts,
        force_refresh=True,
    )

    print()
    print(f"  cache_hit:        {result.cache_hit}")
    print(f"  sources used:     {[s.value for s in result.sources_used]}")
    print(f"  paid credits:     {result.api_credits_used}  (BYOK = $0 to PlaceUp)")
    print(f"  duration:         {result.duration_seconds:.2f}s")
    print(f"  notes:            {result.notes}")
    _print_contacts(result.contacts, "Final ranked contacts")


def parse_args():
    p = argparse.ArgumentParser(description="PlaceUp contact-extractor CLI tester")
    sub = p.add_subparsers(dest="cmd", required=True)

    p_team = sub.add_parser("team-page", help="Test the team-page crawler")
    p_team.add_argument("company")
    p_team.add_argument("base_url")
    p_team.add_argument("--max-contacts", type=int, default=20)

    p_gh = sub.add_parser("github", help="Test the GitHub miner")
    p_gh.add_argument("company")
    p_gh.add_argument("--max-contacts", type=int, default=15)

    p_ats = sub.add_parser("ats", help="Test ATS metadata extractor on a real Greenhouse board")
    p_ats.add_argument("company")
    p_ats.add_argument("token", help="Greenhouse board token (e.g. 'stripe')")
    p_ats.add_argument("--max-contacts", type=int, default=10)

    p_li = sub.add_parser("linkedin", help="Generate a LinkedIn search URL")
    p_li.add_argument("company")
    p_li.add_argument("role_query", default="recruiter", nargs="?")

    p_all = sub.add_parser("all", help="Run the full free-first pipeline")
    p_all.add_argument("company")
    p_all.add_argument("base_url", nargs="?", default=None)
    p_all.add_argument("--role-query", default="recruiter")
    p_all.add_argument("--domain", default=None,
                       help="Optional company email domain (boosts Hunter)")
    p_all.add_argument("--max-contacts", type=int, default=15)
    p_all.add_argument("--apollo-key", default=None,
                       help="Your Apollo BYOK key (free tier 60/mo)")
    p_all.add_argument("--hunter-key", default=None,
                       help="Your Hunter BYOK key (free tier 25/mo)")
    p_all.add_argument("--serpapi-key", default=None,
                       help="Your SerpAPI BYOK key")
    return p.parse_args()


def main():
    args = parse_args()
    handler = {
        "team-page": cmd_team_page,
        "github":    cmd_github,
        "ats":       cmd_ats,
        "linkedin":  cmd_linkedin,
        "all":       cmd_all,
    }[args.cmd]
    asyncio.run(handler(args))


if __name__ == "__main__":
    main()

"""
PlaceUp - Contact Coverage Diagnostic

Runs the FULL find_contacts() pipeline against a list of companies and
reports per-company coverage stats so you can see exactly what the system
is finding (and what it isn't) in real numbers.

Output: stdout table + data/exports/coverage_report_<timestamp>.csv

Usage:
    # Default: top 50 H1B sponsors from the curated catalog
    python scripts/contact_coverage_report.py

    # Specific companies
    python scripts/contact_coverage_report.py --companies "Stripe,Airbnb,Coinbase"

    # Use Hunter (BYOK from .env or --hunter-key flag)
    python scripts/contact_coverage_report.py --use-hunter

    # Use everything (Hunter + Apollo + Google X-ray) for max coverage
    python scripts/contact_coverage_report.py --use-hunter --use-apollo --use-google-xray

    # Limit to top 10 sponsors (saves time + API credits)
    python scripts/contact_coverage_report.py --top-n 10

    # Limit max contacts per company (reduces API spend)
    python scripts/contact_coverage_report.py --max-contacts 5
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import logging
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.db.local_db import SQLiteClient
from app.services.contact_finder import find_contacts
from app.services.h1b_sponsor_boards import H1B_SPONSOR_BOARDS

logging.basicConfig(
    level=logging.WARNING,  # quiet by default; output is the table
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("placeup.coverage")
logger.setLevel(logging.INFO)


def parse_args():
    p = argparse.ArgumentParser(description="PlaceUp contact coverage diagnostic")
    p.add_argument("--companies", default=None,
                   help="Comma-separated company names; default = top H1B sponsors")
    p.add_argument("--top-n", type=int, default=20,
                   help="When using default catalog, how many top companies to test")
    p.add_argument("--max-contacts", type=int, default=10,
                   help="Per-company contact cap (caps Apollo/Hunter spend)")
    p.add_argument("--use-hunter", action="store_true",
                   help="Enable Hunter.io domain-search (uses platform key)")
    p.add_argument("--use-apollo", action="store_true",
                   help="Enable Apollo people-search (uses platform key)")
    p.add_argument("--use-google-xray", action="store_true",
                   help="Enable Google X-ray via SerpAPI (uses platform key)")
    p.add_argument("--hunter-key", default=None, help="Override HUNTER_API_KEY")
    p.add_argument("--apollo-key", default=None, help="Override APOLLO_API_KEY")
    p.add_argument("--serpapi-key", default=None, help="Override SERPAPI_KEY")
    p.add_argument("--concurrency", type=int, default=4,
                   help="Parallel companies (be kind to free APIs)")
    p.add_argument("--output-dir", default="data/exports",
                   help="Where to write the CSV report")
    return p.parse_args()


def _resolve_companies(args) -> list[dict]:
    """Return [{company, domain, ats}] tuples to test."""
    if args.companies:
        names = [n.strip() for n in args.companies.split(",") if n.strip()]
        # Try to match against the catalog for domain hints
        catalog = {entry["company"].lower(): entry for entry in H1B_SPONSOR_BOARDS}
        out = []
        for n in names:
            entry = catalog.get(n.lower())
            out.append({
                "company": n,
                "domain": (entry or {}).get("domain"),
                "ats": (entry or {}).get("ats"),
            })
        return out

    # Default: top N from catalog
    return [
        {"company": e["company"], "domain": None, "ats": e.get("ats")}
        for e in H1B_SPONSOR_BOARDS[: args.top_n]
    ]


def _domain_for_company(company: str, hint: str | None) -> str | None:
    """Best-guess domain from company name when not explicit in catalog."""
    if hint:
        return hint
    # Heuristic — works for common companies. Real implementation should use Clearbit autocomplete.
    slug = company.lower().replace(" ", "").replace(",", "").replace("(", "").replace(")", "")
    slug = slug.replace("inc.", "").replace("inc", "").replace(".", "").strip()
    return f"{slug}.com" if slug else None


async def _enrich_one(company_info: dict, args, db) -> dict:
    company = company_info["company"]
    domain = _domain_for_company(company, company_info.get("domain"))
    started = datetime.utcnow()
    try:
        result = await find_contacts(
            company=company, domain=domain, db=db,
            max_contacts=args.max_contacts,
            use_apollo=args.use_apollo, use_hunter=args.use_hunter,
            use_google_xray=args.use_google_xray,
            byok_apollo_key=args.apollo_key, byok_hunter_key=args.hunter_key,
            byok_serpapi_key=args.serpapi_key,
            force_refresh=True,
        )
    except Exception as exc:
        return {
            "company": company, "domain": domain, "error": str(exc),
            "total_contacts": 0, "with_email": 0, "with_linkedin_url": 0,
            "verified_emails": 0, "sources_used": "", "credits_used": "",
            "duration_s": 0,
        }

    with_email = sum(1 for c in result.contacts if c.email)
    with_linkedin = sum(1 for c in result.contacts if c.linkedin_url)
    verified = sum(1 for c in result.contacts if c.email and getattr(c.confidence, "value", str(c.confidence)) == "verified")
    duration = (datetime.utcnow() - started).total_seconds()
    return {
        "company": company,
        "domain": domain or "",
        "total_contacts": len(result.contacts),
        "with_email": with_email,
        "verified_emails": verified,
        "with_linkedin_url": with_linkedin,
        "sources_used": ", ".join(s.value for s in result.sources_used),
        "credits_used": ", ".join(f"{k}={v}" for k, v in result.api_credits_used.items()) or "$0",
        "duration_s": round(duration, 2),
        "cache_hit": result.cache_hit,
        "error": "",
    }


async def main() -> int:
    args = parse_args()
    db = SQLiteClient()

    companies = _resolve_companies(args)
    print(f"\nRunning coverage diagnostic on {len(companies)} companies…")
    print(f"  use_hunter={args.use_hunter}  use_apollo={args.use_apollo}  "
          f"use_google_xray={args.use_google_xray}  max_contacts={args.max_contacts}")
    print()

    semaphore = asyncio.Semaphore(args.concurrency)

    async def _with_sema(c):
        async with semaphore:
            row = await _enrich_one(c, args, db)
            print(f"  {row['company']:<32} -> {row['total_contacts']:>3} contacts  "
                  f"emails={row['with_email']:>2}  verified={row['verified_emails']:>2}  "
                  f"linkedin={row['with_linkedin_url']:>2}  "
                  f"({row['duration_s']:>5.1f}s)  {row['credits_used']}")
            return row

    results = await asyncio.gather(*[_with_sema(c) for c in companies])

    # Aggregate
    totals = {
        "companies": len(results),
        "total_contacts": sum(r["total_contacts"] for r in results),
        "with_email": sum(r["with_email"] for r in results),
        "verified_emails": sum(r["verified_emails"] for r in results),
        "with_linkedin": sum(r["with_linkedin_url"] for r in results),
        "errors": sum(1 for r in results if r.get("error")),
    }

    # Write CSV
    out_dir = ROOT / args.output_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    csv_path = out_dir / f"coverage_report_{ts}.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=[
            "company", "domain", "total_contacts", "with_email", "verified_emails",
            "with_linkedin_url", "sources_used", "credits_used", "duration_s",
            "cache_hit", "error",
        ])
        w.writeheader()
        w.writerows(results)

    # Summary
    print()
    print("=" * 70)
    print("COVERAGE SUMMARY")
    print("=" * 70)
    print(f"  Companies tested:       {totals['companies']}")
    print(f"  Total contacts found:   {totals['total_contacts']}")
    print(f"    With any email:       {totals['with_email']}  "
          f"({100 * totals['with_email'] / max(totals['total_contacts'], 1):.0f}%)")
    print(f"    Verified emails:      {totals['verified_emails']}")
    print(f"    With LinkedIn URL:    {totals['with_linkedin']}")
    print(f"  Errors:                 {totals['errors']}")
    print(f"  Per-company average:    {totals['total_contacts'] / max(totals['companies'], 1):.1f} contacts, "
          f"{totals['with_email'] / max(totals['companies'], 1):.1f} emails")
    print()
    print(f"Full CSV report: {csv_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

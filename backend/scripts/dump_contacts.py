"""
PlaceUp - Dump All Contacts From SQLite to CSV

Flat CSV of every contact currently cached in your local placeup.db.
Use this after any enrichment run to see the actual emails / LinkedIn
URLs that have been collected.

Usage:
  python scripts/dump_contacts.py
  python scripts/dump_contacts.py --company "Stripe"           # filter
  python scripts/dump_contacts.py --emails-only                 # skip rows without emails
  python scripts/dump_contacts.py --output data/exports/my.csv  # custom path
  python scripts/dump_contacts.py --print 20                    # also print first 20 to stdout
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.db.local_db import SQLiteClient


def parse_args():
    p = argparse.ArgumentParser(description="Dump cached contacts to CSV")
    p.add_argument("--company", default=None,
                   help="Filter to one company name (case-insensitive)")
    p.add_argument("--source", default=None,
                   help="Filter by source: hunter, apollo, github, dol_lca, team_page, crowdsourced, ats_metadata, linkedin_search_url")
    p.add_argument("--emails-only", action="store_true",
                   help="Skip rows that don't have an email")
    p.add_argument("--linkedin-only", action="store_true",
                   help="Skip rows that don't have a LinkedIn URL")
    p.add_argument("--limit", type=int, default=10000)
    p.add_argument("--output", default=None,
                   help="Output CSV path (default: data/exports/contacts_<ts>.csv)")
    p.add_argument("--print", type=int, default=0,
                   help="Also print first N rows to stdout")
    return p.parse_args()


async def main() -> int:
    args = parse_args()
    db = SQLiteClient()

    rows = await db.get_contacts(
        company=args.company,
        limit=args.limit,
    )
    if args.source:
        rows = [r for r in rows if (r.get("source") or "").lower() == args.source.lower()]
    if args.emails_only:
        rows = [r for r in rows if r.get("email")]
    if args.linkedin_only:
        rows = [r for r in rows if r.get("linkedin_url")]

    out_path = (
        Path(args.output) if args.output
        else ROOT / "data" / "exports" / f"contacts_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv"
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "company", "full_name", "first_name", "last_name", "title", "role",
        "email", "linkedin_url", "linkedin_search_url",
        "source", "confidence", "company_domain", "related_job_id",
        "discovered_at", "last_verified_at",
    ]

    with out_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fieldnames})

    # Summary stats
    total = len(rows)
    with_email = sum(1 for r in rows if r.get("email"))
    with_linkedin = sum(1 for r in rows if r.get("linkedin_url"))
    by_source: dict[str, int] = {}
    by_company: dict[str, int] = {}
    for r in rows:
        src = (r.get("source") or "unknown").lower()
        by_source[src] = by_source.get(src, 0) + 1
        comp = r.get("company") or "?"
        by_company[comp] = by_company.get(comp, 0) + 1

    print()
    print("=" * 70)
    print(f"Wrote {total} contacts -> {out_path}")
    print("=" * 70)
    print(f"  with email:        {with_email}  ({100*with_email/max(total,1):.0f}%)")
    print(f"  with LinkedIn URL: {with_linkedin}")
    print(f"  unique companies:  {len(by_company)}")
    print()
    print("By source:")
    for src, n in sorted(by_source.items(), key=lambda x: -x[1]):
        print(f"  {src:<22} {n:>4}")
    print()
    print(f"Top 10 companies by contact count:")
    for comp, n in sorted(by_company.items(), key=lambda x: -x[1])[:10]:
        print(f"  {n:>3} - {comp}")

    if args.print:
        print()
        print(f"--- First {min(args.print, total)} rows ---")
        for r in rows[:args.print]:
            line = (
                f"  [{(r.get('source') or '?'):>20}] "
                f"{(r.get('confidence') or '?'):<9} "
                f"{(r.get('company') or '?'):<24} | "
                f"{(r.get('full_name') or '-'):<24} | "
                f"{(r.get('email') or '-'):<32} | "
                f"{(r.get('linkedin_url') or '-')[:55]}"
            )
            print(line)

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

"""
PlaceUp - Export Contacts For ALL Sponsors

Reads the H1B sponsor CSV (default: data/h1b/sponsors_2024_2025_2026.csv,
480+ companies), runs find_contacts() against every one of them, and
writes a flat CSV with EVERY contact found (not just stats).

Output:
  data/exports/all_contacts.csv          ← one row per (company, contact)
  data/exports/all_contacts_summary.csv  ← one row per company, with counts

KEY FEATURES:
  - Resumable. Re-running skips companies already enriched in cache.
  - Hunter-quota-aware. --max-hunter-calls caps API spend per run so you
    don't burn your monthly free tier.
  - Concurrency-capped. Polite to free APIs.
  - Free-mode toggles. Disable Hunter/Apollo to use only DOL/team-page/GitHub
    (then you can do all 480 companies for $0/month).

Usage examples:

  # Free-only mode (all 480 companies, $0 cost — uses DOL+team-page+GitHub)
  python scripts/export_all_contacts.py

  # With Hunter, 25 calls max (one month of free tier)
  python scripts/export_all_contacts.py --use-hunter --max-hunter-calls 25

  # All sources, but cap at first 100 companies (skip the rest)
  python scripts/export_all_contacts.py --use-hunter --use-apollo --limit 100

  # Resume after stopping
  python scripts/export_all_contacts.py --use-hunter --resume

  # Custom input CSV
  python scripts/export_all_contacts.py --csv data/h1b/my_sponsors.csv
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import logging
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.config import settings
from app.db.local_db import SQLiteClient
from app.services.contact_finder import find_contacts

logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("placeup.export_all")
logger.setLevel(logging.INFO)


def parse_args():
    p = argparse.ArgumentParser(description="Export contacts for ALL H1B sponsors")
    p.add_argument("--csv", default="data/h1b/sponsors_2024_2025_2026.csv",
                   help="Input H1B sponsors CSV")
    p.add_argument("--limit", type=int, default=None,
                   help="Process only the first N companies (skip rest)")
    p.add_argument("--max-contacts", type=int, default=15,
                   help="Per-company cap on contacts returned")
    p.add_argument("--concurrency", type=int, default=4,
                   help="Parallel companies (free APIs prefer low concurrency)")
    p.add_argument("--use-hunter", action="store_true",
                   help="Use Hunter.io (uses platform key + counts toward quota)")
    p.add_argument("--use-apollo", action="store_true",
                   help="Use Apollo.io")
    p.add_argument("--use-google-xray", action="store_true",
                   help="Use Google X-ray (SerpAPI)")
    p.add_argument("--max-hunter-calls", type=int, default=20,
                   help="Stop using Hunter after this many calls (default 20 to leave 5 buffer on free tier)")
    p.add_argument("--max-apollo-calls", type=int, default=50,
                   help="Stop using Apollo after this many results (free tier 60/mo)")
    p.add_argument("--resume", action="store_true",
                   help="Skip companies already cached (no force-refresh)")
    p.add_argument("--output-dir", default="data/exports",
                   help="Where to write CSVs")
    p.add_argument("--guess-domain", action="store_true", default=True,
                   help="Auto-guess company domain from name (helps Hunter)")
    return p.parse_args()


def _guess_domain(employer_name: str) -> str | None:
    """Use the curated sponsor_domains mapping (covers ~200 top sponsors)."""
    from app.services.sponsor_domains import best_domain, is_safe_domain
    d = best_domain(employer_name)
    return d if (d and is_safe_domain(d)) else None




def _dedup_key_from_row(row: dict):
    """Stable dedup key for a contact row.

    Priority: email > linkedin_url > linkedin_search_url > (company, full_name).
    Same person harvested twice (different sources, different runs) collapses
    to one key.
    """
    company = (row.get("company") or "").lower().strip()
    email = (row.get("email") or "").lower().strip()
    li = (row.get("linkedin_url") or "").lower().strip()
    li_search = (row.get("linkedin_search_url") or "").lower().strip()
    name = (row.get("full_name") or "").lower().strip()
    if email:
        return f"e|{email}"
    if li:
        return f"l|{li}"
    if li_search:
        return f"s|{company}|{li_search}"
    if name and company:
        return f"n|{company}|{name}"
    return None


def _read_sponsors(csv_path: Path) -> list[dict]:
    rows = []
    with csv_path.open("r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            name = (row.get("employer_name") or "").strip()
            if not name:
                continue
            rows.append({
                "company": name,
                "petitions": int(row.get("total_petitions") or 0),
            })
    return rows


def _load_resume_set(out_csv: Path) -> set[str]:
    if not out_csv.exists():
        return set()
    seen = set()
    try:
        with out_csv.open("r", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if row.get("company"):
                    seen.add(row["company"].lower().strip())
    except Exception:
        pass
    return seen


async def _enrich_one(
    sponsor: dict, *, args, db, hunter_call_budget, apollo_call_budget,
) -> tuple[dict, list[dict]]:
    """Returns (summary_row, list_of_flat_contact_rows)."""
    company = sponsor["company"]
    domain = _guess_domain(company) if args.guess_domain else None

    # Toggle Hunter/Apollo OFF if budget exhausted
    use_hunter_now = args.use_hunter and hunter_call_budget["remaining"] > 0
    use_apollo_now = args.use_apollo and apollo_call_budget["remaining"] > 0

    try:
        result = await find_contacts(
            company=company,
            domain=domain,
            db=db,
            max_contacts=args.max_contacts,
            use_hunter=use_hunter_now,
            use_apollo=use_apollo_now,
            use_google_xray=args.use_google_xray,
            force_refresh=not args.resume,
        )
    except Exception as exc:
        logger.warning("FAIL %s: %s", company, exc)
        return (
            {"company": company, "domain": domain or "", "contacts": 0,
             "with_email": 0, "verified_emails": 0, "with_linkedin": 0,
             "sources": "", "credits": "", "error": str(exc)},
            [],
        )

    # Decrement budgets
    hunter_call_budget["remaining"] -= result.api_credits_used.get("hunter", 0) and 1 or 0
    apollo_call_budget["remaining"] -= result.api_credits_used.get("apollo", 0)

    # Flat rows for the per-contact CSV
    flat_rows = []
    for c in result.contacts:
        flat_rows.append({
            "company": c.company,
            "petitions": sponsor.get("petitions", 0),
            "domain": domain or "",
            "full_name": c.full_name or "",
            "first_name": c.first_name or "",
            "last_name": c.last_name or "",
            "title": c.title or "",
            "role": c.role.value if hasattr(c.role, "value") else str(c.role),
            "email": c.email or "",
            "linkedin_url": c.linkedin_url or "",
            "linkedin_search_url": c.linkedin_search_url or "",
            "source": c.source.value if hasattr(c.source, "value") else str(c.source),
            "confidence": c.confidence.value if hasattr(c.confidence, "value") else str(c.confidence),
            "discovered_at": c.discovered_at.isoformat() if c.discovered_at else "",
        })

    # Count BOTH actual profile URLs and the clickable search URLs we generate
    li_profiles = sum(1 for c in result.contacts if c.linkedin_url)
    li_search_urls = sum(1 for c in result.contacts if c.linkedin_search_url)
    summary_row = {
        "company": company,
        "domain": domain or "",
        "contacts": len(result.contacts),
        "with_email": sum(1 for c in result.contacts if c.email),
        "verified_emails": sum(1 for c in result.contacts
                                if c.email and (c.confidence.value if hasattr(c.confidence, "value") else "") == "verified"),
        "with_linkedin": li_profiles + li_search_urls,  # NEW: includes search URLs
        "linkedin_profiles": li_profiles,
        "linkedin_search_urls": li_search_urls,
        "sources": ", ".join(s.value for s in result.sources_used),
        "credits": ", ".join(f"{k}={v}" for k, v in result.api_credits_used.items()) or "$0",
        "cache_hit": result.cache_hit,
        "error": "",
    }
    return summary_row, flat_rows


async def main() -> int:
    args = parse_args()
    csv_path = ROOT / args.csv if not Path(args.csv).is_absolute() else Path(args.csv)
    if not csv_path.exists():
        print(f"ERROR: input CSV not found: {csv_path}")
        print(f"Run first: python scripts/import_h1b_2024_2026.py")
        return 1

    sponsors = _read_sponsors(csv_path)
    if args.limit:
        sponsors = sponsors[: args.limit]

    out_dir = ROOT / args.output_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    out_flat = out_dir / "all_contacts.csv"
    out_summary = out_dir / "all_contacts_summary.csv"

    resume_set = _load_resume_set(out_flat) if args.resume else set()
    if resume_set:
        before = len(sponsors)
        sponsors = [s for s in sponsors if s["company"].lower().strip() not in resume_set]
        print(f"Resume mode: skipping {before - len(sponsors)} companies already in {out_flat.name}")

    print(f"\nProcessing {len(sponsors)} companies from {csv_path.name}")
    print(f"  Sources: hunter={args.use_hunter}  apollo={args.use_apollo}  "
          f"xray={args.use_google_xray}  + free (DOL/team/github/ATS) always on")
    if args.use_hunter:
        print(f"  Hunter quota cap: {args.max_hunter_calls} calls (free tier: 25/month)")
    print()

    db = SQLiteClient()
    semaphore = asyncio.Semaphore(args.concurrency)
    hunter_call_budget = {"remaining": args.max_hunter_calls}
    apollo_call_budget = {"remaining": args.max_apollo_calls}

    # Open both CSVs in append mode (so resume keeps existing data)
    flat_exists = out_flat.exists()
    summary_exists = out_summary.exists()

    flat_fields = ["company", "petitions", "domain", "full_name", "first_name", "last_name",
                   "title", "role", "email", "linkedin_url", "linkedin_search_url",
                   "source", "confidence", "discovered_at"]
    summary_fields = ["company", "domain", "contacts", "with_email", "verified_emails",
                      "with_linkedin", "linkedin_profiles", "linkedin_search_urls",
                      "dedup_kept", "dedup_dropped",
                      "sources", "credits", "cache_hit", "error"]

    flat_f = out_flat.open("a" if flat_exists else "w", newline="", encoding="utf-8")
    summary_f = out_summary.open("a" if summary_exists else "w", newline="", encoding="utf-8")
    flat_w = csv.DictWriter(flat_f, fieldnames=flat_fields)
    summary_w = csv.DictWriter(summary_f, fieldnames=summary_fields)

    # ── DEDUP STATE ──
    # If resuming, load existing keys from disk so we never write duplicates.
    seen_keys: set[str] = set()
    if flat_exists:
        try:
            with out_flat.open("r", encoding="utf-8") as _fr:
                for r in csv.DictReader(_fr):
                    k = _dedup_key_from_row(r)
                    if k:
                        seen_keys.add(k)
            print(f"Loaded {len(seen_keys)} existing dedup keys from {out_flat.name}")
        except Exception as exc:
            print(f"WARN: could not pre-load dedup keys: {exc}")
    if not flat_exists:
        flat_w.writeheader()
    if not summary_exists:
        summary_w.writeheader()

    totals = {"companies": 0, "contacts": 0, "emails": 0, "linkedin": 0}

    async def _process(sponsor: dict):
        async with semaphore:
            summary, flat = await _enrich_one(
                sponsor, args=args, db=db,
                hunter_call_budget=hunter_call_budget,
                apollo_call_budget=apollo_call_budget,
            )
            return summary, flat

    # Process sequentially-ish but with bounded concurrency
    tasks = [_process(s) for s in sponsors]
    for i, fut in enumerate(asyncio.as_completed(tasks), 1):
        summary, flat = await fut
        totals["companies"] += 1
        totals["contacts"] += summary["contacts"]
        totals["emails"] += summary["with_email"]
        totals["linkedin"] += summary["with_linkedin"]

        kept = 0
        skipped_dupes = 0
        for row in flat:
            k = _dedup_key_from_row(row)
            if k and k in seen_keys:
                skipped_dupes += 1
                continue
            if k:
                seen_keys.add(k)
            flat_w.writerow(row)
            kept += 1
        summary["dedup_kept"] = kept
        summary["dedup_dropped"] = skipped_dupes
        summary_w.writerow(summary)
        flat_f.flush()
        summary_f.flush()

        budget_note = ""
        if args.use_hunter:
            budget_note = f"  [hunter remaining: {hunter_call_budget['remaining']}]"
        print(f"  [{i:>4}/{len(sponsors)}]  {summary['company'][:38]:<38}  "
              f"contacts={summary['contacts']:>3}  emails={summary['with_email']:>2}  "
              f"li_url={summary.get('linkedin_search_urls', 0):>2}+{summary.get('linkedin_profiles', 0)}  "
              f"{summary['credits']}{budget_note}")

        # Hard-stop if Hunter budget hit zero
        if args.use_hunter and hunter_call_budget["remaining"] <= 0:
            print(f"\n*** Hunter quota cap reached ({args.max_hunter_calls}). "
                  f"Continuing with FREE sources only for remaining companies. ***\n")
            args.use_hunter = False  # turn off for the rest

    flat_f.close()
    summary_f.close()

    print()
    print("=" * 70)
    print("EXPORT COMPLETE")
    print("=" * 70)
    print(f"  Companies processed:  {totals['companies']}")
    print(f"  Total contact rows:   {totals['contacts']}")
    print(f"  With email:           {totals['emails']}")
    print(f"  With LinkedIn URL:    {totals['linkedin']}")
    print()
    print(f"  Per-contact CSV:  {out_flat}")
    print(f"  Per-company CSV:  {out_summary}")
    print()
    print("To inspect:")
    print(f"  python scripts/dump_contacts.py --emails-only --print 30")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

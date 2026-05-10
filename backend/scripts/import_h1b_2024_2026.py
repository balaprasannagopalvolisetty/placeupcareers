"""
PlaceUp - 2024-2026 H1B Sponsor Importer

Pulls the full FY2024 + FY2025 + FY2026 H1B sponsor leaderboards from every
free public source (myvisajobs, h1bdata, h1bgrader, h1data, DOL FLC), dedupes
by employer, and writes the unified roster to:

  data/h1b/sponsors_2024_2026.csv
  ↳ also upserted into the SQLite h1b_sponsors table

Usage:
  python scripts/import_h1b_2024_2026.py
  python scripts/import_h1b_2024_2026.py --years 2024,2025,2026
  python scripts/import_h1b_2024_2026.py --limit-per-year 1000
  python scripts/import_h1b_2024_2026.py --uscis-csv data/uscis/h1b_fy2024.csv

If you've downloaded the official USCIS H-1B Hub CSV, pass its path with
--uscis-csv to merge it in (USCIS is the most authoritative source).
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.db.local_db import SQLiteClient
from app.services.h1b_data import build_recent_sponsors

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("placeup.h1b_import")


def parse_args():
    p = argparse.ArgumentParser(description="Import 2024-2026 H1B sponsor data")
    p.add_argument("--years", default="2024,2025,2026",
                   help="Comma-separated fiscal years (default: 2024,2025,2026)")
    p.add_argument("--limit-per-year", type=int, default=500,
                   help="Max sponsors per leaderboard per year")
    p.add_argument("--uscis-csv", action="append", default=[],
                   help="Path(s) to USCIS H-1B Hub CSVs (repeatable, e.g. --uscis-csv data/uscis/h1b_fy2024.csv)")
    p.add_argument("--output-dir", default="data/h1b",
                   help="Where to write the merged CSV")
    p.add_argument("--no-db", action="store_true",
                   help="Skip writing to SQLite (CSV only)")
    return p.parse_args()


async def main() -> int:
    args = parse_args()
    years = tuple(int(y.strip()) for y in args.years.split(",") if y.strip())

    # Build the {year: csv_path} map for USCIS CSVs (best-effort filename detection)
    uscis_paths: dict[int, str] = {}
    for path in args.uscis_csv:
        for y in years:
            if str(y) in Path(path).name:
                uscis_paths[y] = path
                break

    logger.info("=" * 60)
    logger.info("H1B 2024-2026 Sponsor Import")
    logger.info("  years:           %s", years)
    logger.info("  limit per year:  %s", args.limit_per_year)
    logger.info("  USCIS CSVs:      %s", uscis_paths or "(none)")
    logger.info("  leaderboards:    myvisajobs + h1bgrader + h1data + h1bdata.info topcompanies")
    logger.info("=" * 60)

    sponsors = await build_recent_sponsors(
        years=years,
        per_year_limit=args.limit_per_year,
        uscis_csv_paths=uscis_paths,
    )

    if not sponsors:
        logger.warning("No sponsors collected. Check network connectivity / sites may be down.")
        return 1

    # Write CSV
    out_dir = ROOT / args.output_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    yrs = "_".join(str(y) for y in years)
    csv_path = out_dir / f"sponsors_{yrs}.csv"

    fieldnames = [
        "employer_name", "city", "state", "zip_code",
        "total_petitions", "initial_approvals", "initial_denials",
        "continuing_approvals", "continuing_denials",
        "approval_rate_pct", "fiscal_year", "id",
    ]
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for s in sponsors:
            w.writerow({
                "employer_name": s.employer_name,
                "city": s.city,
                "state": s.state,
                "zip_code": s.zip_code,
                "total_petitions": s.total_petitions,
                "initial_approvals": s.initial_approvals,
                "initial_denials": s.initial_denials,
                "continuing_approvals": s.continuing_approvals,
                "continuing_denials": s.continuing_denials,
                "approval_rate_pct": s.approval_rate,
                "fiscal_year": s.fiscal_year,
                "id": s.id,
            })

    logger.info("Wrote %s sponsors to %s", len(sponsors), csv_path)

    # Upsert to SQLite
    if not args.no_db:
        db = SQLiteClient()
        rows = [s.model_dump(mode="json") for s in sponsors]
        n = await db.upsert_h1b_sponsors(rows)
        logger.info("Upserted %s sponsors into SQLite (%s)", n, db.db_path)

    # Print top 20 to stdout for sanity
    print("\nTop 20 by petition count:")
    for s in sorted(sponsors, key=lambda r: r.total_petitions, reverse=True)[:20]:
        print(f"  {s.total_petitions:>7,} - {s.employer_name}")

    print(f"\nFull list saved: {csv_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

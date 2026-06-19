"""
Country backfill — re-resolves the `country` of existing job rows using the
corrected location logic in `app.services.global_visa_rules.resolve_country`.

Why this exists
---------------
Three location bugs mislabeled historical rows, and a fix only applies to
newly-scraped jobs. This one-time (or occasional) worker repairs the rows
already in the database:

  1. Unparseable locations ("Remote - EMEA", "Hybrid", blank) were defaulted
     to "US". Now corrected to UNKNOWN ("").
  2. "City, UK" was stored as the invalid code "UK". Now corrected to "GB".
  3. "City, CA/DE/IN" (California/Delaware/Indiana) was resolved to the
     COUNTRY (Canada/Germany/India). Now disambiguated to the US state.

Recompute rules (conservative — never blanks out a legitimately-set country):
  - Empty location           -> leave row untouched (could be an explicit
                                country from a connector with no location).
  - Location resolves to X   -> set country = X if different.
  - Location doesn't resolve  -> only fix the known US-default mislabel
                                (current country == "US" -> set "").

Idempotent and safe to re-run. Reads in keyset-paginated batches by id.

CLI:
    python -m app.workers.country_backfill --dry-run            # preview counts
    python -m app.workers.country_backfill --limit 5000         # cap scan
    python -m app.workers.country_backfill                      # full run
"""

from __future__ import annotations

import argparse
import logging
import time
from typing import Optional

from sqlalchemy import text

from app.db.postgres import PostgresClient
from app.services.global_visa_rules import resolve_country

logger = logging.getLogger("placeup.workers.country_backfill")

_TABLES = ("master_jobs", "jobs")


def _recompute(location: Optional[str], current: Optional[str]) -> Optional[str]:
    """Return the corrected country to store, or None for "no change"."""
    loc = (location or "").strip()
    cur = (current or "").strip().upper()
    if not loc:
        return None  # no location to re-resolve; preserve any explicit value
    new = resolve_country(loc)
    if new:
        new = new.upper()
        return new if new != cur else None
    # Location is non-empty but unresolvable: only correct the US-default bug.
    if cur == "US":
        return ""  # unknown; still passes the target-country prefilter
    return None


def _backfill_table(db, table: str, *, limit: Optional[int], batch_size: int, dry_run: bool) -> dict:
    scanned = 0
    changed = 0
    last_id = None
    samples: list[tuple[str, str, str]] = []
    while True:
        if last_id is None:
            rows = db.execute(
                text(f"SELECT id, location, country FROM {table} ORDER BY id LIMIT :b"),
                {"b": batch_size},
            ).all()
        else:
            rows = db.execute(
                text(f"SELECT id, location, country FROM {table} WHERE id > :lid ORDER BY id LIMIT :b"),
                {"lid": last_id, "b": batch_size},
            ).all()
        if not rows:
            break
        updates: list[dict] = []
        for rid, location, country in rows:
            scanned += 1
            new = _recompute(location, country)
            if new is not None:
                updates.append({"id": rid, "country": new})
                if len(samples) < 15:
                    samples.append((str(location or "")[:42], (country or "").upper() or "∅", new or "∅"))
            last_id = rid
        if updates and not dry_run:
            db.execute(text(f"UPDATE {table} SET country = :country WHERE id = :id"), updates)
            db.commit()
        changed += len(updates)
        if limit and scanned >= limit:
            break
    return {"table": table, "scanned": scanned, "changed": changed, "samples": samples}


def run(*, limit: Optional[int] = None, batch_size: int = 1000, dry_run: bool = False, tables=_TABLES) -> dict:
    started = time.monotonic()
    client = PostgresClient()
    results = []
    with client.session() as db:
        existing = {t for t in tables if db.execute(text("SELECT to_regclass(:t)"), {"t": f"public.{t}"}).scalar()}
        for table in tables:
            if table not in existing:
                logger.info("Skipping %s (table not present)", table)
                continue
            results.append(_backfill_table(db, table, limit=limit, batch_size=batch_size, dry_run=dry_run))
    elapsed = round(time.monotonic() - started, 1)
    total_changed = sum(r["changed"] for r in results)
    total_scanned = sum(r["scanned"] for r in results)
    logger.info("Country backfill %s: scanned=%s changed=%s in %ss",
                "DRY-RUN" if dry_run else "APPLIED", total_scanned, total_changed, elapsed)
    for r in results:
        logger.info("  %s: scanned=%s changed=%s", r["table"], r["scanned"], r["changed"])
        for loc, was, now in r["samples"]:
            logger.info("    %-42s %s -> %s", loc, was, now)
    return {"dry_run": dry_run, "elapsed_s": elapsed, "total_scanned": total_scanned,
            "total_changed": total_changed, "tables": results}


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    parser = argparse.ArgumentParser(description="Re-resolve country for existing job rows.")
    parser.add_argument("--dry-run", action="store_true", help="Preview counts without writing.")
    parser.add_argument("--limit", type=int, default=None, help="Max rows to scan per table.")
    parser.add_argument("--batch-size", type=int, default=1000, help="Rows per page.")
    args = parser.parse_args()
    run(limit=args.limit, batch_size=args.batch_size, dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

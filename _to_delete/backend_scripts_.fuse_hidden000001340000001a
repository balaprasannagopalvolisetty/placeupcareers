"""
PlaceUp - Profiles → 2-Sheet xlsx

Reads any source of contact rows (default = data/exports/all_contacts.csv,
or the SQLite contacts table) and:

  1. Fuzzy-matches each contact's company name against the H1B sponsor list
     loaded from data/h1b/h1b_us_companies.csv (22,901 companies from your
     uploaded H1b_US_DataLIst.xlsx).
  2. Splits results into two sheets:
        - h1b_company_profiles    : matched against H1B sponsor
        - regular_company_profiles: not in the H1B list
  3. Writes columns: name, company, position (title), email, linkedin_url,
     linkedin_search_url, source, confidence, h1b_match (the matched
     canonical employer name), match_score.

  Optionally also runs FinalScout bulk LinkedIn-URL enrichment on rows
  that have a LinkedIn profile URL but no email yet (--enrich-with-finalscout).

Usage:
    # From the existing contacts CSV
    python scripts/profiles_to_xlsx.py

    # From SQLite (everything cached)
    python scripts/profiles_to_xlsx.py --from-db

    # From a CSV of LinkedIn URLs you collected manually (one per line, no header)
    python scripts/profiles_to_xlsx.py --linkedin-urls-file my_urls.txt --enrich-with-finalscout

    # Custom output
    python scripts/profiles_to_xlsx.py --output data/exports/h1b_profiles.xlsx
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

from app.db.postgres import PostgresClient

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                    datefmt="%H:%M:%S")
logger = logging.getLogger("placeup.profiles_xlsx")


def parse_args():
    p = argparse.ArgumentParser(description="Split contacts into H1B / regular sheets")
    p.add_argument("--input-csv", default="data/exports/all_contacts.csv",
                   help="Source contacts CSV (from export_all_contacts.py)")
    p.add_argument("--from-db", action="store_true",
                   help="Load contacts from SQLite instead of CSV")
    p.add_argument("--h1b-csv", default="data/h1b/h1b_us_companies.csv",
                   help="H1B sponsor list (from import_h1b xlsx -> csv)")
    p.add_argument("--output", default=None,
                   help="Output xlsx (default: data/exports/h1b_profiles_<ts>.xlsx)")
    p.add_argument("--match-threshold", type=int, default=85,
                   help="Fuzzy match score threshold (0-100). Default 85.")
    p.add_argument("--linkedin-urls-file", default=None,
                   help="Path to a text file with LinkedIn URLs (one per line) to bulk-enrich")
    p.add_argument("--enrich-with-finalscout", action="store_true",
                   help="Submit FinalScout bulk linkedin job for any URL-only rows")
    p.add_argument("--finalscout-batch-size", type=int, default=100,
                   help="Max URLs per FinalScout bulk task")
    return p.parse_args()


def _normalize_company_name(name: str) -> str:
    """Normalize for fuzzy matching: uppercase, strip suffixes/punctuation."""
    if not name:
        return ""
    n = name.upper().strip()
    for suffix in [
        " INC", " LLC", " LTD", " LIMITED", " LLP", " LP", " CORPORATION",
        " CORP", " CO", " COMPANY", "., ", ".",
        " THE", " US", " USA", " GLOBAL", " AMERICAS", " AMERICA",
        " HOLDINGS", " GROUP", " ENTERPRISES", " SERVICES", " SOLUTIONS",
        " TECHNOLOGY", " TECHNOLOGIES", " CONSULTING",
    ]:
        n = n.replace(suffix, " ")
    n = " ".join(n.split())
    n = n.rstrip(",.").strip()
    return n


def _fuzzy_score(a: str, b: str) -> int:
    """Token-set fuzzy ratio 0-100 (no rapidfuzz dep — use difflib)."""
    from difflib import SequenceMatcher
    if not a or not b:
        return 0
    na, nb = _normalize_company_name(a), _normalize_company_name(b)
    if na == nb:
        return 100
    # Substring containment is only safe if BOTH names share the first significant
    # word (avoids false positives like "Acme" matching "ACME CONTROL SYSTEM").
    a_first = na.split()[0] if na.split() else ""
    b_first = nb.split()[0] if nb.split() else ""
    if a_first and a_first == b_first and (na in nb or nb in na):
        return 95
    return int(SequenceMatcher(None, na, nb).ratio() * 100)


def _load_h1b_companies(csv_path: Path) -> dict[str, dict]:
    """Return dict mapping NORMALIZED name -> H1B company dict."""
    if not csv_path.exists():
        logger.error(f"H1B CSV not found: {csv_path}")
        return {}
    out: dict[str, dict] = {}
    with csv_path.open("r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            name = (row.get("employer_name") or "").strip()
            if not name:
                continue
            norm = _normalize_company_name(name)
            if not norm:
                continue
            # Keep first occurrence; multiple raw names may collapse to same normalized form
            if norm not in out:
                out[norm] = row
    logger.info(f"Loaded {len(out)} unique normalized H1B employers from {csv_path}")
    return out


def _classify(company: str, h1b_index: dict[str, dict], threshold: int = 85) -> tuple[bool, str, int]:
    """Returns (is_h1b, matched_canonical_name, score)."""
    if not company:
        return False, "", 0
    norm = _normalize_company_name(company)
    if not norm:
        return False, "", 0
    if norm in h1b_index:
        return True, h1b_index[norm]["employer_name"], 100
    # Fast prefix scan: only do full fuzzy on candidates sharing first significant word
    first_token = norm.split()[0] if norm.split() else ""
    candidates = [(k, v) for k, v in h1b_index.items() if k.startswith(first_token)]
    if not candidates:
        # broaden to any containment
        candidates = [(k, v) for k, v in h1b_index.items() if first_token and first_token in k]
    best = ("", 0, None)
    for k, v in candidates[:200]:  # cap
        s = _fuzzy_score(norm, k)
        if s > best[1]:
            best = (k, s, v)
    if best[1] >= threshold:
        return True, best[2]["employer_name"], best[1]
    return False, "", best[1]


def _load_input_contacts(args) -> list[dict]:
    """Load contacts either from CSV or SQLite."""
    if args.from_db:
        async def _load():
            db = PostgresClient()
            return await db.get_contacts(limit=100000)
        rows = asyncio.run(_load())
        logger.info(f"Loaded {len(rows)} contacts from SQLite")
        return rows
    csv_path = ROOT / args.input_csv if not Path(args.input_csv).is_absolute() else Path(args.input_csv)
    if not csv_path.exists():
        logger.error(f"Input CSV not found: {csv_path}")
        logger.error("Run scripts/export_all_contacts.py first to generate it.")
        return []
    rows = []
    with csv_path.open("r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            rows.append(row)
    logger.info(f"Loaded {len(rows)} contacts from {csv_path}")
    return rows


async def _enrich_via_finalscout(rows: list[dict], batch_size: int) -> list[dict]:
    """Submit LinkedIn URLs from rows that have li_url but no email to FinalScout bulk."""
    from app.services.finalscout_enrichment import (
        submit_linkedin_bulk, collect_bulk_contacts,
    )
    urls = []
    for r in rows:
        li = (r.get("linkedin_url") or "").strip()
        if li and not (r.get("email") or "").strip():
            urls.append(li)
    urls = list(dict.fromkeys(urls))  # dedupe order-preserving
    logger.info(f"FinalScout: {len(urls)} URL-only rows queued for bulk enrichment")

    enriched = []
    for i in range(0, len(urls), batch_size):
        batch = urls[i:i + batch_size]
        task_id = await submit_linkedin_bulk(
            batch,
            name=f"PlaceUp profiles_to_xlsx batch {i // batch_size + 1}",
            enable_personal_email=False,
            enable_generic_email=False,
        )
        if not task_id:
            logger.warning(f"Batch {i}: submit failed")
            continue
        logger.info(f"Batch {i}: task_id={task_id}, polling...")
        contacts = await collect_bulk_contacts(task_id)
        for c in contacts:
            enriched.append({
                "company": c.company,
                "full_name": c.full_name,
                "first_name": c.first_name,
                "last_name": c.last_name,
                "title": c.title,
                "role": c.role.value if hasattr(c.role, "value") else str(c.role),
                "email": c.email,
                "linkedin_url": c.linkedin_url,
                "linkedin_search_url": "",
                "source": "finalscout",
                "confidence": c.confidence.value if hasattr(c.confidence, "value") else str(c.confidence),
            })
    logger.info(f"FinalScout bulk: collected {len(enriched)} new contacts")
    return enriched


def _load_linkedin_urls_file(path: Path) -> list[dict]:
    """Read a plain text file of LinkedIn URLs (one per line) into row stubs."""
    rows = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            url = line.strip()
            if url and "linkedin.com/in/" in url:
                rows.append({
                    "company": "",
                    "full_name": "",
                    "title": "",
                    "email": "",
                    "linkedin_url": url,
                    "linkedin_search_url": "",
                    "source": "manual",
                    "confidence": "unknown",
                })
    logger.info(f"Loaded {len(rows)} LinkedIn URLs from {path}")
    return rows


def _write_xlsx(matched: list[dict], unmatched: list[dict], output_path: Path):
    """Write 2-sheet xlsx with auto-styled headers."""
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment

    wb = openpyxl.Workbook()
    wb.remove(wb.active)

    cols = [
        ("name",           lambda r: r.get("full_name") or ""),
        ("company",        lambda r: r.get("company") or ""),
        ("h1b_match",      lambda r: r.get("h1b_match") or ""),
        ("match_score",    lambda r: r.get("match_score") or ""),
        ("position",       lambda r: r.get("title") or ""),
        ("role",           lambda r: r.get("role") or ""),
        ("email",          lambda r: r.get("email") or ""),
        ("linkedin_url",   lambda r: r.get("linkedin_url") or ""),
        ("search_url",     lambda r: r.get("linkedin_search_url") or ""),
        ("source",         lambda r: r.get("source") or ""),
        ("confidence",     lambda r: r.get("confidence") or ""),
    ]

    header_font = Font(bold=True, color="FFFFFF")
    header_fill_h1b = PatternFill("solid", fgColor="1F77B4")
    header_fill_reg = PatternFill("solid", fgColor="2CA02C")

    for sheet_name, rows, fill in (
        ("h1b_company_profiles", matched, header_fill_h1b),
        ("regular_company_profiles", unmatched, header_fill_reg),
    ):
        ws = wb.create_sheet(sheet_name)
        # header row
        for ci, (col, _) in enumerate(cols, 1):
            cell = ws.cell(row=1, column=ci, value=col)
            cell.font = header_font
            cell.fill = fill
            cell.alignment = Alignment(horizontal="center")
        # data rows
        for ri, row in enumerate(rows, 2):
            for ci, (col, accessor) in enumerate(cols, 1):
                ws.cell(row=ri, column=ci, value=accessor(row))
        # auto column widths (cap)
        for ci, (col, _) in enumerate(cols, 1):
            max_len = max(
                [len(str(r.get(col, "") or "")) for r in rows[:200]] + [len(col)]
            )
            ws.column_dimensions[ws.cell(row=1, column=ci).column_letter].width = min(max_len + 2, 60)
        ws.freeze_panes = "A2"

    wb.save(output_path)
    logger.info(f"Wrote {output_path}")


async def main() -> int:
    args = parse_args()

    # 1. Load H1B index
    h1b_index = _load_h1b_companies(ROOT / args.h1b_csv)
    if not h1b_index:
        return 1

    # 2. Load source contacts
    rows = _load_input_contacts(args)

    # 3. Optional: also pull LinkedIn URLs from a file
    if args.linkedin_urls_file:
        rows.extend(_load_linkedin_urls_file(Path(args.linkedin_urls_file)))

    # 4. Optional: bulk-enrich URL-only rows via FinalScout
    if args.enrich_with_finalscout:
        new_rows = await _enrich_via_finalscout(rows, batch_size=args.finalscout_batch_size)
        rows.extend(new_rows)

    if not rows:
        logger.error("No input rows. Run export_all_contacts.py or pass --linkedin-urls-file.")
        return 1

    # 5. Classify each row
    matched, unmatched = [], []
    for r in rows:
        company = (r.get("company") or "").strip()
        is_h1b, canonical, score = _classify(company, h1b_index, threshold=args.match_threshold)
        r["h1b_match"] = canonical
        r["match_score"] = score
        (matched if is_h1b else unmatched).append(r)

    # 6. Dedupe within each sheet (email > linkedin_url > company+name)
    def _dedup(in_rows):
        seen = set()
        out = []
        for r in in_rows:
            key = ((r.get("email") or "").lower().strip()
                   or (r.get("linkedin_url") or "").lower().strip()
                   or f"{(r.get('company') or '').lower()}|{(r.get('full_name') or '').lower()}")
            if not key or key in seen:
                continue
            seen.add(key)
            out.append(r)
        return out

    before_m, before_u = len(matched), len(unmatched)
    matched = _dedup(matched)
    unmatched = _dedup(unmatched)

    # 7. Output
    out_path = Path(args.output) if args.output else (
        ROOT / "data" / "exports" / f"h1b_profiles_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.xlsx"
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    _write_xlsx(matched, unmatched, out_path)

    print()
    print("=" * 70)
    print(f"H1B sponsor companies in catalog: {len(h1b_index):>6}")
    print(f"Total input rows:                 {len(rows):>6}")
    print(f"Matched H1B (after dedup):        {len(matched):>6}  (was {before_m})")
    print(f"  - with email:                   {sum(1 for r in matched if r.get('email')):>6}")
    print(f"  - with linkedin_url:            {sum(1 for r in matched if r.get('linkedin_url')):>6}")
    print(f"Regular companies (after dedup):  {len(unmatched):>6}  (was {before_u})")
    print(f"  - with email:                   {sum(1 for r in unmatched if r.get('email')):>6}")
    print(f"  - with linkedin_url:            {sum(1 for r in unmatched if r.get('linkedin_url')):>6}")
    print(f"Output:                           {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

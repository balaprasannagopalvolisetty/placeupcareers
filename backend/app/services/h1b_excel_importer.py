"""
PlaceUp Career — H1B Excel importer.

Imports the curated `H1b_US_DataLIst.xlsx` file (USCIS Employer Data
Hub format) into the `h1b_sponsors` table. Idempotent — re-running on
startup updates counts in place.

The Excel columns we care about:
  - Employer (Petitioner) Name
  - Petitioner City / State / Zip Code
  - New Employment Approval / Denial
  - Continuation Approval / Denial
  - Fiscal Year

Aggregated per (employer_name, city, state, fiscal_year).
"""
from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Iterable

logger = logging.getLogger(__name__)

EXCEL_FILE = Path(__file__).resolve().parent.parent.parent / "H1b_US_DataLIst.xlsx"


def _row_to_sponsor(row: tuple) -> dict | None:
    """Pluck the columns we care about from the source spreadsheet row."""
    try:
        # Column order (from the workbook, validated):
        # 0: Line, 1: Fiscal Year, 2: Employer Name, 3: Tax ID,
        # 4: Industry, 5: City, 6: State, 7: Zip,
        # 8: NewApproval, 9: NewDenial,
        # 10: ContApproval, 11: ContDenial,
        # 12: ChangeSameApproval, 13: ChangeSameDenial,
        # 14: NewConcurrentApproval, 15: NewConcurrentDenial,
        # 16: ChangeOfEmployerApproval, 17: ChangeOfEmployerDenial,
        # 18: AmendedApproval, 19: AmendedDenial
        employer = (row[2] or "").strip() if row[2] else ""
        if not employer:
            return None
        fiscal_year = int(row[1]) if str(row[1]).strip().isdigit() else 0
        city = (row[5] or "").strip()
        state = (row[6] or "").strip()
        zip_code = (row[7] or "").strip() if row[7] else ""

        new_a = int(row[8] or 0)
        new_d = int(row[9] or 0)
        cont_a = int(row[10] or 0)
        cont_d = int(row[11] or 0)
        chg_a = int(row[12] or 0) + int(row[14] or 0) + int(row[16] or 0) + int(row[18] or 0)
        chg_d = int(row[13] or 0) + int(row[15] or 0) + int(row[17] or 0) + int(row[19] or 0)

        total = new_a + new_d + cont_a + cont_d + chg_a + chg_d
        if total == 0:
            return None  # skip rows with no activity at all

        seed = f"{employer.lower()}|{city.lower()}|{state.lower()}|{fiscal_year}"
        sponsor_id = hashlib.sha1(seed.encode("utf-8")).hexdigest()[:16]
        return {
            "id": sponsor_id,
            "employer_name": employer,
            "city": city,
            "state": state,
            "zip_code": zip_code,
            "initial_approvals": new_a,
            "initial_denials": new_d,
            "continuing_approvals": cont_a + chg_a,
            "continuing_denials": cont_d + chg_d,
            "total_petitions": total,
            "fiscal_year": fiscal_year,
        }
    except Exception:
        return None


def _iter_rows(path: Path) -> Iterable[tuple]:
    import openpyxl
    wb = openpyxl.load_workbook(str(path), read_only=True, data_only=True)
    ws = wb[wb.sheetnames[0]]
    first = True
    for row in ws.iter_rows(values_only=True):
        if first:
            first = False
            continue
        yield row


async def import_h1b_excel(db, *, file_path: Path = EXCEL_FILE, force: bool = False) -> int:
    """Import the workbook into `h1b_sponsors` (idempotent).

    Args:
      db: SQLiteClient or compatible
      file_path: location of the .xlsx
      force: when False, skip if the table already has rows
    Returns the number of sponsor rows written.
    """
    if not file_path.exists():
        logger.warning(f"H1B Excel not found at {file_path}; skipping import")
        return 0

    if not force:
        try:
            existing = await db.get_h1b_sponsors(limit=1)
            if existing:
                logger.info(f"H1B sponsors already populated; skipping Excel import (force=False)")
                return 0
        except Exception:
            pass

    logger.info(f"H1B: starting import from {file_path.name} ...")

    aggregated: dict[str, dict] = {}
    for row in _iter_rows(file_path):
        sponsor = _row_to_sponsor(row)
        if sponsor is None:
            continue
        sid = sponsor["id"]
        if sid in aggregated:
            agg = aggregated[sid]
            for key in ("initial_approvals", "initial_denials", "continuing_approvals", "continuing_denials", "total_petitions"):
                agg[key] += sponsor[key]
        else:
            aggregated[sid] = sponsor

    sponsors = list(aggregated.values())
    if not sponsors:
        logger.warning("H1B: no usable rows extracted from spreadsheet")
        return 0

    written = await db.upsert_h1b_sponsors(sponsors)
    logger.info(f"H1B: imported {written} sponsor records ({len(sponsors)} unique employers)")
    return written

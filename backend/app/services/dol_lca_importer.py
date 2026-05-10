"""
DOL Foreign Labor Cert (FLC / LCA) Disclosure Data Importer

The U.S. Department of Labor publishes quarterly disclosure data for every
H1B, H2B, PERM, and Prevailing Wage filing in the country. The H-1B file
typically contains 200K+ records per fiscal year and includes hiring-side
contact info that the petitioning employer is REQUIRED to disclose:

  Field                            Use as Contact
  ─────────────────────────────────────────────────────────────────
  EMPLOYER_NAME                  → Contact.company
  EMPLOYER_PHONE                 → Contact.source_payload.phone
  EMPLOYER_POC_LAST_NAME         → Contact.last_name
  EMPLOYER_POC_FIRST_NAME        → Contact.first_name
  EMPLOYER_POC_MIDDLE_NAME       → (combined into name)
  EMPLOYER_POC_JOB_TITLE         → Contact.title
  EMPLOYER_POC_EMAIL             → Contact.email
  AGENT_ATTORNEY_NAME            → secondary contact (immigration attorney)
  AGENT_ATTORNEY_FIRM_NAME       → context
  AGENT_POC_EMPLOYER_PHONE       → contact phone
  AGENT_ATTORNEY_EMAIL_ADDRESS   → secondary email

  WORKSITE_CITY / STATE / ZIP    → location enrichment

This is FREE, OFFICIAL, and covers EVERY active H1B sponsor — they're
legally required to file. Each record is one petition, so we dedupe by
(employer + POC name + email).

Download files from:
  https://www.dol.gov/agencies/eta/foreign-labor/performance

Drop into data/dol_lca/ and call:
  python -c "import asyncio; from app.services.dol_lca_importer import import_lca_csv; \\
             asyncio.run(import_lca_csv('data/dol_lca/H1B_Disclosure_Data_FY2024.csv'))"
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime
from pathlib import Path
from typing import Iterable, Optional

from app.models.contact import (
    Contact,
    ContactConfidence,
    ContactRole,
    ContactSource,
)

logger = logging.getLogger(__name__)


# Column-name normalization — DOL changes capitalization between fiscal years
COLUMN_ALIASES = {
    "employer_name":          ["EMPLOYER_NAME", "EMPLOYER_BUSINESS_NAME"],
    "employer_phone":         ["EMPLOYER_PHONE", "EMPLOYER_PHONE_NUMBER"],
    "employer_country":       ["EMPLOYER_COUNTRY"],
    "employer_state":         ["EMPLOYER_STATE", "EMPLOYER_STATE_PROVINCE"],
    "employer_city":          ["EMPLOYER_CITY"],
    "poc_first_name":         ["EMPLOYER_POC_FIRST_NAME", "EMPLOYER_FIRST_NAME"],
    "poc_last_name":          ["EMPLOYER_POC_LAST_NAME", "EMPLOYER_LAST_NAME"],
    "poc_middle_name":        ["EMPLOYER_POC_MIDDLE_NAME", "EMPLOYER_MIDDLE_NAME"],
    "poc_job_title":          ["EMPLOYER_POC_JOB_TITLE", "EMPLOYER_TITLE"],
    "poc_email":              ["EMPLOYER_POC_EMAIL", "EMPLOYER_EMAIL_ADDRESS", "EMPLOYER_EMAIL"],
    "agent_name":             ["AGENT_ATTORNEY_NAME", "AGENT_ATTORNEY_LAST_NAME"],
    "agent_first":            ["AGENT_ATTORNEY_FIRST_NAME"],
    "agent_email":            ["AGENT_ATTORNEY_EMAIL_ADDRESS", "AGENT_EMAIL_ADDRESS"],
    "agent_firm":             ["AGENT_ATTORNEY_FIRM_NAME", "AGENT_FIRM"],
    "fiscal_year":            ["FISCAL_YEAR", "YEAR"],
}


def _resolve(row: dict, key: str) -> Optional[str]:
    """Look up a logical field across possible DOL column names."""
    for alias in COLUMN_ALIASES.get(key, [key]):
        v = row.get(alias)
        if v is not None and str(v).strip() and str(v).strip().lower() != "nan":
            return str(v).strip()
    return None


def _classify_role(title: Optional[str]) -> ContactRole:
    if not title:
        return ContactRole.OTHER
    t = title.lower()
    if "talent acquisition" in t or "recruit" in t:
        return ContactRole.RECRUITER
    if "head of people" in t or "vp people" in t:
        return ContactRole.HEAD_OF_PEOPLE
    if "engineering manager" in t or "eng manager" in t:
        return ContactRole.ENGINEERING_MANAGER
    if "human resources" in t or t.startswith("hr ") or " hr " in t:
        return ContactRole.TALENT_ACQUISITION
    return ContactRole.OTHER


def _contact_id(company: str, identifier: str) -> str:
    raw = f"dol|{company.lower()}|{identifier.lower()}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _row_to_contacts(row: dict, fiscal_year: Optional[int] = None) -> list[Contact]:
    """Convert one DOL LCA row into 1–2 Contact records (POC + attorney)."""
    employer = _resolve(row, "employer_name")
    if not employer:
        return []

    contacts: list[Contact] = []
    fy = _resolve(row, "fiscal_year") or (str(fiscal_year) if fiscal_year else "")

    # 1) Employer point-of-contact (the actual hiring/HR contact)
    poc_first = _resolve(row, "poc_first_name") or ""
    poc_last = _resolve(row, "poc_last_name") or ""
    poc_middle = _resolve(row, "poc_middle_name") or ""
    poc_email = (_resolve(row, "poc_email") or "").lower() or None
    poc_title = _resolve(row, "poc_job_title")
    poc_phone = _resolve(row, "employer_phone")

    poc_full = " ".join(p for p in (poc_first, poc_middle, poc_last) if p).strip() or None

    if poc_full or poc_email:
        contacts.append(Contact(
            id=_contact_id(employer, f"{poc_full or ''}:{poc_email or ''}"),
            full_name=poc_full,
            first_name=poc_first or None,
            last_name=poc_last or None,
            title=poc_title,
            role=_classify_role(poc_title),
            company=employer,
            email=poc_email,
            source=ContactSource.DOL_LCA,
            confidence=(
                ContactConfidence.VERIFIED if poc_email else ContactConfidence.PATTERN
            ),
            source_payload={
                "fiscal_year": fy,
                "employer_phone": poc_phone,
                "city": _resolve(row, "employer_city"),
                "state": _resolve(row, "employer_state"),
                "filing_type": "H-1B LCA (employer POC)",
            },
            discovered_at=datetime.utcnow(),
        ))

    # 2) Agent / attorney (often immigration counsel, can be useful for outreach)
    agent_first = _resolve(row, "agent_first") or ""
    agent_name = _resolve(row, "agent_name") or ""
    agent_email = (_resolve(row, "agent_email") or "").lower() or None
    agent_firm = _resolve(row, "agent_firm")

    agent_full = " ".join(p for p in (agent_first, agent_name) if p).strip() or None

    if agent_full or agent_email:
        contacts.append(Contact(
            id=_contact_id(employer, f"agent:{agent_full or ''}:{agent_email or ''}"),
            full_name=agent_full,
            first_name=agent_first or None,
            last_name=agent_name or None,
            title=f"Immigration counsel{' (' + agent_firm + ')' if agent_firm else ''}",
            role=ContactRole.OTHER,
            company=employer,
            email=agent_email,
            source=ContactSource.DOL_LCA,
            confidence=(
                ContactConfidence.VERIFIED if agent_email else ContactConfidence.PATTERN
            ),
            source_payload={
                "fiscal_year": fy,
                "agent_firm": agent_firm,
                "filing_type": "H-1B LCA (attorney/agent)",
            },
            discovered_at=datetime.utcnow(),
        ))

    return contacts


async def import_lca_csv(
    file_path: str,
    *,
    db=None,
    fiscal_year: Optional[int] = None,
    chunksize: int = 50_000,
) -> dict:
    """Stream a DOL LCA CSV in chunks, deduping contacts as we go.

    Returns summary dict with row counts and contacts written. Designed to
    handle the 200K+ row annual files without loading everything in memory.
    """
    path = Path(file_path)
    if not path.exists():
        return {"error": f"File not found: {file_path}", "imported": 0}

    try:
        import pandas as pd
    except ImportError:
        return {"error": "pandas not installed", "imported": 0}

    seen_ids: set[str] = set()
    total_rows = 0
    written = 0
    skipped_dupes = 0

    try:
        for chunk in pd.read_csv(
            path,
            chunksize=chunksize,
            low_memory=False,
            encoding="utf-8-sig",
            dtype=str,
            on_bad_lines="skip",
        ):
            batch: list[Contact] = []
            for _, row in chunk.iterrows():
                total_rows += 1
                row_dict = row.to_dict()
                contacts = _row_to_contacts(row_dict, fiscal_year=fiscal_year)
                for c in contacts:
                    if c.id in seen_ids:
                        skipped_dupes += 1
                        continue
                    seen_ids.add(c.id)
                    batch.append(c)

            if batch and db is not None:
                await db.upsert_contacts([c.model_dump(mode="json") for c in batch])
                written += len(batch)

            logger.info(
                "DOL LCA import: chunk done | rows=%s contacts_written=%s dupes=%s",
                total_rows, written, skipped_dupes,
            )
    except Exception as exc:
        logger.error("DOL LCA import failed: %s", exc)
        return {"error": str(exc), "imported": written, "rows_processed": total_rows}

    return {
        "imported": written,
        "rows_processed": total_rows,
        "duplicates_skipped": skipped_dupes,
        "fiscal_year": fiscal_year,
        "file": str(path),
    }


async def get_contacts_for_company(
    employer_name: str,
    *,
    db,
    limit: int = 10,
) -> list[Contact]:
    """Pull pre-imported DOL contacts for a company directly from cache."""
    if db is None:
        return []
    rows = await db.get_contacts(company=employer_name, limit=limit * 3)
    contacts: list[Contact] = []
    for r in rows:
        if (r.get("source") or "").lower() != ContactSource.DOL_LCA.value:
            continue
        try:
            contacts.append(Contact(**r))
        except Exception:
            continue
        if len(contacts) >= limit:
            break
    return contacts

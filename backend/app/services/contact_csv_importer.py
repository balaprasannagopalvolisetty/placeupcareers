"""
PlaceUp Career — Recruiter / People CSV importer.

Ingests a sheet of (first_name, last_name, title, company, profile_url,
email?, phone?) into the `contacts` table as crowdsourced records.

After insert, optionally fans out to FinalScout / Apollo / Hunter to
fill missing emails for rows we have only a LinkedIn URL for. Email
enrichment is bypassed silently when no API key is configured — the
contact still gets stored with the LinkedIn URL.
"""
from __future__ import annotations

import csv
import hashlib
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

logger = logging.getLogger(__name__)

# Strip the "Last Name" garbage column that came from LinkedIn search export.
# We keep only the first space-separated token before any comma.
def _clean_last_name(raw: Optional[str]) -> Optional[str]:
    if not raw:
        return None
    raw = raw.strip().strip('"').strip("-")
    if not raw or raw == "-":
        return None
    # Take everything up to the first comma, then the first word.
    head = raw.split(",", 1)[0].strip()
    first_word = head.split()[0] if head.split() else None
    if not first_word or first_word == "-":
        return None
    return first_word.title()


def _slugify_url(url: Optional[str]) -> Optional[str]:
    if not url:
        return None
    url = url.strip()
    if not url or url == "-":
        return None
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    return url


def _looks_recruiter(title: str) -> bool:
    if not title:
        return False
    t = title.lower()
    return any(kw in t for kw in (
        "recruiter", "talent", "sourcer", "people ops", "people operations",
        "human resources", "hr", "hiring", "tech recruiter", "technical recruiter",
    ))


def _row_to_contact(row: dict) -> Optional[dict]:
    """Map a CSV row to a contact dict suitable for `db.upsert_contacts`."""
    first = (row.get("First Name") or "").strip().strip('"')
    last  = _clean_last_name(row.get("Last Name"))
    title = (row.get("Title") or "").strip().strip('"').strip("-").strip() or None
    company = (row.get("Company") or "").strip().strip('"').strip("-").strip() or None
    email = (row.get("Email") or "").strip().strip('"').strip("-").strip().lower() or None
    phone = (row.get("Phone") or "").strip().strip('"').strip("-").strip() or None
    profile = _slugify_url(row.get("Profile URL"))

    if not (first or last or profile or email):
        return None
    if not company:
        # Without a company we can't usefully match recruiters to jobs;
        # store under a generic bucket so they're searchable, but skip
        # rows that have no anchoring data at all.
        company = "Unknown"

    full_name = " ".join(p for p in (first, last) if p) or None

    seed = "|".join(filter(None, [profile, email, full_name, company])).lower()
    contact_id = hashlib.sha256(("csv|" + seed).encode("utf-8")).hexdigest()[:16]

    return {
        "id": contact_id,
        "full_name": full_name,
        "first_name": first or None,
        "last_name": last,
        "title": title,
        "role": "recruiter" if _looks_recruiter(title or "") else "other",
        "company": company,
        "company_domain": None,
        "email": email,
        "linkedin_url": profile,
        "linkedin_search_url": None,
        "source": "csv_import",
        "confidence": "verified" if (email or profile) else "pattern",
        "related_job_id": None,
        "discovered_at": datetime.now(timezone.utc).isoformat(),
        "last_verified_at": None,
        "source_payload": {"phone": phone, "title": title, "company_raw": company},
    }


async def import_csv(db, file_path: Path, *, max_rows: Optional[int] = None) -> dict:
    """Stream the CSV in and upsert into the `contacts` table.

    Returns counts: rows_seen, rows_imported, rows_skipped.
    """
    file_path = Path(file_path)
    if not file_path.exists():
        return {"rows_seen": 0, "rows_imported": 0, "rows_skipped": 0,
                "error": f"file not found: {file_path}"}

    contacts: list[dict] = []
    seen = 0
    skipped = 0

    with file_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            seen += 1
            if max_rows and seen > max_rows:
                break
            mapped = _row_to_contact(row)
            if mapped is None:
                skipped += 1
                continue
            contacts.append(mapped)

    if not contacts:
        return {"rows_seen": seen, "rows_imported": 0, "rows_skipped": skipped,
                "note": "no usable rows"}

    written = await db.upsert_contacts(contacts)
    logger.info(f"CSV import: wrote {written} contacts ({seen} rows, {skipped} skipped)")
    return {
        "rows_seen": seen,
        "rows_imported": written,
        "rows_skipped": skipped,
        "with_email": sum(1 for c in contacts if c.get("email")),
        "with_linkedin": sum(1 for c in contacts if c.get("linkedin_url")),
    }


async def enrich_missing_emails(db, *, limit: int = 200) -> dict:
    """For contacts that have a LinkedIn URL but no email, try the
    configured enrichment providers in order: FinalScout → Hunter.

    Each successful lookup updates the row in place (same id) so we
    never create duplicates. Skipped silently if no key is configured.
    """
    from app.config import settings

    have_finalscout = bool((settings.finalscout_api_key or "").strip())
    have_hunter = bool((settings.hunter_api_key or "").strip())
    if not (have_finalscout or have_hunter):
        logger.info("Email enrichment skipped: no API keys configured")
        return {"enriched": 0, "note": "no API keys configured"}

    rows = await db.get_contacts(limit=10000)
    candidates = [r for r in rows if r.get("linkedin_url") and not r.get("email")][:limit]
    if not candidates:
        return {"enriched": 0, "candidates_checked": 0, "note": "no candidates"}

    enriched = 0
    fs_calls = 0
    hu_calls = 0

    for c in candidates:
        email = None

        # 1) FinalScout — LinkedIn URL → email (1 credit per call).
        if have_finalscout:
            try:
                from app.services.finalscout_enrichment import find_by_linkedin
                contact_obj = await find_by_linkedin(
                    c["linkedin_url"],
                    enable_personal_email=False,
                    enable_generic_email=False,
                )
                fs_calls += 1
                if contact_obj and contact_obj.email:
                    email = contact_obj.email
            except Exception as exc:
                logger.debug(f"FinalScout lookup failed: {exc}")

        # 2) Hunter fallback — needs a known company DOMAIN + first/last.
        if not email and have_hunter:
            domain = (c.get("company_domain") or "").strip()
            first = (c.get("first_name") or "").strip()
            last = (c.get("last_name") or "").strip()
            if domain and first and last:
                try:
                    from app.services.hunter_enrichment import email_finder
                    contact_obj = await email_finder(
                        domain=domain, first_name=first, last_name=last,
                        company=c.get("company"),
                    )
                    hu_calls += 1
                    if contact_obj and contact_obj.email:
                        email = contact_obj.email
                except Exception as exc:
                    logger.debug(f"Hunter lookup failed: {exc}")

        if email:
            c["email"] = email.lower()
            c["confidence"] = "verified"
            await db.upsert_contacts([c])
            enriched += 1

    return {
        "enriched": enriched,
        "candidates_checked": len(candidates),
        "finalscout_credits_used": fs_calls,
        "hunter_credits_used": hu_calls,
    }

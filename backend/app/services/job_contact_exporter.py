"""Export open jobs matched with company contacts that have usable emails."""

from __future__ import annotations

import csv
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


EXPORT_COLUMNS = [
    "job_id",
    "job_title",
    "job_company",
    "job_location",
    "job_url",
    "contact_name",
    "contact_title",
    "contact_company",
    "contact_email",
    "contact_linkedin_url",
    "contact_source",
    "contact_confidence",
    "match_score",
    "match_reason",
]


BAD_EMAILS = {
    "jubao@lingying.com",
    "privacy@linkedin.com",
    "security@linkedin.com",
    "abuse@linkedin.com",
}

BAD_PREFIXES = (
    "no-reply",
    "noreply",
    "donotreply",
    "do-not-reply",
    "support",
    "privacy",
    "security",
    "abuse",
    "legal",
    "sales",
    "info",
)


SOURCE_SCORE = {
    "finalscout": 100,
    "hunter": 80,
    "apollo": 80,
    "crowdsourced": 70,
    "github": 45,
    "team_page": 25,
}


ROLE_SCORE = {
    "recruiter": 40,
    "talent_acquisition": 40,
    "hiring_manager": 35,
    "head_of_people": 35,
    "engineering_manager": 25,
    "team_lead": 15,
}


def _norm(value: Optional[str]) -> str:
    text = re.sub(r"[^a-z0-9]+", " ", (value or "").lower())
    words = [
        word for word in text.split()
        if word not in {"inc", "llc", "ltd", "corp", "corporation", "company", "co"}
    ]
    return " ".join(words)


def _clean(value) -> str:
    return str(value or "").replace("\r", " ").replace("\n", " ").strip()


def _is_usable_email(contact: dict) -> bool:
    email = (contact.get("email") or "").strip().lower()
    if not email or "@" not in email:
        return False
    if email in BAD_EMAILS:
        return False
    prefix = email.split("@", 1)[0]
    if prefix in BAD_PREFIXES or prefix.startswith(BAD_PREFIXES):
        return False
    return bool(contact.get("full_name") or contact.get("linkedin_url") or contact.get("source") in {"finalscout", "hunter", "apollo"})


def _contact_score(contact: dict, job_company_norm: str) -> tuple[int, str]:
    score = 0
    reasons: list[str] = []

    contact_company_norm = _norm(contact.get("company"))
    if contact_company_norm == job_company_norm:
        score += 60
        reasons.append("company_exact")
    elif job_company_norm and contact_company_norm and (
        job_company_norm in contact_company_norm or contact_company_norm in job_company_norm
    ):
        score += 35
        reasons.append("company_partial")

    source = (contact.get("source") or "").lower()
    source_score = SOURCE_SCORE.get(source, 5)
    score += source_score
    reasons.append(f"source_{source or 'unknown'}")

    role = (contact.get("role") or "").lower()
    role_score = ROLE_SCORE.get(role, 0)
    if role_score:
        score += role_score
        reasons.append(f"role_{role}")

    confidence = (contact.get("confidence") or "").lower()
    if confidence == "verified":
        score += 20
        reasons.append("verified")
    elif confidence == "pattern":
        score += 8
        reasons.append("pattern")

    if contact.get("full_name"):
        score += 10
        reasons.append("named_contact")
    if contact.get("linkedin_url"):
        score += 8
        reasons.append("profile_linked")

    return score, ",".join(reasons)


def _row(job: dict, contact: dict, score: int, reason: str) -> dict:
    return {
        "job_id": _clean(job.get("id")),
        "job_title": _clean(job.get("title")),
        "job_company": _clean(job.get("company")),
        "job_location": _clean(job.get("location")),
        "job_url": _clean(job.get("job_url")),
        "contact_name": _clean(contact.get("full_name")),
        "contact_title": _clean(contact.get("title")),
        "contact_company": _clean(contact.get("company")),
        "contact_email": _clean(contact.get("email")).lower(),
        "contact_linkedin_url": _clean(contact.get("linkedin_url")),
        "contact_source": _clean(contact.get("source")),
        "contact_confidence": _clean(contact.get("confidence")),
        "match_score": score,
        "match_reason": reason,
    }


async def export_job_contact_matches(
    db,
    *,
    contacts_per_job: int = 5,
    min_contacts_per_job: int = 3,
    job_limit: int = 1000,
    output_path: Optional[Path] = None,
) -> dict:
    """Write a CSV of open jobs with 3-5 best available contact emails each."""
    contacts_per_job = max(1, min(5, contacts_per_job))
    min_contacts_per_job = max(0, min(contacts_per_job, min_contacts_per_job))

    jobs = await db.get_jobs(filters={}, limit=job_limit, offset=0)
    jobs = [job for job in jobs if (job.get("status") or "active").lower() == "active"]
    contacts = await db.get_contacts(limit=10000)
    usable_contacts = [contact for contact in contacts if _is_usable_email(contact)]

    contacts_by_company: dict[str, list[dict]] = {}
    for contact in usable_contacts:
        key = _norm(contact.get("company"))
        if key:
            contacts_by_company.setdefault(key, []).append(contact)

    rows: list[dict] = []
    jobs_with_contacts = 0
    jobs_below_min = 0

    for job in jobs:
        job_company_norm = _norm(job.get("company"))
        if not job_company_norm:
            continue

        candidates = list(contacts_by_company.get(job_company_norm, []))
        if not candidates:
            candidates = [
                contact for key, matches in contacts_by_company.items()
                if job_company_norm in key or key in job_company_norm
                for contact in matches
            ]

        scored = []
        seen_emails = set()
        for contact in candidates:
            email = (contact.get("email") or "").strip().lower()
            if email in seen_emails:
                continue
            seen_emails.add(email)
            score, reason = _contact_score(contact, job_company_norm)
            scored.append((score, reason, contact))

        scored.sort(key=lambda item: item[0], reverse=True)
        selected = scored[:contacts_per_job]
        if selected:
            jobs_with_contacts += 1
        if len(selected) < min_contacts_per_job:
            jobs_below_min += 1

        for score, reason, contact in selected:
            rows.append(_row(job, contact, score, reason))

    if output_path is None:
        backend_root = Path(__file__).resolve().parents[2]
        exports_dir = backend_root / "data" / "exports"
        exports_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        output_path = exports_dir / f"job_contact_emails_{timestamp}.csv"
    else:
        output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=EXPORT_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)

    return {
        "output_file": str(output_path),
        "jobs_scanned": len(jobs),
        "contacts_scanned": len(contacts),
        "usable_email_contacts": len(usable_contacts),
        "rows_written": len(rows),
        "jobs_with_contacts": jobs_with_contacts,
        "jobs_below_min_contacts": jobs_below_min,
        "contacts_per_job": contacts_per_job,
        "min_contacts_per_job": min_contacts_per_job,
    }

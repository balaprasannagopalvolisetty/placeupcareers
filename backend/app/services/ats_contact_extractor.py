"""
Free-path Contact Extraction from ATS Metadata

Several ATS platforms publish recruiter / hiring-manager fields directly in
the same public JSON we already use for the job listings:

  Greenhouse  → "metadata" array sometimes contains a {name: "Recruiter",
                value: "jane@stripe.com"} entry; "departments" + "offices"
                give us hints about who's hiring.
  Lever       → "lists" / "applicationLink" / "hiringManager" fields when
                the company has them enabled on their public board.
  Ashby       → "departments" + "team" + "compensation" — generally NO
                public recruiter info.
  Workday     → "bulletFields" sometimes carries a recruiter name.
  Personio    → "subcompany" + "department" hints only.
  SmartRec    → "function" / "industry" hints.
  Recruitee   → "recruiter_id" surfaced; needs lookup.

We harvest whatever IS present and emit Contact records with
ContactSource.ATS_METADATA. Confidence is PATTERN (not VERIFIED) since the
emails we see are usually department aliases (jobs@…, careers@…) rather
than a specific person's verified work email.

This is the zero-cost, zero-risk path — always runs first.
"""

from __future__ import annotations

import hashlib
import logging
import re
from datetime import datetime
from typing import Any, Optional

from app.models.contact import (
    Contact,
    ContactConfidence,
    ContactRole,
    ContactSource,
)
from app.models.job import JobPost
from app.services.google_xray import linkedin_search_url

logger = logging.getLogger(__name__)


EMAIL_REGEX = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")


def _classify_role(label: Optional[str], value: Optional[str] = None) -> ContactRole:
    text = " ".join(s for s in (label, value) if s).lower()
    if not text:
        return ContactRole.OTHER
    if "talent acquisition" in text:
        return ContactRole.TALENT_ACQUISITION
    if "recruit" in text:
        return ContactRole.RECRUITER
    if "engineering manager" in text or "eng manager" in text:
        return ContactRole.ENGINEERING_MANAGER
    if "head of people" in text:
        return ContactRole.HEAD_OF_PEOPLE
    if "team lead" in text or "tech lead" in text:
        return ContactRole.TEAM_LEAD
    if "hiring manager" in text:
        return ContactRole.HIRING_MANAGER
    return ContactRole.OTHER


def _contact_id(company: str, identifier: str) -> str:
    raw = f"ats|{company.lower()}|{identifier.lower()}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _is_personal_email(email: str) -> bool:
    """Filter out clearly generic addresses we don't want to surface."""
    local = email.split("@", 1)[0].lower()
    generic = {
        "info", "contact", "hello", "hr", "careers", "jobs", "recruit",
        "support", "admin", "noreply", "no-reply", "webmaster",
    }
    return local not in generic


def extract_from_jobpost(job: JobPost) -> list[Contact]:
    """Walk a JobPost's extra_metadata and emit any Contact-shaped fields.

    This NEVER calls an external service — it only parses what we already
    pulled from the ATS JSON during scraping.
    """
    contacts: list[Contact] = []
    company = job.company
    extras = job.extra_metadata or {}

    # 1. Greenhouse-style "metadata": list of {name, value} dicts
    gh_meta = extras.get("metadata") or extras.get("greenhouse_metadata") or []
    if isinstance(gh_meta, list):
        for entry in gh_meta:
            if not isinstance(entry, dict):
                continue
            name_label = (entry.get("name") or "").strip()
            value = entry.get("value")
            if isinstance(value, list):
                value = ", ".join(str(v) for v in value)
            if not value or not isinstance(value, str):
                continue
            label_lower = name_label.lower()
            if any(k in label_lower for k in ("recruiter", "hiring manager", "contact email", "talent")):
                emails = EMAIL_REGEX.findall(value)
                if emails:
                    for em in emails:
                        if not _is_personal_email(em):
                            continue
                        contacts.append(Contact(
                            id=_contact_id(company, em),
                            full_name=value if not emails else None,
                            title=name_label,
                            role=_classify_role(name_label, value),
                            company=company,
                            email=em.lower(),
                            source=ContactSource.ATS_METADATA,
                            confidence=ContactConfidence.PATTERN,
                            source_payload={"ats": extras.get("ats", "greenhouse"), "field": name_label},
                            related_job_id=job.id,
                            discovered_at=datetime.utcnow(),
                        ))
                else:
                    # Just a name field — emit as a name-only contact and
                    # generate the LinkedIn search URL for them.
                    contacts.append(Contact(
                        id=_contact_id(company, f"{name_label}:{value}"),
                        full_name=value,
                        title=name_label,
                        role=_classify_role(name_label, value),
                        company=company,
                        linkedin_search_url=linkedin_search_url(company, value),
                        source=ContactSource.ATS_METADATA,
                        confidence=ContactConfidence.UNKNOWN,
                        source_payload={"ats": extras.get("ats", "greenhouse"), "field": name_label},
                        related_job_id=job.id,
                        discovered_at=datetime.utcnow(),
                    ))

    # 2. Lever sometimes exposes hiringManager / list emails
    if extras.get("ats") == "lever":
        lever_lists = extras.get("lists") or []
        if isinstance(lever_lists, list):
            for blk in lever_lists:
                if not isinstance(blk, dict):
                    continue
                content = blk.get("content") or ""
                emails = EMAIL_REGEX.findall(str(content))
                for em in emails:
                    if not _is_personal_email(em):
                        continue
                    contacts.append(Contact(
                        id=_contact_id(company, em),
                        title=blk.get("text") or "Lever public list",
                        role=_classify_role(blk.get("text")),
                        company=company,
                        email=em.lower(),
                        source=ContactSource.ATS_METADATA,
                        confidence=ContactConfidence.PATTERN,
                        source_payload={"ats": "lever", "list_text": blk.get("text")},
                        related_job_id=job.id,
                        discovered_at=datetime.utcnow(),
                    ))

    # 3. Workday bulletFields sometimes carry recruiter names
    if extras.get("ats") == "workday":
        bullets = extras.get("bullet_fields") or []
        if isinstance(bullets, list):
            for b in bullets:
                if not isinstance(b, str):
                    continue
                if "recruiter" in b.lower():
                    contacts.append(Contact(
                        id=_contact_id(company, f"workday-recruiter:{b}"),
                        full_name=b,
                        title="Recruiter (Workday bulletField)",
                        role=ContactRole.RECRUITER,
                        company=company,
                        linkedin_search_url=linkedin_search_url(company, b),
                        source=ContactSource.ATS_METADATA,
                        confidence=ContactConfidence.UNKNOWN,
                        source_payload={"ats": "workday"},
                        related_job_id=job.id,
                        discovered_at=datetime.utcnow(),
                    ))

    # 4. Promote any high-confidence single email to JobPost.hiring_manager_email
    for c in contacts:
        if c.email and not job.hiring_manager_email:
            job.hiring_manager_email = c.email
            job.hiring_manager_name = c.full_name or job.hiring_manager_name
            break

    # 5. Always emit one zero-cost LinkedIn search-link contact for the role
    contacts.append(Contact(
        id=_contact_id(company, f"role-search:{job.title}"),
        title=f"LinkedIn search: {job.title} recruiter @ {company}",
        role=ContactRole.RECRUITER,
        company=company,
        linkedin_search_url=linkedin_search_url(company, f"recruiter {job.title}"),
        source=ContactSource.LINKEDIN_SEARCH_URL,
        confidence=ContactConfidence.UNKNOWN,
        source_payload={"job_title": job.title, "note": "Click to search LinkedIn as yourself."},
        related_job_id=job.id,
        discovered_at=datetime.utcnow(),
    ))

    return contacts

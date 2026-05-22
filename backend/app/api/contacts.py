"""PlaceUp Career - Contacts / Recruiter Discovery API (Free-First, Multi-Tenant)."""
from __future__ import annotations
import hashlib
import logging
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Body, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field

from pathlib import Path

from app.dependencies import get_db
from fastapi.responses import PlainTextResponse
from app.models.contact import (
    Contact, ContactContribution, ContactSearchRequest,
    ContactSource, EnrichmentResult,
)
from app.models.job import JobPost
from app.services.contact_finder import bulk_enrich_jobs, find_contacts
from app.services.email_personalizer import draft_personalized_email
from app.security import current_user_id, require_internal_api_key

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/contacts", tags=["Contacts"])


@router.post("/import-csv")
async def import_recruiter_csv(
    file_path: Optional[str] = Query(
        default=None,
        description="Absolute path or filename inside backend/. Defaults to 'sample user.csv'.",
    ),
    _: None = Depends(require_internal_api_key),
    db=Depends(get_db),
):
    """Ingest a recruiter CSV (First Name, Last Name, Title, Company, Profile URL, …).

    Atomic: each unique (linkedin_url|email|name|company) becomes one
    `contacts` row. Re-running with the same file is a no-op (UNIQUE id).
    """
    from app.services.contact_csv_importer import import_csv

    backend_root = Path(__file__).resolve().parent.parent.parent
    if file_path:
        candidate = Path(file_path)
        if not candidate.is_absolute():
            candidate = backend_root / file_path
    else:
        candidate = backend_root / "sample user.csv"

    if not candidate.exists():
        raise HTTPException(status_code=404, detail=f"CSV not found at {candidate}")

    return await import_csv(db, candidate)


@router.post("/enrich-emails")
async def enrich_recruiter_emails(
    limit: int = Query(default=200, ge=1, le=2000),
    x_finalscout_key: Optional[str] = Header(default=None, alias="X-FinalScout-Key"),
    _: None = Depends(require_internal_api_key),
    db=Depends(get_db),
):
    """For contacts that have a LinkedIn URL but no email, run them through
    FinalScout → Apollo → Hunter to fill the gap. Returns counts."""
    from app.services.contact_csv_importer import enrich_missing_emails

    return await enrich_missing_emails(db, limit=limit, byok_finalscout_key=x_finalscout_key)


@router.post("/import-sample-and-enrich")
async def import_sample_and_enrich(
    limit: int = Query(default=20, ge=1, le=2000),
    x_finalscout_key: Optional[str] = Header(default=None, alias="X-FinalScout-Key"),
    _: None = Depends(require_internal_api_key),
    db=Depends(get_db),
):
    """Import backend/sample user.csv, then run LinkedIn email enrichment."""
    from app.services.contact_csv_importer import enrich_missing_emails, import_csv

    backend_root = Path(__file__).resolve().parent.parent.parent
    csv_result = await import_csv(db, backend_root / "sample user.csv")
    enrich_result = await enrich_missing_emails(db, limit=limit, byok_finalscout_key=x_finalscout_key)
    return {"csv_import": csv_result, "email_enrichment": enrich_result}


@router.get("/debug/finalscout")
async def debug_finalscout(
    linkedin_url: str = Query(..., description="A LinkedIn profile URL to probe"),
    _: None = Depends(require_internal_api_key),
):
    """Probe every plausible FinalScout endpoint + auth-style combination.

    Returns the FIRST 200 response (the real endpoint) plus a summary of
    everything else tried. Use this to discover the live API surface for
    your specific FinalScout plan/account, then update FINALSCOUT_BASE.
    """
    import httpx
    from app.config import settings

    api_key = (settings.finalscout_api_key or "").strip()
    if not api_key:
        raise HTTPException(status_code=400, detail="FINALSCOUT_API_KEY not configured")

    body = {"linkedin_url": linkedin_url, "enable_personal_email": False, "enable_generic_email": False}

    candidates = [
        # Verified live endpoint (locked).
        ("https://api.finalscout.com/v1/find/linkedin/single",  {"Authorization": f"Bearer {api_key}"}, body),
    ]

    attempts: list[dict] = []
    winner: dict | None = None
    async with httpx.AsyncClient(timeout=30.0) as client:
        for url, headers, payload in candidates:
            headers = {**headers, "Content-Type": "application/json"}
            try:
                r = await client.post(url, headers=headers, json=payload)
                snippet = r.text[:300]
                row = {
                    "url": url,
                    "auth": "Bearer" if "Authorization" in headers else "X-API-Key",
                    "status": r.status_code,
                    "body_snippet": snippet,
                }
                attempts.append(row)
                if r.status_code == 200 and winner is None:
                    try:
                        winner = {"url": url, "body": r.json()}
                    except Exception:
                        winner = {"url": url, "body_text": snippet}
            except httpx.HTTPError as exc:
                attempts.append({"url": url, "error": str(exc)[:120]})

    return {
        "winner": winner,
        "attempts": attempts,
        "recommendation": (
            "If 'winner' is set, copy its `url` (without the path) into "
            "FINALSCOUT_BASE in app/services/finalscout_enrichment.py and adjust "
            "the path argument in find_by_linkedin if needed."
        ),
    }


@router.get("/debug/finalscout-account")
async def debug_finalscout_account(_: None = Depends(require_internal_api_key)):
    """Diagnostic: check FinalScout credit balance + plan."""
    import httpx
    from app.config import settings

    api_key = (settings.finalscout_api_key or "").strip()
    if not api_key:
        raise HTTPException(status_code=400, detail="FINALSCOUT_API_KEY not configured")

    async with httpx.AsyncClient(timeout=30.0) as client:
        # Try several documented endpoints — different FS API versions differ.
        for path in ("/account", "/v1/account", "/api/account", "/user/info"):
            r = await client.get(
                f"https://finalscout.com{path}",
                headers={"Authorization": f"Bearer {api_key}"},
            )
            if r.status_code == 200:
                return {"endpoint": path, "body": r.json()}
        return {"error": "no working account endpoint", "last_status": r.status_code, "last_body": r.text[:600]}


class BulkEnrichRequest(BaseModel):
    job_ids: list[str] = Field(default_factory=list)
    company: Optional[str] = None
    max_jobs: int = Field(default=20, ge=1, le=200)
    max_contacts_per_job: int = Field(default=5, ge=1, le=20)
    concurrency: int = Field(default=4, ge=1, le=16)
    use_apollo: bool = False
    use_hunter: bool = False
    use_google_xray: bool = False


@router.post("/enrich", response_model=EnrichmentResult)
async def enrich_contacts(
    request: ContactSearchRequest = Body(...),
    x_apollo_key: Optional[str] = Header(default=None, alias="X-Apollo-Key"),
    x_hunter_key: Optional[str] = Header(default=None, alias="X-Hunter-Key"),
    x_serpapi_key: Optional[str] = Header(default=None, alias="X-SerpAPI-Key"),
    user_id: str = Depends(current_user_id),
    db=Depends(get_db),
):
    """Find recruiter / hiring-manager contacts. Free-first; BYOK headers override platform keys."""
    job: Optional[JobPost] = None
    if request.job_id:
        try:
            row = await db.get_job(request.job_id)
        except Exception:
            row = None
        if not row:
            raise HTTPException(status_code=404, detail=f"Job {request.job_id} not found")
        try:
            job = JobPost(**row)
        except Exception:
            job = None

    company = request.company or (job.company if job else None)
    if not company:
        raise HTTPException(status_code=400, detail="Provide either job_id or company")

    role_query = request.role_query or (job.title if job else None)
    apollo_key = x_apollo_key or request.byok_apollo_key
    hunter_key = x_hunter_key or request.byok_hunter_key
    serpapi_key = x_serpapi_key or request.byok_serpapi_key

    return await find_contacts(
        company=company, role_query=role_query, domain=request.domain, job=job, db=db,
        use_ats_metadata=request.use_ats_metadata, use_dol_lca=request.use_dol_lca,
        use_team_page=request.use_team_page, use_github=request.use_github,
        use_crowdsourced=request.use_crowdsourced,
        use_apollo=request.use_apollo, use_hunter=request.use_hunter,
        use_google_xray=request.use_google_xray,
        byok_apollo_key=apollo_key, byok_hunter_key=hunter_key, byok_serpapi_key=serpapi_key,
        max_contacts=request.max_contacts, force_refresh=request.force_refresh,
    )


@router.post("/bulk-enrich")
async def bulk_enrich(
    request: BulkEnrichRequest = Body(...),
    x_apollo_key: Optional[str] = Header(default=None, alias="X-Apollo-Key"),
    x_hunter_key: Optional[str] = Header(default=None, alias="X-Hunter-Key"),
    x_serpapi_key: Optional[str] = Header(default=None, alias="X-SerpAPI-Key"),
    user_id: str = Depends(current_user_id),
    db=Depends(get_db),
):
    job_rows: list[dict] = []
    if request.job_ids:
        for jid in request.job_ids[: request.max_jobs]:
            row = await db.get_job(jid)
            if row:
                job_rows.append(row)
    elif request.company:
        rows = await db.get_jobs(filters={"search": request.company}, limit=request.max_jobs, offset=0)
        job_rows = [r for r in rows if (r.get("company") or "").lower() == request.company.lower()]
    else:
        raise HTTPException(status_code=400, detail="Provide either job_ids or company")

    jobs: list[JobPost] = []
    for row in job_rows:
        try:
            jobs.append(JobPost(**row))
        except Exception:
            pass

    if not jobs:
        return {"jobs_enriched": 0, "results": {}}

    results = await bulk_enrich_jobs(
        jobs, db=db, max_per_job=request.max_contacts_per_job, concurrency=request.concurrency,
        use_apollo=request.use_apollo, use_hunter=request.use_hunter,
        use_google_xray=request.use_google_xray,
        byok_apollo_key=x_apollo_key, byok_hunter_key=x_hunter_key, byok_serpapi_key=x_serpapi_key,
    )
    return {
        "jobs_enriched": len(results),
        "total_contacts": sum(len(r.contacts) for r in results.values()),
        "results": {jid: r.model_dump(mode="json") for jid, r in results.items()},
    }


@router.post("/contribute", response_model=Contact)
async def contribute_contact(
    payload: ContactContribution = Body(...),
    user_id: str = Depends(current_user_id),
    db=Depends(get_db),
):
    """Submit a verified contact to the crowdsourced pool (shared across all PlaceUp users)."""
    if not payload.company:
        raise HTTPException(status_code=400, detail="company is required")
    if not (payload.email or payload.linkedin_url or payload.full_name):
        raise HTTPException(status_code=400,
            detail="At least one of email / linkedin_url / full_name is required")

    seed = payload.email or payload.linkedin_url or payload.full_name or ""
    raw_id = f"crowd|{payload.company.lower()}|{seed.lower()}"
    contact_id = hashlib.sha256(raw_id.encode("utf-8")).hexdigest()[:16]

    contact = Contact(
        id=contact_id,
        full_name=payload.full_name, title=payload.title, role=payload.role,
        company=payload.company,
        email=(payload.email or "").lower() or None,
        linkedin_url=payload.linkedin_url,
        source=ContactSource.CROWDSOURCED,
        confidence="verified" if (payload.email or payload.linkedin_url) else "pattern",
        source_payload={"submitted_by": payload.submitted_by, "notes": payload.notes},
        discovered_at=datetime.utcnow(),
    )
    await db.upsert_contacts([contact.model_dump(mode="json")])
    return contact


@router.get("", response_model=list[Contact])
async def list_contacts(
    company: Optional[str] = Query(None),
    job_id: Optional[str] = Query(None),
    source: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=500),
    user_id: str = Depends(current_user_id),
    db=Depends(get_db),
):
    fetch_limit = 10000 if source else limit
    rows = await db.get_contacts(company=company, job_id=job_id, limit=fetch_limit)
    if source:
        rows = [r for r in rows if (r.get("source") or "").lower() == source.lower()]
        rows = rows[:limit]
    contacts: list[Contact] = []
    for r in rows:
        try:
            contacts.append(Contact(**r))
        except Exception:
            pass
    return contacts


def _cell(value, width: int) -> str:
    text = str(value or "").replace("\r", " ").replace("\n", " ").strip()
    if len(text) > width:
        text = text[: max(0, width - 1)] + "…"
    return text.ljust(width)


def _contacts_table(rows: list[dict]) -> str:
    columns = [
        ("Name", 24, lambda r: r.get("full_name")),
        ("Email", 34, lambda r: r.get("email")),
        ("Company", 24, lambda r: r.get("company")),
        ("Title", 34, lambda r: r.get("title")),
        ("Source", 16, lambda r: r.get("source")),
        ("Confidence", 10, lambda r: r.get("confidence")),
        ("LinkedIn", 44, lambda r: r.get("linkedin_url") or r.get("linkedin_search_url")),
    ]
    header = " | ".join(_cell(label, width) for label, width, _ in columns)
    divider = "-+-".join("-" * width for _, width, _ in columns)
    body = [
        " | ".join(_cell(accessor(row), width) for _, width, accessor in columns)
        for row in rows
    ]
    if not body:
        body = ["No contacts found."]
    return "\n".join([header, divider, *body])


@router.get("/table", response_class=PlainTextResponse)
async def list_contacts_table(
    company: Optional[str] = Query(None),
    job_id: Optional[str] = Query(None),
    source: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=500),
    user_id: str = Depends(current_user_id),
    db=Depends(get_db),
):
    """Human-readable contacts table for CLI use."""
    fetch_limit = 10000 if source else limit
    rows = await db.get_contacts(company=company, job_id=job_id, limit=fetch_limit)
    if source:
        rows = [r for r in rows if (r.get("source") or "").lower() == source.lower()]
    return _contacts_table(rows[:limit])


@router.post("/export-job-emails")
async def export_job_emails(
    contacts_per_job: int = Query(default=5, ge=1, le=5),
    min_contacts_per_job: int = Query(default=3, ge=0, le=5),
    job_limit: int = Query(default=1000, ge=1, le=10000),
    output_file: Optional[str] = Query(
        default=None,
        description="Optional filename inside backend/data/exports, e.g. job_contact_emails.csv.",
    ),
    _: None = Depends(require_internal_api_key),
    db=Depends(get_db),
):
    """Export open jobs matched with 3-5 best available contact emails per company."""
    from app.services.job_contact_exporter import export_job_contact_matches

    output_path = None
    if output_file:
        backend_root = Path(__file__).resolve().parent.parent.parent
        output_path = backend_root / "data" / "exports" / Path(output_file).name

    return await export_job_contact_matches(
        db,
        contacts_per_job=contacts_per_job,
        min_contacts_per_job=min_contacts_per_job,
        job_limit=job_limit,
        output_path=output_path,
    )


@router.get("/stats")
async def contact_stats(user_id: str = Depends(current_user_id), db=Depends(get_db)):
    total = await db.count_contacts()
    rows = await db.get_contacts(limit=10000)
    by_source: dict[str, int] = {}
    by_confidence: dict[str, int] = {}
    by_company: dict[str, int] = {}
    with_email = 0
    with_linkedin = 0
    for r in rows:
        src = (r.get("source") or "unknown").lower()
        conf = (r.get("confidence") or "unknown").lower()
        comp = r.get("company") or "Unknown"
        by_source[src] = by_source.get(src, 0) + 1
        by_confidence[conf] = by_confidence.get(conf, 0) + 1
        by_company[comp] = by_company.get(comp, 0) + 1
        if r.get("email"): with_email += 1
        if r.get("linkedin_url"): with_linkedin += 1
    top_companies = sorted(by_company.items(), key=lambda kv: kv[1], reverse=True)[:25]
    return {
        "total_contacts": total,
        "with_email": with_email,
        "with_linkedin": with_linkedin,
        "free_source_share": {s: by_source.get(s, 0) for s in
            ("ats_metadata", "dol_lca", "team_page", "github", "crowdsourced", "linkedin_search_url")},
        "paid_source_share": {s: by_source.get(s, 0) for s in ("apollo", "hunter", "finalscout", "google_xray")},
        "by_confidence": by_confidence,
        "top_companies": [{"company": c, "contacts": n} for c, n in top_companies],
    }


class EmailDraftRequest(BaseModel):
    """Request body for POST /api/contacts/draft-email."""
    contact_id: Optional[str] = Field(default=None, description="Use a cached contact")
    contact: Optional[Contact] = Field(default=None, description="Or pass a Contact inline")
    company: str
    position: str = Field(description="Target role title for the outreach")
    candidate_name: str = ""
    candidate_skills: str = ""
    candidate_linkedin: str = ""
    availability: str = "this week"
    subject_template: Optional[str] = None
    body_template: Optional[str] = None
    byok_groq_key: Optional[str] = Field(default=None, description="Override platform Groq key")


@router.post("/draft-email")
async def draft_email_endpoint(
    request: EmailDraftRequest = Body(...),
    x_groq_key: Optional[str] = Header(default=None, alias="X-Groq-Key"),
    user_id: str = Depends(current_user_id),
    db=Depends(get_db),
):
    contact = request.contact
    if not contact and request.contact_id:
        rows = await db.get_contacts(limit=500)
        for r in rows:
            if r.get("id") == request.contact_id:
                try:
                    contact = Contact(**r)
                except Exception:
                    contact = None
                break
    if not contact:
        raise HTTPException(status_code=400, detail="Provide either contact or contact_id (cached)")
    kwargs = {
        "contact": contact, "company": request.company, "position": request.position,
        "candidate_name": request.candidate_name, "candidate_skills": request.candidate_skills,
        "candidate_linkedin": request.candidate_linkedin, "availability": request.availability,
        "byok_groq_key": x_groq_key or request.byok_groq_key,
    }
    if request.subject_template: kwargs["subject_template"] = request.subject_template
    if request.body_template: kwargs["body_template"] = request.body_template
    return await draft_personalized_email(**kwargs)

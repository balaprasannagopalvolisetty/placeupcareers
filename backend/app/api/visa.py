"""
PlaceUp Career — Visa & H1B API Routes.

Powers the Visa Tracker page: aggregate dashboard + paginated/searchable
sponsor list (backed by the H1B Excel import) + per-employer lookups.
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.dependencies import get_db
from app.models.visa import (
    H1BSearchResponse, H1BSponsor, H1BSalaryData,
    VisaClassifyRequest, VisaScore,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/visa", tags=["Visa & H1B"])


def _sponsor_row_to_card(r: dict) -> dict:
    initial_a = int(r.get("initial_approvals") or 0)
    initial_d = int(r.get("initial_denials") or 0)
    cont_a = int(r.get("continuing_approvals") or 0)
    cont_d = int(r.get("continuing_denials") or 0)
    approvals = initial_a + cont_a
    denials = initial_d + cont_d
    total = approvals + denials
    rate = round((approvals / total) * 100) if total else 0
    return {
        "employer": r.get("employer_name") or "Unknown",
        "city": r.get("city") or "",
        "state": r.get("state") or "",
        "type": "H-1B",
        "fiscal_year": r.get("fiscal_year") or 0,
        "approvals": approvals,
        "new_approvals": initial_a,
        "continuing_approvals": cont_a,
        "denials": denials,
        "rate": rate,
        "status": "Active" if approvals > 0 else "Inactive",
        "total_petitions": int(r.get("total_petitions") or total),
    }


@router.get("/dashboard")
async def get_visa_dashboard(db=Depends(get_db)):
    """Aggregate sponsorship dashboard view: top sponsors + headline stats."""
    try:
        rows = await db.get_h1b_sponsors(limit=200)
    except Exception:
        rows = []

    sponsors = [_sponsor_row_to_card(r) for r in rows]
    sponsors.sort(key=lambda s: s["approvals"], reverse=True)
    sponsors = sponsors[:25]

    total_approvals = sum(s["approvals"] for s in sponsors)
    total_denials = sum(s["denials"] for s in sponsors)
    total = total_approvals + total_denials
    avg_rate = round((total_approvals / total) * 100) if total else 0

    try:
        all_count = len(await db.get_h1b_sponsors(limit=100000))
    except Exception:
        all_count = len(sponsors)

    return {
        "stats": {
            "h1b_sponsors": f"{all_count:,}+",
            "opt_roles": "15K+",
            "avg_approval_rate": f"{avg_rate}%",
            "petitions_last_year": f"{total_approvals + total_denials:,}+",
        },
        "sponsors": sponsors,
    }


@router.get("/sponsors")
async def list_visa_sponsors(
    company: Optional[str] = Query(None, description="Filter by company name (substring match)"),
    state: Optional[str] = Query(None, description="Filter by state code"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    db=Depends(get_db),
):
    """Searchable sponsor directory backed by the H1B Excel import."""
    try:
        # The store's `get_h1b_sponsors` already supports an `employer` ILIKE-ish filter.
        all_rows = await db.get_h1b_sponsors(employer=company, limit=100000)
    except Exception as e:
        logger.error(f"Sponsor search failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    if state:
        all_rows = [r for r in all_rows if (r.get("state") or "").lower() == state.lower()]

    total = len(all_rows)
    start = (page - 1) * page_size
    end = start + page_size
    sponsors = [_sponsor_row_to_card(r) for r in all_rows[start:end]]
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": max(1, (total + page_size - 1) // page_size),
        "sponsors": sponsors,
    }


@router.get("/h1b/{employer}")
async def get_h1b_employer_data(employer: str, db=Depends(get_db)):
    """All H1B records we have for a single employer (case-insensitive)."""
    try:
        rows = await db.get_h1b_sponsors(employer=employer, limit=200)
    except Exception as e:
        logger.error(f"H1B employer lookup failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    if not rows:
        return {"employer": employer, "records": [], "total_petitions": 0}

    cards = [_sponsor_row_to_card(r) for r in rows]
    return {
        "employer": employer,
        "records": cards,
        "total_petitions": sum(c["total_petitions"] for c in cards),
        "total_approvals": sum(c["approvals"] for c in cards),
        "total_denials": sum(c["denials"] for c in cards),
    }


@router.get("/search", response_model=H1BSearchResponse)
async def search_h1b_data(
    employer: Optional[str] = Query(None),
    job_title: Optional[str] = Query(None),
    city: Optional[str] = Query(None),
    year: int = Query(2024),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db=Depends(get_db),
):
    """Combined sponsor + salary search (delegates to live h1b_data scrapers)."""
    if not employer and not job_title and not city:
        raise HTTPException(
            status_code=400,
            detail="At least one of employer / job_title / city is required.",
        )
    try:
        from app.services.h1b_data import search_h1b_salaries, search_visa_sponsors
        salary_data = await search_h1b_salaries(employer=employer, job_title=job_title, city=city, year=year)
        sponsor_data = []
        if employer:
            sponsor_data = await search_visa_sponsors(company=employer)
        total = len(salary_data) + len(sponsor_data)
        return H1BSearchResponse(
            sponsors=sponsor_data[:page_size],
            salary_data=salary_data[:page_size],
            total=total, page=page, page_size=page_size,
        )
    except Exception as e:
        logger.error(f"H1B search failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/classify", response_model=VisaScore)
async def classify_job_visa(request: VisaClassifyRequest):
    try:
        from app.services.visa_classifier import classify_job
        return classify_job(title=request.title, company=request.company, description=request.description)
    except Exception as e:
        logger.error(f"Visa classification failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/salary")
async def get_h1b_salary_data(
    job_title: str = Query(...),
    location: Optional[str] = Query(None),
    year: int = Query(2024),
):
    try:
        from app.services.h1b_data import search_h1b_salaries
        results = await search_h1b_salaries(job_title=job_title, city=location, year=year)
        salaries = [r.base_salary for r in results if r.base_salary]
        stats = {}
        if salaries:
            stats = {
                "min_salary": min(salaries),
                "max_salary": max(salaries),
                "avg_salary": round(sum(salaries) / len(salaries), 0),
                "median_salary": sorted(salaries)[len(salaries) // 2],
                "sample_size": len(salaries),
            }
        return {
            "job_title": job_title,
            "location": location,
            "year": year,
            "statistics": stats,
            "records": [r.model_dump() for r in results[:50]],
            "total_records": len(results),
        }
    except Exception as e:
        logger.error(f"H1B salary lookup failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

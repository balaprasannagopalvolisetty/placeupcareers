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
from app.services.global_visa_rules import COUNTRY_RULES, normalize_country_code

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/visa", tags=["Visa & H1B"])


OFFICIAL_SPONSOR_SOURCES = {
    "US": {"name": "USCIS H-1B Employer Data Hub / DOL LCA", "url": "https://www.uscis.gov/tools/reports-and-studies/h-1b-employer-data-hub", "route": "H-1B"},
    "GB": {"name": "GOV.UK Register of licensed sponsors: workers", "url": "https://www.gov.uk/government/publications/register-of-licensed-sponsors-workers", "route": "Skilled Worker"},
    "NL": {"name": "IND Public Register Recognised Sponsors", "url": "https://ind.nl/en/public-register-recognised-sponsors/public-register-work", "route": "Highly Skilled Migrant"},
    "NZ": {"name": "Immigration New Zealand accredited employer check", "url": "https://www.immigration.govt.nz/new-zealand-visas/preparing-a-visa-application/working-in-nz/check-if-an-employer-is-accredited", "route": "AEWV"},
    "IE": {"name": "Ireland Employment Permit Statistics", "url": "https://www.gov.ie/en/department-of-enterprise-tourism-and-employment/collections/employment-permit-statistics/", "route": "Critical Skills / General Employment Permit"},
    "CA": {"name": "Government of Canada positive LMIA employer data", "url": "https://open.canada.ca/data/en/dataset/90fed587-1364-4f33-a9ee-208181dc0b97", "route": "LMIA Work Permit"},
    "SG": {"name": "Singapore MOM Employment Pass", "url": "https://www.mom.gov.sg/passes-and-permits/employment-pass", "route": "Employment Pass"},
    "AU": {"name": "Australian sponsor sanctions and sponsorship obligations", "url": "https://www.abf.gov.au/about-us/what-we-do/sponsor-sanctions/register-of-sanctioned-sponsors", "route": "Skills in Demand / ENS"},
}


def _sponsor_row_to_card(r: dict) -> dict:
    meta = r.get("data_json") or {}
    if not isinstance(meta, dict):
        meta = {}
    city = r.get("city") or meta.get("city") or meta.get("location_city") or ""
    state = r.get("state") or meta.get("state") or meta.get("location_state") or ""
    fy = r.get("fiscal_year") or meta.get("fiscal_year") or meta.get("fy") or 0
    initial_a = int(r.get("initial_approvals") or meta.get("initial_approvals") or meta.get("approvals") or 0)
    initial_d = int(r.get("initial_denials") or meta.get("initial_denials") or meta.get("denials") or 0)
    cont_a = int(r.get("continuing_approvals") or meta.get("continuing_approvals") or 0)
    cont_d = int(r.get("continuing_denials") or meta.get("continuing_denials") or 0)
    approvals = initial_a + cont_a
    denials = initial_d + cont_d
    total_petitions = int(r.get("total_petitions") or meta.get("total_petitions") or 0)
    if approvals == 0 and denials == 0 and total_petitions > 0:
        approvals = total_petitions
    total = approvals + denials
    rate = round((approvals / total) * 100) if total else 0
    location = ", ".join(part for part in (city, state) if part) or "Remote / Multiple"
    return {
        "employer": r.get("employer_name") or "Unknown",
        "city": city,
        "state": state,
        "location": location,
        "type": "H-1B",
        "fiscal_year": fy,
        "fy": fy,
        "approvals": approvals,
        "approval": approvals,
        "new_approvals": initial_a,
        "continuing_approvals": cont_a,
        "denials": denials,
        "denial": denials,
        "rate": rate,
        "approval_rate": rate,
        "status": "Active" if approvals > 0 or total_petitions > 0 else "Inactive",
        "total_petitions": total_petitions or total,
    }


def _global_sponsor_row_to_card(r: dict) -> dict:
    approvals = int(r.get("approvals") or 0)
    denials = int(r.get("denials") or 0)
    total_petitions = int(r.get("total_petitions") or approvals + denials or 0)
    total = approvals + denials
    rate = round((approvals / total) * 100) if total else (100 if approvals or total_petitions else 0)
    city = r.get("city") or ""
    region = r.get("region") or ""
    location = ", ".join(part for part in (city, region) if part) or r.get("country_name") or "Multiple"
    return {
        "employer": r.get("employer_name") or "Unknown",
        "city": city or location,
        "state": region,
        "location": location,
        "type": r.get("visa_route") or "Work visa",
        "country": r.get("country"),
        "country_name": r.get("country_name"),
        "source": r.get("source_name"),
        "source_url": r.get("source_url"),
        "fiscal_year": int(r.get("fiscal_year") or 0),
        "fy": int(r.get("fiscal_year") or 0),
        "approvals": approvals,
        "approval": approvals,
        "new_approvals": approvals,
        "continuing_approvals": 0,
        "denials": denials,
        "denial": denials,
        "rate": rate,
        "approval_rate": rate,
        "status": r.get("status") or "Active",
        "total_petitions": total_petitions,
    }


@router.get("/dashboard")
async def get_visa_dashboard(db=Depends(get_db)):
    """Aggregate sponsorship dashboard view: top sponsors + headline stats."""
    try:
        global_rows = await db.get_visa_sponsors(limit=100000) if hasattr(db, "get_visa_sponsors") else []
    except Exception:
        global_rows = []
    try:
        rows = await db.get_h1b_sponsors(limit=100000)
    except Exception:
        rows = []

    all_sponsors = [_global_sponsor_row_to_card(r) for r in global_rows] or [_sponsor_row_to_card(r) for r in rows]
    active_sponsors = [s for s in all_sponsors if (s["approvals"] + s["denials"]) > 0]
    active_sponsors.sort(key=lambda s: (s["approvals"], s["total_petitions"]), reverse=True)
    sponsors = active_sponsors[:25]

    latest_year = max((s["fiscal_year"] for s in active_sponsors), default=0)
    latest_year_sponsors = [
        s for s in active_sponsors if latest_year and s["fiscal_year"] == latest_year
    ] or active_sponsors
    total_approvals = sum(s["approvals"] for s in latest_year_sponsors)
    total_denials = sum(s["denials"] for s in latest_year_sponsors)
    total = total_approvals + total_denials
    avg_rate = round((total_approvals / total) * 100) if total else 0

    try:
        visa_jobs = await db.count_jobs({"visa_only": True})
    except Exception:
        visa_jobs = 0

    return {
        "stats": {
            "h1b_sponsors": f"{len(all_sponsors):,}+",
            "opt_roles": f"{visa_jobs:,}",
            "avg_approval_rate": f"{avg_rate}%",
            "petitions_last_year": f"{total_approvals + total_denials:,}+",
        },
        "sponsors": sponsors,
    }


@router.get("/sponsors")
async def list_visa_sponsors(
    company: Optional[str] = Query(None, description="Filter by company name (substring match)"),
    state: Optional[str] = Query(None, description="Filter by state code"),
    country: Optional[str] = Query("US", description="Country code. US uses imported H-1B employer records; other countries return official source metadata until imported."),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    db=Depends(get_db),
):
    """Searchable sponsor directory backed by the H1B Excel import."""
    country_code = normalize_country_code(country) or "US"
    official_source = OFFICIAL_SPONSOR_SOURCES.get(country_code)
    if hasattr(db, "get_visa_sponsors"):
        try:
            total = await db.count_visa_sponsors(country=country_code, employer=company, region=state)
            if total:
                offset = (page - 1) * page_size
                rows = await db.get_visa_sponsors(
                    country=country_code,
                    employer=company,
                    region=state,
                    limit=page_size,
                    offset=offset,
                )
                return {
                    "total": total,
                    "page": page,
                    "page_size": page_size,
                    "total_pages": max(1, (total + page_size - 1) // page_size),
                    "country": country_code,
                    "country_name": COUNTRY_RULES.get(country_code).name if COUNTRY_RULES.get(country_code) else country_code,
                    "official_source": official_source,
                    "sponsors": [_global_sponsor_row_to_card(r) for r in rows],
                }
        except Exception as e:
            logger.warning("Global visa sponsor lookup failed for %s: %s", country_code, e)

    if country_code != "US":
        rule = COUNTRY_RULES.get(country_code)
        source = official_source or {
            "name": f"{rule.name if rule else country_code} official immigration sponsor source",
            "url": "",
            "route": ", ".join(program.name for program in (rule.programs if rule else ())) or "Work visa",
        }
        return {
            "total": 0,
            "page": page,
            "page_size": page_size,
            "total_pages": 1,
            "country": country_code,
            "country_name": rule.name if rule else country_code,
            "official_source": source,
            "sponsors": [],
            "message": "Official country sponsor source is ready. Company-level import for this country is pending.",
        }
    try:
        total = await db.count_h1b_sponsors(employer=company, state=state)
        offset = (page - 1) * page_size
        rows = await db.get_h1b_sponsors(employer=company, state=state, limit=page_size, offset=offset)
    except Exception as e:
        logger.error(f"Sponsor search failed: {e}")
        raise HTTPException(status_code=500, detail="Sponsor search failed")

    sponsors = [_sponsor_row_to_card(r) for r in rows]
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": max(1, (total + page_size - 1) // page_size),
        "country": country_code,
        "official_source": official_source,
        "sponsors": sponsors,
    }


@router.get("/h1b/{employer}")
async def get_h1b_employer_data(employer: str, db=Depends(get_db)):
    """All H1B records we have for a single employer (case-insensitive)."""
    try:
        rows = await db.get_h1b_sponsors(employer=employer, limit=200)
    except Exception as e:
        logger.error(f"H1B employer lookup failed: {e}")
        raise HTTPException(status_code=500, detail="H1B employer lookup failed")

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
        raise HTTPException(status_code=500, detail="H1B search failed")


@router.post("/classify", response_model=VisaScore)
async def classify_job_visa(request: VisaClassifyRequest):
    try:
        from app.services.visa_classifier import classify_job
        return classify_job(title=request.title, company=request.company, description=request.description)
    except Exception as e:
        logger.error(f"Visa classification failed: {e}")
        raise HTTPException(status_code=500, detail="Visa classification failed")


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
        raise HTTPException(status_code=500, detail="H1B salary lookup failed")

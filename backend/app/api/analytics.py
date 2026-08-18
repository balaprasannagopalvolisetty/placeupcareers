"""
Market analytics — REAL data only, no synthetic series.

The /analytics/dashboard endpoint and its page were removed; only the
/analytics/market endpoint remains (it powers the Overview market widget).
"""
import hashlib
import json
from typing import Optional

from fastapi import APIRouter, Depends, Query

from app.db import user_store
from app.dependencies import get_db
from app.security import optional_user_id
from app.services.global_visa_rules import normalize_country_code, resolve_country

router = APIRouter(prefix="/analytics", tags=["Analytics"])


def _target_country_from_user(user_id: Optional[str], explicit_country: Optional[str]) -> Optional[str]:
    if explicit_country:
        return normalize_country_code(explicit_country)
    if not user_id:
        return None
    try:
        prefs = user_store.get_preferences(user_id)
        for location in prefs.get("target_locations") or []:
            country = resolve_country(str(location))
            if country:
                return country
        user = user_store.get_user_by_id(user_id) or {}
        return normalize_country_code(user.get("country")) or resolve_country(user.get("location"))
    except Exception:
        return None


def _market_where(title_terms: list[str], country: Optional[str]) -> tuple[str, dict]:
    clauses = ["status = 'active'"]
    params: dict[str, object] = {}
    if country:
        clauses.append("upper(country) = :country")
        params["country"] = country.upper()
    terms = [str(term).strip() for term in title_terms if str(term).strip()][:60]
    if terms:
        ors: list[str] = []
        for idx, term in enumerate(terms):
            key = f"term{idx}"
            ors.append(f"title ILIKE :{key}")
            params[key] = f"%{term}%"
        clauses.append("(" + " OR ".join(ors) + ")")
    return " AND ".join(clauses), params


@router.get("/market")
async def get_market_analytics(
    target_roles: bool = Query(True, description="Limit analytics to the signed-in user's saved target roles when available."),
    country: Optional[str] = Query(None, description="Optional destination country ISO code."),
    user_id: Optional[str] = Depends(optional_user_id),
    db=Depends(get_db),
):
    """Live job-market analytics straight from the jobs database.

    Cached per target profile so the dashboard can show a fast, honest count of
    open positions for the user's saved roles instead of one global market total.
    """
    from app.services.cache import cache_get_json, cache_set_json

    preferred_roles: list[str] = []
    title_terms: list[str] = []
    if user_id and target_roles:
        try:
            prefs = user_store.get_preferences(user_id)
            preferred_roles = [str(r).strip() for r in (prefs.get("target_roles") or []) if str(r).strip()][:12]
            if preferred_roles:
                from app.api.jobs import _terms_for_role_names

                title_terms = _terms_for_role_names([role.lower() for role in preferred_roles])
        except Exception:
            preferred_roles = []
            title_terms = []

    target_country = _target_country_from_user(user_id, country)
    count_filters: dict = {"status": "active"}
    if title_terms:
        count_filters["title_terms"] = title_terms
    if target_country:
        count_filters["country"] = target_country

    key_payload = {"roles": preferred_roles, "terms": title_terms, "country": target_country, "target_roles": target_roles}
    cache_hash = hashlib.sha1(json.dumps(key_payload, sort_keys=True).encode("utf-8")).hexdigest()[:16]
    cached = cache_get_json(f"analytics:market:v2:{cache_hash}")
    if cached is not None:
        return cached

    out: dict = {
        "total_active": 0,
        "added_series": [],
        "by_country": [],
        "by_source": [],
        "targeted": bool(title_terms or target_country),
        "target_roles": preferred_roles,
        "target_country": target_country,
    }
    try:
        out["total_active"] = await db.count_jobs(filters=count_filters)
    except Exception:
        pass
    try:
        out["added_series"] = await db.jobs_added_daily(days=14, title_terms=title_terms or None)
    except Exception:
        pass
    try:
        from sqlalchemy import text

        table = "master_jobs" if getattr(db, "_master_jobs_available", lambda: False)() else "jobs"
        where, params = _market_where(title_terms, target_country)
        with db.session() as s:
            country_rows = s.execute(text(
                f"SELECT COALESCE(NULLIF(country, ''), 'Other') AS k, COUNT(*) AS c "
                f"FROM {table} WHERE {where} GROUP BY 1 ORDER BY c DESC LIMIT 8"
            ), params).mappings().all()
            out["by_country"] = [{"key": r["k"], "count": int(r["c"])} for r in country_rows]
            source_rows = s.execute(text(
                f"SELECT COALESCE(NULLIF(source_name, ''), 'Other') AS k, COUNT(*) AS c "
                f"FROM {table} WHERE {where} GROUP BY 1 ORDER BY c DESC LIMIT 8"
            ), params).mappings().all()
            out["by_source"] = [{"key": r["k"], "count": int(r["c"])} for r in source_rows]
    except Exception:
        pass
    cache_set_json(f"analytics:market:v2:{cache_hash}", out, ttl=120)
    return out

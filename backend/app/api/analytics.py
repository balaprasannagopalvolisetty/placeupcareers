"""
Analytics dashboard — REAL data only, no synthetic series.

Pulls per-user counts from the SQLite store. Returns empty arrays when
the user hasn't applied or uploaded resumes yet — the frontend handles
the empty state gracefully.
"""
import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query

from app.db import user_store
from app.dependencies import get_db
from app.models.analytics import (
    AnalyticsDashboard,
    MetricCard,
    ScorePoint,
    TimeSeriesPoint,
)
from app.security import optional_user_id
from app.services.global_visa_rules import normalize_country_code, resolve_country

router = APIRouter(prefix="/analytics", tags=["Analytics"])


@router.get("/dashboard", response_model=AnalyticsDashboard)
async def get_analytics_dashboard(user_id: Optional[str] = Depends(optional_user_id)):
    apps_total = 0
    top_resume_score = 0
    score_history: list[ScorePoint] = []
    applications_over_time: list[TimeSeriesPoint] = []

    if user_id:
        try:
            applications = user_store.list_user_applications(user_id)
            apps_total = len(applications)
            today = datetime.now(tz=timezone.utc).date()
            buckets: list[dict] = []
            for i in range(13, -1, -1):
                day = today - timedelta(days=i)
                buckets.append({"date": day, "apps": 0, "interviews": 0, "matches": 0})
            by_key = {b["date"].isoformat(): b for b in buckets}
            for row in applications:
                applied_ts = row.get("created_at") or row.get("updated_at")
                heard_ts = row.get("updated_at") or row.get("created_at")
                if row.get("status") == "applied" and applied_ts:
                    key = str(applied_ts)[:10]
                    if key in by_key:
                        by_key[key]["apps"] += 1
                if (row.get("status") == "interview" or row.get("heard_back") is True) and heard_ts:
                    key = str(heard_ts)[:10]
                    if key in by_key:
                        by_key[key]["interviews"] += 1
                if int(row.get("match_score") or 0) > 0 and applied_ts:
                    key = str(applied_ts)[:10]
                    if key in by_key:
                        by_key[key]["matches"] += 1
            applications_over_time = [
                TimeSeriesPoint(
                    month=b["date"].strftime("%b %d"),
                    apps=b["apps"],
                    interviews=b["interviews"],
                    matches=b["matches"],
                )
                for b in buckets
                if b["apps"] or b["interviews"] or b["matches"]
            ]
        except Exception:
            apps_total = 0
        try:
            resumes = sorted(
                user_store.list_resumes(user_id),
                key=lambda r: r.get("uploaded_at") or "",
            )
            for idx, r in enumerate(resumes, start=1):
                score_history.append(ScorePoint(version=f"v{idx}", score=int(r.get("score") or 0)))
            if resumes:
                top_resume_score = max(int(r.get("score") or 0) for r in resumes)
        except Exception:
            pass

    metrics = [
        MetricCard(label="Applications", value=str(apps_total), trend=""),
        MetricCard(label="Profile Views", value="0", trend=""),
        MetricCard(label="Resume Downloads", value="0", trend=""),
        MetricCard(
            label="Top Resume Score",
            value=f"{top_resume_score}%" if top_resume_score else "—",
            trend="Best ATS score" if top_resume_score else "Upload a resume to see your score",
        ),
    ]

    return AnalyticsDashboard(
        metrics=metrics,
        applications_over_time=applications_over_time,
        ats_score_history=score_history,
    )


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

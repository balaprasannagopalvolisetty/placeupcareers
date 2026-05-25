"""
Analytics dashboard — REAL data only, no synthetic series.

Pulls per-user counts from the SQLite store. Returns empty arrays when
the user hasn't applied or uploaded resumes yet — the frontend handles
the empty state gracefully.
"""
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends

from app.db import user_store
from app.models.analytics import (
    AnalyticsDashboard,
    MetricCard,
    ScorePoint,
    TimeSeriesPoint,
)
from app.security import optional_user_id

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

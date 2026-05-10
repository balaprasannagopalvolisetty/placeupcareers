"""
Analytics dashboard — REAL data only, no synthetic series.

Pulls per-user counts from the SQLite store. Returns empty arrays when
the user hasn't applied or uploaded resumes yet — the frontend handles
the empty state gracefully.
"""
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

    if user_id:
        try:
            apps_total = user_store.count_user_applications(user_id)
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
        applications_over_time=[],   # populated when user_applications start tracking timestamps
        ats_score_history=score_history,
    )

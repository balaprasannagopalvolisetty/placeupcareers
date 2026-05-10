from pydantic import BaseModel


class MetricCard(BaseModel):
    label: str
    value: str
    trend: str


class TimeSeriesPoint(BaseModel):
    month: str
    apps: int
    interviews: int
    matches: int


class ScorePoint(BaseModel):
    version: str
    score: int


class AnalyticsDashboard(BaseModel):
    metrics: list[MetricCard]
    applications_over_time: list[TimeSeriesPoint]
    ats_score_history: list[ScorePoint]

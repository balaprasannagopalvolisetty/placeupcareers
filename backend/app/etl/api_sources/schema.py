from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field


SponsorSignal = Literal["confirmed", "likely", "unknown"] | None


class NormalizedJob(BaseModel):
    job_id: str
    source: str
    source_job_id: str
    title: str
    company: str
    location: str
    country: str
    remote: bool = False
    url: str
    description: str = ""
    posted_date: str | None = None
    salary_min: float | None = None
    salary_max: float | None = None
    raw_tags: list[str] = Field(default_factory=list)
    sponsor_signal: SponsorSignal = None
    ingested_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    raw: dict[str, Any] = Field(default_factory=dict, exclude=True)


class FetchParams(BaseModel):
    query: str
    country: str = "US"
    page: int = 1
    per_page: int = 50


def stable_job_id(source: str, source_job_id: str) -> str:
    raw = f"{source}|{source_job_id}".strip().lower()
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def iso_or_none(value: Any) -> str | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    text = str(value).strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(timezone.utc).isoformat()
    except ValueError:
        return text


def clean_text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()

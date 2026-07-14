"""PlaceUp Career - Health Check API."""

from datetime import datetime, timezone
import logging
import os

from fastapi import APIRouter, HTTPException, Query

router = APIRouter(tags=["Health"])
logger = logging.getLogger(__name__)


@router.get("/health")
async def health_check():
    """Minimal public health response for uptime checks."""
    return {
        "status": "ok",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/health/ats-coverage")
async def ats_coverage(hours: int = Query(24, ge=1, le=720)):
    """At-a-glance scraper supply mix: first-party ATS boards vs LinkedIn/
    Indeed/Dice aggregators over a rolling window.

    Use this to confirm the scraper is actually collecting ATS-portal jobs
    (not just aggregators) and to watch the One-Click Apply feed's supply. A
    healthy platform keeps a real, non-trivial first-party share.
    """
    from app.db.postgres import PostgresClient
    from app.scrape_constants import AGGREGATOR_SOURCES, FIRST_PARTY_ATS_SOURCES

    try:
        rows = PostgresClient().source_coverage_sync(hours=hours)
    except Exception as exc:  # pragma: no cover - DB may be unavailable
        logger.warning("ATS coverage query failed: %s", exc)
        raise HTTPException(status_code=503, detail="ATS coverage is temporarily unavailable") from exc

    buckets = {"first_party_ats": 0, "aggregator": 0, "other": 0}
    per_source = []
    for row in rows:
        source = str(row.get("source") or "unknown").lower()
        count = int(row.get("count") or 0)
        if source in FIRST_PARTY_ATS_SOURCES:
            bucket = "first_party_ats"
        elif source in AGGREGATOR_SOURCES:
            bucket = "aggregator"
        else:
            bucket = "other"
        buckets[bucket] += count
        per_source.append({"source": source, "count": count, "bucket": bucket})

    per_source.sort(key=lambda item: item["count"], reverse=True)
    total = sum(buckets.values())
    first_party_share = round(buckets["first_party_ats"] / total, 4) if total else 0.0
    try:
        minimum_share = max(0.0, min(1.0, float(os.getenv("ATS_COVERAGE_MIN_FIRST_PARTY_SHARE", "0.05"))))
    except ValueError:
        minimum_share = 0.05
    direct_ats_healthy = buckets["first_party_ats"] > 0 and first_party_share >= minimum_share

    def _pct(part: int) -> float:
        return round(100 * part / total, 1) if total else 0.0

    return {
        "status": "ok",
        "window_hours": hours,
        "total_active_jobs": total,
        "counts": buckets,
        "percent": {
            "first_party_ats": _pct(buckets["first_party_ats"]),
            "aggregator": _pct(buckets["aggregator"]),
            "other": _pct(buckets["other"]),
        },
        "first_party_share": first_party_share,
        "minimum_first_party_share": minimum_share,
        "supply_status": "healthy" if direct_ats_healthy else "degraded",
        "direct_ats_healthy": direct_ats_healthy,
        "by_source": per_source,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

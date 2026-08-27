"""Helpers for recording ETL run lifecycle and metrics."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.db.schema import IngestRun


def start_ingest_run(db: Session, *, source_name: str, pipeline_name: str, schedule_type: str) -> IngestRun:
    run = IngestRun(
        source_name=source_name,
        pipeline_name=pipeline_name,
        schedule_type=schedule_type,
        status="running",
    )
    db.add(run)
    db.flush()
    return run


def finish_ingest_run(
    db: Session,
    run: IngestRun,
    *,
    status: str,
    records_seen: int = 0,
    records_staged: int = 0,
    records_inserted: int = 0,
    records_updated: int = 0,
    records_failed: int = 0,
    error_message: str | None = None,
) -> None:
    run.status = status
    run.finished_at = datetime.utcnow()
    run.records_seen = records_seen
    run.records_staged = records_staged
    run.records_inserted = records_inserted
    run.records_updated = records_updated
    run.records_failed = records_failed
    run.error_message = error_message
    db.add(run)

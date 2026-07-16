"""Resumable master_jobs analysis through the private GPU ATS model."""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

import httpx
from sqlalchemy import text

from app.db.postgres import PostgresClient

log = logging.getLogger("placeup.master_ats_analysis")
ANALYSIS_VERSION = os.getenv("ATS_MODEL_VERSION", "mistral-ats-v1")
MODEL_URL = os.getenv("ATS_MODEL_URL", "").rstrip("/")
SERVICE_TOKEN = os.getenv("ATS_MODEL_SERVICE_TOKEN", "")
MIN_JD_CHARS = int(os.getenv("ATS_ANALYSIS_MIN_JD_CHARS", "500"))

FETCH_SQL = text("""
SELECT id, title, company, location, description, extra_metadata
FROM master_jobs
WHERE status = 'active'
  AND length(trim(coalesce(description, ''))) >= :min_chars
  AND (
    coalesce(extra_metadata->'ats_model_analysis'->>'version', '') <> :version
    OR coalesce(extra_metadata->'ats_model_analysis'->>'description_hash', '')
       <> md5(coalesce(description, ''))
  )
  AND (
    nullif(extra_metadata->'ats_model_analysis_error'->>'attempted_at', '') IS NULL
    OR (extra_metadata->'ats_model_analysis_error'->>'attempted_at')::timestamptz < now() - interval '6 hours'
  )
ORDER BY coalesce(posted_at, first_seen_at, last_seen_at) DESC NULLS LAST, id
LIMIT :batch_size
""")

UPDATE_SQL = text("""
UPDATE master_jobs
SET extra_metadata = jsonb_set(
  coalesce(extra_metadata, '{}'::jsonb),
  '{ats_model_analysis}',
  cast(:analysis as jsonb),
  true
) - 'ats_model_analysis_error'
WHERE id = :job_id
""")

ERROR_SQL = text("""
UPDATE master_jobs
SET extra_metadata = jsonb_set(
  coalesce(extra_metadata, '{}'::jsonb),
  '{ats_model_analysis_error}',
  cast(:error as jsonb),
  true
)
WHERE id = :job_id
""")


def _identity_token(audience: str) -> str:
    from google.auth.transport.requests import Request
    from google.oauth2 import id_token

    return id_token.fetch_id_token(Request(), audience)


def _description_hash(description: str) -> str:
    # This is a change detector, not a security boundary. PostgreSQL's built-in
    # md5(text) lets the selection query compare it without a pgcrypto extension.
    return hashlib.md5((description or "").encode("utf-8"), usedforsecurity=False).hexdigest()


def _call_model(client: httpx.Client, row: dict[str, Any], identity: str = "") -> dict[str, Any]:
    headers = {"X-Service-Token": SERVICE_TOKEN}
    if identity:
        headers["Authorization"] = f"Bearer {identity}"
    response = client.post(
        f"{MODEL_URL}/v1/analyze-job",
        headers=headers,
        json={
            "job_id": str(row["id"]),
            "title": str(row.get("title") or "Unknown role"),
            "company": str(row.get("company") or ""),
            "location": str(row.get("location") or ""),
            "description": str(row.get("description") or ""),
        },
    )
    response.raise_for_status()
    payload = response.json()
    analysis = payload.get("analysis")
    if not isinstance(analysis, dict):
        raise ValueError("ATS model returned no analysis object")
    return {
        **analysis,
        "version": ANALYSIS_VERSION,
        "model": "SlyGoblin/mistral_ATSscore_generation",
        "base_model": "mistralai/Mistral-7B-Instruct-v0.2",
        "description_hash": _description_hash(str(row.get("description") or "")),
        "analyzed_at": datetime.now(timezone.utc).isoformat(),
    }


def run(*, batch_size: int = 10, max_jobs: int = 0, max_runtime_seconds: int = 82_800) -> dict[str, Any]:
    if not MODEL_URL or not SERVICE_TOKEN:
        raise RuntimeError("ATS_MODEL_URL and ATS_MODEL_SERVICE_TOKEN are required")
    started = time.monotonic()
    db = PostgresClient()
    identity = _identity_token(MODEL_URL) if (urlparse(MODEL_URL).hostname or "").endswith(".run.app") else ""
    analyzed = failed = 0
    last_error = ""

    with httpx.Client(timeout=httpx.Timeout(900.0, connect=30.0)) as client:
        while time.monotonic() - started < max_runtime_seconds:
            if max_jobs and analyzed + failed >= max_jobs:
                break
            size = min(batch_size, max_jobs - analyzed - failed) if max_jobs else batch_size
            with db.session() as session:
                rows = [dict(row) for row in session.execute(
                    FETCH_SQL,
                    {"min_chars": MIN_JD_CHARS, "version": ANALYSIS_VERSION, "batch_size": max(1, size)},
                ).mappings().all()]
            if not rows:
                break
            for row in rows:
                if time.monotonic() - started >= max_runtime_seconds:
                    break
                try:
                    analysis = _call_model(client, row, identity)
                    with db.session() as session:
                        session.execute(UPDATE_SQL, {"job_id": row["id"], "analysis": json.dumps(analysis)})
                    analyzed += 1
                    if analyzed % 25 == 0:
                        log.info("Analyzed %s master jobs", analyzed)
                except httpx.HTTPStatusError as exc:
                    if identity and exc.response.status_code in {401, 403}:
                        identity = _identity_token(MODEL_URL)
                    failed += 1
                    last_error = f"HTTP {exc.response.status_code}: {exc.response.text[:200]}"
                    with db.session() as session:
                        session.execute(ERROR_SQL, {
                            "job_id": row["id"],
                            "error": json.dumps({"version": ANALYSIS_VERSION, "attempted_at": datetime.now(timezone.utc).isoformat(), "detail": last_error}),
                        })
                    log.warning("Job %s analysis failed: %s", row["id"], last_error)
                except Exception as exc:
                    failed += 1
                    last_error = str(exc)[:300]
                    with db.session() as session:
                        session.execute(ERROR_SQL, {
                            "job_id": row["id"],
                            "error": json.dumps({"version": ANALYSIS_VERSION, "attempted_at": datetime.now(timezone.utc).isoformat(), "detail": last_error}),
                        })
                    log.warning("Job %s analysis failed: %s", row["id"], last_error)

    summary = {
        "analyzed": analyzed,
        "failed": failed,
        "version": ANALYSIS_VERSION,
        "duration_seconds": round(time.monotonic() - started, 2),
        "last_error": last_error,
    }
    log.info("Master ATS analysis complete: %s", summary)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze active master jobs with the private ATS model")
    parser.add_argument("--batch-size", type=int, default=10)
    parser.add_argument("--max-jobs", type=int, default=0, help="0 means continue until runtime or completion")
    parser.add_argument("--max-runtime-seconds", type=int, default=82_800)
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args()
    logging.basicConfig(level=args.log_level.upper(), format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    print(json.dumps(run(batch_size=args.batch_size, max_jobs=args.max_jobs, max_runtime_seconds=args.max_runtime_seconds)))


if __name__ == "__main__":
    main()

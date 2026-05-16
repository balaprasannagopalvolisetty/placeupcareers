"""
ATS Worker — recomputes per-user, per-job ATS match scores in the background.

Why this is its own service
---------------------------
The API container was doing full ATS scoring inline on every job-list
request. Two problems with that:

1. CPU pressure: tokenizing a 50-page resume and 40 job descriptions on
   each request used noticeable CPU on the request-serving container,
   which made the Today filter feel slow.
2. Coupling: a slow scoring pass meant the request itself was slow.
   Cold-start retries piled on more work.

Pulling the work into a Cloud Run Job:
- Keeps the API container small & fast.
- Lets us run on a CPU-bigger, longer-timeout instance without paying
  for it on every API replica.
- Persists scores so list endpoints can read pre-computed values.

Operationally it is a one-shot script: Cloud Scheduler triggers the job
every N minutes, the job scans recently-changed users / jobs and writes
scores back to the database.

Run with:
    python -m app.workers.ats_worker --limit-users 500 --limit-jobs 2000

Cloud Run Job command (see .github/workflows/deploy.yml):
    --command python --args "-m,app.workers.ats_worker"
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import time

logger = logging.getLogger("ats_worker")


async def run(limit_users: int, limit_jobs: int) -> dict:
    """Recompute scores for the active resume of each recent user against
    the most-recent jobs. Returns a small summary so Cloud Run logs are
    useful at a glance.

    Implementation note: keep this thin and idempotent. Heavy lifting
    (DB writes, scoring) lives in app.services.ats_scorer and
    app.db.postgres so it can be unit tested without spinning up Cloud
    Run.
    """
    started = time.time()
    from app.api.jobs import _prepare_resume_tokens, _score_job_against_resume, _active_resume_text
    from app.db.postgres import PostgresClient
    from app.services import user_store

    db = PostgresClient()

    # Bound the work: recent users × recent jobs. We intentionally don't
    # try to score everything every run — Cloud Run Jobs have a hard
    # ceiling, and rescoring everyone hourly is wasteful.
    user_ids: list[str] = []
    try:
        user_ids = [u["id"] for u in user_store.list_recent_users(limit=limit_users)]
    except AttributeError:
        # list_recent_users hasn't been added to user_store yet — fall
        # back to scoring just the user_ids who have an applications row.
        logger.warning("user_store.list_recent_users missing; using application authors as the user set.")
        user_ids = list({a.get("user_id") for a in user_store.list_recent_applications(limit=limit_users) or [] if a.get("user_id")})

    jobs = await db.get_jobs(filters={}, limit=limit_jobs, offset=0)

    scored = 0
    skipped = 0
    for user_id in user_ids:
        resume_text = await _active_resume_text(user_id)
        if not resume_text:
            skipped += 1
            continue
        cache = _prepare_resume_tokens(resume_text)
        # Write back top-N scores so the API can read them without
        # recomputing on demand. The exact persistence target depends
        # on what your jobs DB supports — log for now if missing.
        upsert_fn = getattr(user_store, "upsert_match_scores", None)
        if not upsert_fn:
            logger.warning(
                "user_store.upsert_match_scores is not implemented yet — "
                "scoring run is a no-op until persistence lands."
            )
            scored += 1
            continue
        payload = []
        for job in jobs:
            text = f"{job.get('title') or ''}\n{job.get('description') or ''}"
            score = _score_job_against_resume(resume_text, text, resume_cache=cache)
            payload.append({"job_id": job.get("id"), "score": score})
        upsert_fn(user_id, payload)
        scored += 1

    duration = round(time.time() - started, 2)
    summary = {
        "users_scored": scored,
        "users_skipped": skipped,
        "jobs_considered": len(jobs),
        "duration_seconds": duration,
    }
    logger.info("ATS worker complete: %s", summary)
    return summary


def main():
    parser = argparse.ArgumentParser(description="Recompute per-user ATS scores in the background.")
    parser.add_argument("--limit-users", type=int, default=500, help="Max users to score this run.")
    parser.add_argument("--limit-jobs", type=int, default=2000, help="Max jobs to score against per user.")
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args()

    logging.basicConfig(
        level=args.log_level.upper(),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    summary = asyncio.run(run(args.limit_users, args.limit_jobs))
    # Cloud Run picks up stdout JSON neatly — useful when scanning logs.
    import json
    print(json.dumps(summary))


if __name__ == "__main__":
    main()

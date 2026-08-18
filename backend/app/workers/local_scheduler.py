"""Local replacement for Cloud Scheduler and Cloud Run Jobs.

Every task runs in a child process using the same backend image and local
PostgreSQL connection. This keeps worker failures isolated from the API while
remaining completely independent of GCP. Use ``--list`` to inspect the local
schedule or ``--run NAME`` for an immediate one-off execution.
"""
from __future__ import annotations

import argparse
import logging
import os
import subprocess
import sys
from dataclasses import dataclass
from zoneinfo import ZoneInfo

from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_EXECUTED
from apscheduler.executors.pool import ThreadPoolExecutor
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

log = logging.getLogger("placeup.local_scheduler")


@dataclass(frozen=True)
class LocalJob:
    name: str
    module: str
    args: tuple[str, ...]
    cron: dict[str, str | int]

    @property
    def command(self) -> list[str]:
        return [sys.executable, "-m", self.module, *self.args]


JOBS: tuple[LocalJob, ...] = (
    LocalJob("job-scraper-am", "app.etl.jobs_scraper_6h", (), {"hour": 11, "minute": 0}),
    LocalJob("job-scraper-pm", "app.etl.jobs_scraper_6h", (), {"hour": 20, "minute": 0}),
    LocalJob("daily-match-digest", "app.etl.daily_match_digest", (), {"hour": 9, "minute": 0}),
    LocalJob("jd-repair", "app.workers.job_description_repair", ("--limit", "5000", "--concurrency", "6"), {"hour": "*/2", "minute": 10}),
    LocalJob("company-link-resolver", "app.workers.company_link_resolver", ("--limit", "400", "--concurrency", "5"), {"hour": "*/2", "minute": 30}),
    LocalJob("board-discovery", "app.workers.board_discovery_sweep", ("--limit", "800", "--concurrency", "1"), {"hour": "*/6", "minute": 0}),
    LocalJob("job-liveness", "app.workers.job_liveness_checker", ("--limit", "1500", "--concurrency", "24"), {"hour": "*/6", "minute": 45}),
    LocalJob("stale-jobs", "app.workers.stale_jobs_sweeper", ("--retention-days", "60"), {"hour": 3, "minute": 30}),
    LocalJob("job-retention", "app.workers.job_retention", ("--retention-days", "60"), {"hour": 4, "minute": 15}),
    LocalJob("ats-worker", "app.workers.ats_worker", ("--limit-users", "500", "--limit-jobs", "2000"), {"hour": 2, "minute": 30}),
    LocalJob("taxonomy-report", "app.workers.taxonomy_evolution", (), {"day_of_week": "sun", "hour": 5, "minute": 0}),
    LocalJob("master-ats-analysis", "app.workers.master_ats_analysis", ("--batch-size", "10", "--max-runtime-seconds", "10800"), {"hour": 1, "minute": 0}),
)


def _disabled() -> set[str]:
    value = os.getenv("LOCAL_SCHEDULER_DISABLED_JOBS", "").strip()
    disabled = {part.strip() for part in value.replace("~", ",").split(",") if part.strip()}
    if os.getenv("LOCAL_ATS_ANALYSIS_ENABLED", "false").lower() not in {"1", "true", "yes", "on"}:
        disabled.add("master-ats-analysis")
    return disabled


def _run(job: LocalJob) -> int:
    log.info("Starting local job %s: %s", job.name, " ".join(job.command))
    completed = subprocess.run(job.command, check=False, env=os.environ.copy())
    if completed.returncode:
        log.error("Local job %s failed with exit code %s", job.name, completed.returncode)
    else:
        log.info("Local job %s completed", job.name)
    return completed.returncode


def _listener(event) -> None:
    if event.code == EVENT_JOB_ERROR:
        log.error("Scheduled job %s raised: %s", event.job_id, event.exception)
    elif event.code == EVENT_JOB_EXECUTED:
        log.info("Scheduled job %s finished", event.job_id)


def build_scheduler() -> BlockingScheduler:
    timezone_name = os.getenv("LOCAL_TIMEZONE", "America/Chicago")
    timezone = ZoneInfo(timezone_name)
    scheduler = BlockingScheduler(
        timezone=timezone,
        executors={"default": ThreadPoolExecutor(max_workers=max(1, int(os.getenv("LOCAL_WORKER_CONCURRENCY", "2"))))},
        job_defaults={"coalesce": True, "max_instances": 1, "misfire_grace_time": 1800},
    )
    disabled = _disabled()
    for job in JOBS:
        if job.name in disabled:
            log.info("Local job disabled: %s", job.name)
            continue
        scheduler.add_job(
            _run,
            CronTrigger(timezone=timezone, **job.cron),
            args=(job,),
            id=job.name,
            name=job.name,
            replace_existing=True,
        )
    scheduler.add_listener(_listener, EVENT_JOB_EXECUTED | EVENT_JOB_ERROR)
    return scheduler


def main() -> int:
    parser = argparse.ArgumentParser(description="Run PlaceUp's cloud-free local worker schedule.")
    parser.add_argument("--list", action="store_true", help="Print the configured jobs and exit")
    parser.add_argument("--run", metavar="NAME", help="Run one configured job immediately and exit")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    by_name = {job.name: job for job in JOBS}
    if args.list:
        for job in JOBS:
            state = "disabled" if job.name in _disabled() else "enabled"
            print(f"{job.name:24} {state:8} {job.cron}  {' '.join(job.command)}")
        return 0
    if args.run:
        job = by_name.get(args.run)
        if not job:
            parser.error(f"unknown job {args.run!r}; choose from {', '.join(by_name)}")
        return _run(job)

    scheduler = build_scheduler()
    log.info("Local scheduler started with %s jobs", len(scheduler.get_jobs()))
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown(wait=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""
Per-ATS submission queue (Cloud Tasks abstraction).

The doc mandates Cloud Tasks over Pub/Sub for submission: per-queue
`max-dispatches-per-second` + `max-concurrent-dispatches`, explicit retry caps,
scheduling, and dedup — exactly what's needed to pace Workday far slower than
Greenhouse and avoid tripping volume thresholds. One queue per ATS.

This module gives the rest of the app a single `enqueue_application(...)`
entry point with two backends:

  * cloudtasks — real `google.cloud.tasks_v2` (production on GCP)
  * local      — in-process asyncio fallback for dev/tests (no infra)

Handlers must be idempotent: keyed on the Cloud Tasks task name (or the
application id here), enqueuing the same application twice is a no-op.
"""
from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field

from app.config import settings

log = logging.getLogger("placeup.apply")

# Conservative per-ATS pacing. Workday/Oracle/SuccessFactors are throttled hard
# because they run bot-detection; Tier A APIs can move faster.
PER_ATS_RATE: dict[str, float] = {
    "greenhouse": 5.0,
    "ashby": 5.0,
    "smartrecruiters": 5.0,
    "workable": 5.0,
    "recruitee": 5.0,
    "lever": 1.0,
    "workday": 0.1,          # ~1 every 10s — deliberately slow
    "oracle": 0.1,
    "successfactors": 0.1,
    "_default": 0.5,
}

# Dedicated queues provisioned by deploy_backend.ps1. Browser/Tier-B/C and
# unknown platforms share one deliberately slow queue until their production
# drivers are implemented.
DEDICATED_QUEUES = frozenset({
    "greenhouse", "ashby", "smartrecruiters", "workable", "recruitee",
})


def rate_for(ats_type: str) -> float:
    return PER_ATS_RATE.get((ats_type or "").lower(), PER_ATS_RATE["_default"])


@dataclass
class _LocalQueue:
    """Dev/test fallback — tracks enqueued task names for idempotency."""

    seen: set[str] = field(default_factory=set)

    async def enqueue(self, task_name: str, coro_factory) -> bool:
        if task_name in self.seen:
            log.info("apply_queue(local): duplicate task %s ignored", task_name)
            return False
        self.seen.add(task_name)
        # Run detached; in production Cloud Tasks pushes to an HTTP handler.
        asyncio.get_event_loop().create_task(coro_factory())
        return True


_local = _LocalQueue()


def _backend() -> str:
    return getattr(settings, "apply_queue_backend", "local") or "local"


async def enqueue_application(app_id: str, ats_type: str, coro_factory) -> bool:
    """Enqueue an approved application for submission.

    `coro_factory` is a zero-arg callable returning the coroutine that performs
    the submission (used only by the local backend). Returns False if this
    exact application is already queued (idempotency).
    """
    task_name = f"apply-{ats_type}-{app_id}"
    backend = _backend()
    if backend == "cloudtasks":  # pragma: no cover - requires GCP
        return _enqueue_cloud_tasks(task_name, ats_type, app_id)
    return await _local.enqueue(task_name, coro_factory)


def _enqueue_cloud_tasks(task_name: str, ats_type: str, app_id: str) -> bool:  # pragma: no cover
    """Create a Cloud Task on the per-ATS queue. Requires
    google-cloud-tasks and APPLY_QUEUE_* settings to be configured."""
    from google.cloud import tasks_v2  # type: ignore

    client = tasks_v2.CloudTasksClient()
    project = settings.gcp_project_id
    location = getattr(settings, "apply_queue_region", "us-east1")
    queue_key = (ats_type or "").strip().lower()
    queue = f"apply-{queue_key if queue_key in DEDICATED_QUEUES else 'browser'}"
    parent = client.queue_path(project, location, queue)
    worker_url = str(getattr(settings, "apply_worker_url", "") or "").rstrip("/")
    if not worker_url:
        raise RuntimeError("APPLY_WORKER_URL is required for the Cloud Tasks backend")
    handler_url = f"{worker_url}/api/apply/internal-submit"
    headers = {"Content-Type": "application/json"}
    # Authenticate the push to the internal-submit handler with the shared key.
    if getattr(settings, "internal_api_key", ""):
        headers["X-API-Key"] = settings.internal_api_key
    else:
        raise RuntimeError("INTERNAL_API_KEY is required for Cloud Tasks pushes")
    task = {
        "name": client.task_path(project, location, queue, task_name),
        "http_request": {
            "http_method": tasks_v2.HttpMethod.POST,
            "url": handler_url,
            "headers": headers,
            "body": json.dumps({"app_id": app_id}).encode("utf-8"),
        },
    }
    try:
        client.create_task(request={"parent": parent, "task": task})
    except Exception as exc:
        # Cloud Tasks retains completed task names for a deduplication window.
        # Treat an already-existing name as the intended idempotent no-op while
        # allowing every other infrastructure/auth error to fail the approval.
        if exc.__class__.__name__ == "AlreadyExists":
            return False
        raise
    return True

from __future__ import annotations

import logging
from typing import Iterable

from google.cloud import firestore

from app.config import settings
from app.etl.api_sources.schema import NormalizedJob

logger = logging.getLogger(__name__)


def firestore_client() -> firestore.Client:
    project = settings.gcp_project_id or settings.user_firestore_project_id
    return firestore.Client(project=project, database=settings.user_firestore_database)


def upsert_jobs(jobs: Iterable[NormalizedJob], *, collection: str = "jobs") -> dict[str, int]:
    """Upsert normalized jobs by job_id into Firestore in batches."""
    db = firestore_client()
    count = 0
    batch = db.batch()
    committed = 0
    for job in jobs:
        ref = db.collection(collection).document(job.job_id)
        batch.set(ref, job.model_dump(exclude={"raw"}), merge=True)
        count += 1
        if count % 450 == 0:
            batch.commit()
            committed += 450
            batch = db.batch()
    if count % 450:
        batch.commit()
        committed = count
    logger.info("Firestore upsert complete: collection=%s jobs=%s", collection, count)
    return {"upserted": count, "committed": committed}


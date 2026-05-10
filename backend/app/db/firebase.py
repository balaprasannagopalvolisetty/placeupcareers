"""
PlaceUp Career — Firebase Firestore Client
Database layer for production deployment on Google Cloud.
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)

_db = None


def get_firestore_db():
    """Initialize and return the Firestore database client.

    Uses Firebase Admin SDK with Application Default Credentials
    (or explicit service account JSON for local dev).

    Returns:
        Firestore client instance
    """
    global _db
    if _db is not None:
        return _db

    try:
        import firebase_admin
        from firebase_admin import credentials, firestore

        from app.config import settings

        if not firebase_admin._apps:
            if settings.firebase_credentials_path:
                try:
                    cred = credentials.Certificate(settings.firebase_credentials_path)
                    firebase_admin.initialize_app(cred)
                except FileNotFoundError:
                    # Fall back to Application Default Credentials
                    firebase_admin.initialize_app()
            else:
                firebase_admin.initialize_app()

        _db = firestore.client()
        logger.info("Firestore client initialized successfully")
        return _db

    except Exception as e:
        logger.error(f"Failed to initialize Firestore: {e}")
        raise


class FirestoreClient:
    """Firestore database operations for PlaceUp Career.

    Provides CRUD operations for jobs, resumes, H1B data, and alerts.
    Uses the same collection structure defined in backend-pipeline.md.
    """

    def __init__(self):
        self.db = get_firestore_db()

    # ─── Jobs Collection ───────────────────────────────────

    async def get_jobs(self, filters: dict = None, limit: int = 20, offset: int = 0) -> list[dict]:
        """Get jobs with optional filtering."""
        ref = self.db.collection("jobs")

        if filters:
            if filters.get("category"):
                ref = ref.where("category", "==", filters["category"])
            if filters.get("visa_only"):
                ref = ref.where("visa.visa_score", ">=", 30)
            if filters.get("source"):
                ref = ref.where("source", "==", filters["source"])

        ref = ref.order_by("scraped_at", direction="DESCENDING")
        ref = ref.limit(limit).offset(offset)

        docs = ref.stream()
        return [doc.to_dict() | {"id": doc.id} for doc in docs]

    async def get_job(self, job_id: str) -> Optional[dict]:
        """Get a single job by ID."""
        doc = self.db.collection("jobs").document(job_id).get()
        return doc.to_dict() | {"id": doc.id} if doc.exists else None

    async def upsert_job(self, job_id: str, job_data: dict) -> None:
        """Insert or update a job document."""
        self.db.collection("jobs").document(job_id).set(job_data, merge=True)

    async def upsert_jobs_batch(self, jobs: list[dict]) -> int:
        """Batch upsert multiple jobs."""
        batch = self.db.batch()
        count = 0
        for job in jobs:
            job_id = job.get("id", "")
            if job_id:
                ref = self.db.collection("jobs").document(job_id)
                batch.set(ref, job, merge=True)
                count += 1
                # Firestore batch limit is 500
                if count % 500 == 0:
                    batch.commit()
                    batch = self.db.batch()
        if count % 500 != 0:
            batch.commit()
        return count

    async def get_existing_hashes(self) -> set:
        """Get all existing content hashes for deduplication."""
        docs = self.db.collection("jobs").select(["content_hash"]).stream()
        return {doc.to_dict().get("content_hash", "") for doc in docs}

    async def count_jobs(self, filters: dict = None) -> int:
        """Count total jobs matching filters."""
        ref = self.db.collection("jobs")
        if filters:
            if filters.get("category"):
                ref = ref.where("category", "==", filters["category"])
        # Note: Firestore doesn't have a direct count() for filtered queries
        # in all SDK versions, so we use a select+stream approach
        docs = list(ref.select([]).stream())
        return len(docs)

    # ─── H1B Sponsors Collection ───────────────────────────

    async def get_h1b_sponsors(self, employer: str = None, limit: int = 20) -> list[dict]:
        """Get H1B sponsor records."""
        ref = self.db.collection("h1bSponsors")
        if employer:
            ref = ref.where("employer_name", ">=", employer.upper())
            ref = ref.where("employer_name", "<=", employer.upper() + "\uf8ff")
        ref = ref.limit(limit)
        docs = ref.stream()
        return [doc.to_dict() | {"id": doc.id} for doc in docs]

    async def upsert_h1b_sponsors(self, sponsors: list[dict]) -> int:
        """Batch upsert H1B sponsor records."""
        batch = self.db.batch()
        count = 0
        for sponsor in sponsors:
            sponsor_id = sponsor.get("id", "")
            if sponsor_id:
                ref = self.db.collection("h1bSponsors").document(sponsor_id)
                batch.set(ref, sponsor, merge=True)
                count += 1
                if count % 500 == 0:
                    batch.commit()
                    batch = self.db.batch()
        if count % 500 != 0:
            batch.commit()
        return count

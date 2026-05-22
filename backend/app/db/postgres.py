"""PostgreSQL database client for production jobs/contact data."""

from __future__ import annotations

import hashlib
import json
from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import create_engine, func, inspect, or_, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings
from app.db.schema import Company, Contact, H1BSponsor, Job, MasterJob, StagingRecord


def json_default(value):
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def stable_hash(payload: dict) -> str:
    raw = json.dumps(payload, sort_keys=True, default=json_default)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def normalize_text(value: str) -> str:
    return " ".join((value or "").lower().strip().split())


class PostgresClient:
    """Postgres-backed data access used by FastAPI and ETL workers."""

    def __init__(self, database_url: Optional[str] = None):
        self.engine = create_engine(database_url or settings.database_url, pool_pre_ping=True)
        self.SessionLocal = sessionmaker(bind=self.engine, autoflush=False, expire_on_commit=False)
        self._has_master_jobs: Optional[bool] = None

    @contextmanager
    def session(self):
        db = self.SessionLocal()
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    async def get_jobs(self, filters: dict = None, limit: int = 20, offset: int = 0) -> list[dict]:
        if self._master_jobs_available():
            with self.session() as db:
                stmt = select(
                    MasterJob.id,
                    MasterJob.title,
                    MasterJob.company,
                    MasterJob.location,
                    func.substr(MasterJob.description, 1, 900).label("description"),
                    MasterJob.source_url,
                    MasterJob.employment_type,
                    MasterJob.salary_min,
                    MasterJob.salary_max,
                    MasterJob.currency,
                    MasterJob.visa_opt,
                    MasterJob.visa_stem_opt,
                    MasterJob.visa_h1b,
                    MasterJob.h1b_verified,
                    MasterJob.visa_score,
                    MasterJob.source_name,
                    MasterJob.source_job_id,
                    MasterJob.posted_at,
                    MasterJob.last_seen_at,
                    MasterJob.status,
                    MasterJob.canonical_key,
                    MasterJob.extra_metadata,
                    MasterJob.merged_sources,
                )
                stmt = self._apply_master_job_filters(stmt, filters)
                stmt = stmt.order_by(MasterJob.last_seen_at.desc()).limit(limit).offset(offset)
                rows = db.execute(stmt).mappings().all()
                return [self._master_job_mapping_to_dict(row) for row in rows]
        with self.session() as db:
            stmt = select(
                Job.id,
                Job.title,
                Company.name.label("company"),
                Job.location,
                func.substr(Job.description, 1, 900).label("description"),
                Job.source_url,
                Job.category,
                Job.employment_type,
                Job.salary_min,
                Job.salary_max,
                Job.currency,
                Job.visa_opt,
                Job.visa_stem_opt,
                Job.visa_h1b,
                Job.h1b_verified,
                Job.visa_score,
                Job.source_name,
                Job.source_job_id,
                Job.posted_at,
                Job.last_seen_at,
                Job.status,
                Job.content_hash,
                Job.extra_metadata,
            ).join(Company, Job.company_id == Company.id, isouter=True)
            stmt = self._apply_job_filters(stmt, filters)
            stmt = stmt.order_by(Job.last_seen_at.desc()).limit(limit).offset(offset)
            rows = db.execute(stmt).mappings().all()
            return [self._job_mapping_to_dict(row) for row in rows]

    async def get_job(self, job_id: str) -> Optional[dict]:
        if self._master_jobs_available():
            with self.session() as db:
                row = db.execute(select(MasterJob).where(MasterJob.id == job_id)).scalar_one_or_none()
                return self._master_job_to_dict(row) if row else None
        with self.session() as db:
            row = db.execute(
                select(Job, Company)
                .join(Company, Job.company_id == Company.id, isouter=True)
                .where(Job.id == job_id)
            ).first()
            if not row:
                return None
            job, company = row
            return self._job_to_dict(job, company)

    async def upsert_job(self, job_id: str, job_data: dict) -> None:
        await self.upsert_jobs_batch([job_data | {"id": job_id}])

    async def upsert_jobs_batch(self, jobs: list[dict]) -> int:
        from app.etl.loaders.jobs import load_normalized_jobs

        with self.session() as db:
            return load_normalized_jobs(db, jobs)

    async def get_existing_hashes(self) -> set:
        with self.session() as db:
            return set(db.execute(select(Job.content_hash)).scalars().all())

    async def count_jobs(self, filters: dict = None) -> int:
        if self._master_jobs_available():
            with self.session() as db:
                stmt = select(func.count()).select_from(MasterJob)
                stmt = self._apply_master_job_filters(stmt, filters)
                return int(db.execute(stmt).scalar() or 0)
        with self.session() as db:
            stmt = select(func.count()).select_from(Job).join(Company, Job.company_id == Company.id, isouter=True)
            stmt = self._apply_job_filters(stmt, filters)
            return int(db.execute(stmt).scalar() or 0)

    async def deactivate_old_jobs(self, days_old: int = 15) -> int:
        cutoff = datetime.utcnow() - timedelta(days=days_old)
        with self.session() as db:
            result = db.execute(
                text("update jobs set status = 'inactive' where status = 'active' and last_seen_at < :cutoff"),
                {"cutoff": cutoff},
            )
            return int(result.rowcount or 0)

    async def get_contacts(self, company=None, job_id=None, limit=50):
        with self.session() as db:
            stmt = select(Contact, Company).join(Company, Contact.company_id == Company.id, isouter=True)
            if company:
                stmt = stmt.where(Company.normalized_name == normalize_text(company))
            if job_id:
                stmt = stmt.where(Contact.related_job_id == job_id)
            rows = db.execute(stmt.order_by(Contact.first_seen_at.desc()).limit(limit)).all()
            return [self._contact_to_dict(contact, company_row) for contact, company_row in rows]

    async def upsert_contacts(self, contacts):
        if not contacts:
            return 0
        with self.session() as db:
            count = 0
            for contact in contacts:
                company = upsert_company(db, contact.get("company") or "")
                values = {
                    "id": contact.get("id") or stable_hash(contact),
                    "company_id": company.id if company else None,
                    "full_name": contact.get("full_name"),
                    "first_name": contact.get("first_name"),
                    "last_name": contact.get("last_name"),
                    "title": contact.get("title"),
                    "role": contact.get("role") or "other",
                    "company_domain": contact.get("company_domain"),
                    "email": (contact.get("email") or "").lower() or None,
                    "linkedin_url": contact.get("linkedin_url"),
                    "linkedin_search_url": contact.get("linkedin_search_url"),
                    "source_name": contact.get("source") or "unknown",
                    "confidence": contact.get("confidence"),
                    "related_job_id": contact.get("related_job_id"),
                    "last_verified_at": contact.get("last_verified_at"),
                    "source_payload": contact.get("source_payload") or {},
                }
                if not values["email"] and not values["linkedin_url"]:
                    continue
                stmt = insert(Contact).values(**values)
                stmt = stmt.on_conflict_do_update(
                    index_elements=[Contact.id],
                    set_={k: v for k, v in values.items() if k != "id"},
                )
                db.execute(stmt)
                count += 1
            return count

    async def count_contacts(self, company=None):
        with self.session() as db:
            stmt = select(func.count()).select_from(Contact)
            if company:
                stmt = stmt.join(Company).where(Company.normalized_name == normalize_text(company))
            return int(db.execute(stmt).scalar() or 0)

    async def get_h1b_sponsors(self, employer: str = None, state: str = None, limit: int = 20, offset: int = 0) -> list[dict]:
        with self.session() as db:
            stmt = select(H1BSponsor)
            if employer:
                stmt = stmt.where(H1BSponsor.employer_name.ilike(f"%{employer}%"))
            if state:
                stmt = stmt.where(func.lower(H1BSponsor.state) == state.lower())
            rows = db.execute(stmt.order_by(H1BSponsor.total_petitions.desc()).limit(limit).offset(offset)).scalars().all()
            return [row.to_dict() for row in rows]

    async def count_h1b_sponsors(self, employer: str = None, state: str = None) -> int:
        with self.session() as db:
            stmt = select(func.count()).select_from(H1BSponsor)
            if employer:
                stmt = stmt.where(H1BSponsor.employer_name.ilike(f"%{employer}%"))
            if state:
                stmt = stmt.where(func.lower(H1BSponsor.state) == state.lower())
            return int(db.execute(stmt).scalar() or 0)

    async def upsert_h1b_sponsors(self, sponsors: list[dict]) -> int:
        with self.session() as db:
            count = 0
            for sponsor in sponsors:
                stmt = insert(H1BSponsor).values(**sponsor)
                stmt = stmt.on_conflict_do_update(
                    index_elements=[H1BSponsor.id],
                    set_={k: v for k, v in sponsor.items() if k != "id"},
                )
                db.execute(stmt)
                count += 1
            return count

    def stage_records(self, db: Session, ingest_run_id, source_name: str, records: list[dict]) -> int:
        count = 0
        for record in records:
            payload = record.get("payload", record)
            record_hash = record.get("record_hash") or stable_hash(payload)
            stmt = insert(StagingRecord).values(
                ingest_run_id=ingest_run_id,
                source_name=source_name,
                source_record_id=record.get("source_record_id"),
                source_url=record.get("source_url"),
                record_hash=record_hash,
                payload=payload,
                normalized_payload=record.get("normalized_payload"),
                validation_status=record.get("validation_status", "pending"),
                validation_errors=record.get("validation_errors", []),
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=[StagingRecord.source_name, StagingRecord.record_hash],
                set_={
                    "ingest_run_id": ingest_run_id,
                    "payload": payload,
                    "normalized_payload": record.get("normalized_payload"),
                    "validation_status": record.get("validation_status", "pending"),
                    "validation_errors": record.get("validation_errors", []),
                    "last_seen_at": func.now(),
                },
            )
            db.execute(stmt)
            count += 1
        return count

    def _apply_job_filters(self, stmt, filters: dict | None):
        filters = filters or {}
        if filters.get("category"):
            stmt = stmt.where(Job.category == filters["category"])
        if filters.get("source"):
            stmt = stmt.where(Job.source_name == filters["source"])
        if filters.get("status"):
            stmt = stmt.where(Job.status == filters["status"])
        if filters.get("location"):
            stmt = stmt.where(Job.location.ilike(f"%{filters['location']}%"))
        if filters.get("posted_since"):
            stmt = stmt.where(Job.posted_at >= filters["posted_since"])
        if filters.get("title_terms"):
            terms = [str(t).strip() for t in filters["title_terms"] if str(t).strip()]
            if terms:
                stmt = stmt.where(or_(*[
                    clause
                    for term in terms[:80]
                    for clause in (Job.title.ilike(f"%{term}%"), Company.name.ilike(f"%{term}%"))
                ]))
        if filters.get("search"):
            q = f"%{filters['search']}%"
            stmt = stmt.where(or_(Job.title.ilike(q), Company.name.ilike(q), Job.description.ilike(q)))
        if filters.get("visa_only"):
            stmt = stmt.where(Job.visa_score >= 30)
        return stmt

    def _master_jobs_available(self) -> bool:
        if self._has_master_jobs is None:
            self._has_master_jobs = inspect(self.engine).has_table("master_jobs")
        return bool(self._has_master_jobs)

    def _apply_master_job_filters(self, stmt, filters: dict | None):
        filters = filters or {}
        if filters.get("category"):
            stmt = stmt.where(MasterJob.extra_metadata.op("->>")("category") == filters["category"])
        if filters.get("source"):
            stmt = stmt.where(MasterJob.source_name == filters["source"])
        if filters.get("status"):
            stmt = stmt.where(MasterJob.status == filters["status"])
        if filters.get("location"):
            stmt = stmt.where(MasterJob.location.ilike(f"%{filters['location']}%"))
        if filters.get("posted_since"):
            stmt = stmt.where(MasterJob.posted_at >= filters["posted_since"])
        if filters.get("title_terms"):
            terms = [str(t).strip() for t in filters["title_terms"] if str(t).strip()]
            if terms:
                stmt = stmt.where(or_(*[
                    clause
                    for term in terms[:80]
                    for clause in (MasterJob.title.ilike(f"%{term}%"), MasterJob.company.ilike(f"%{term}%"))
                ]))
        if filters.get("search"):
            q = f"%{filters['search']}%"
            stmt = stmt.where(or_(MasterJob.title.ilike(q), MasterJob.company.ilike(q), MasterJob.description.ilike(q)))
        if filters.get("visa_only"):
            stmt = stmt.where(MasterJob.visa_score >= 30)
        return stmt

    def _master_job_to_dict(self, job: MasterJob) -> dict:
        meta = job.extra_metadata or {}
        return {
            "id": job.id,
            "title": job.title,
            "company": job.company or "",
            "location": job.location or "",
            "description": job.description or "",
            "job_url": job.source_url or "",
            "category": meta.get("category") or "Other",
            "job_type": job.employment_type or "",
            "salary": {
                "min_salary": float(job.salary_min) if job.salary_min is not None else None,
                "max_salary": float(job.salary_max) if job.salary_max is not None else None,
                "currency": job.currency or "USD",
            },
            "visa": {
                "visa_opt": job.visa_opt,
                "visa_stem_opt": job.visa_stem_opt,
                "visa_h1b": job.visa_h1b,
                "h1b_verified": job.h1b_verified,
                "visa_score": job.visa_score,
            },
            "source": job.source_name,
            "source_job_id": job.source_job_id or "",
            "posted_at": job.posted_at,
            "scraped_at": job.last_seen_at,
            "status": job.status,
            "content_hash": job.canonical_key,
            "extra_metadata": meta | {"merged_sources": job.merged_sources or []},
        }

    def _master_job_mapping_to_dict(self, row) -> dict:
        meta = row.get("extra_metadata") or {}
        return {
            "id": row.get("id"),
            "title": row.get("title"),
            "company": row.get("company") or "",
            "location": row.get("location") or "",
            "description": row.get("description") or "",
            "job_url": row.get("source_url") or "",
            "category": meta.get("category") or "Other",
            "job_type": row.get("employment_type") or "",
            "salary": {
                "min_salary": float(row.get("salary_min")) if row.get("salary_min") is not None else None,
                "max_salary": float(row.get("salary_max")) if row.get("salary_max") is not None else None,
                "currency": row.get("currency") or "USD",
            },
            "visa": {
                "visa_opt": row.get("visa_opt"),
                "visa_stem_opt": row.get("visa_stem_opt"),
                "visa_h1b": row.get("visa_h1b"),
                "h1b_verified": row.get("h1b_verified"),
                "visa_score": row.get("visa_score"),
            },
            "source": row.get("source_name"),
            "source_job_id": row.get("source_job_id") or "",
            "posted_at": row.get("posted_at"),
            "scraped_at": row.get("last_seen_at"),
            "status": row.get("status"),
            "content_hash": row.get("canonical_key"),
            "extra_metadata": meta | {"merged_sources": row.get("merged_sources") or []},
        }

    def _job_to_dict(self, job: Job, company: Company | None) -> dict:
        return {
            "id": job.id,
            "title": job.title,
            "company": company.name if company else "",
            "location": job.location or "",
            "description": job.description or "",
            "job_url": job.source_url or "",
            "category": job.category or "Other",
            "job_type": job.employment_type or "",
            "salary": {
                "min_salary": float(job.salary_min) if job.salary_min is not None else None,
                "max_salary": float(job.salary_max) if job.salary_max is not None else None,
                "currency": job.currency or "USD",
            },
            "visa": {
                "visa_opt": job.visa_opt,
                "visa_stem_opt": job.visa_stem_opt,
                "visa_h1b": job.visa_h1b,
                "h1b_verified": job.h1b_verified,
                "visa_score": job.visa_score,
            },
            "source": job.source_name,
            "source_job_id": job.source_job_id or "",
            "posted_at": job.posted_at,
            "scraped_at": job.last_seen_at,
            "status": job.status,
            "content_hash": job.content_hash,
            "extra_metadata": job.extra_metadata or {},
        }

    def _job_mapping_to_dict(self, row) -> dict:
        return {
            "id": row.get("id"),
            "title": row.get("title"),
            "company": row.get("company") or "",
            "location": row.get("location") or "",
            "description": row.get("description") or "",
            "job_url": row.get("source_url") or "",
            "category": row.get("category") or "Other",
            "job_type": row.get("employment_type") or "",
            "salary": {
                "min_salary": float(row.get("salary_min")) if row.get("salary_min") is not None else None,
                "max_salary": float(row.get("salary_max")) if row.get("salary_max") is not None else None,
                "currency": row.get("currency") or "USD",
            },
            "visa": {
                "visa_opt": row.get("visa_opt"),
                "visa_stem_opt": row.get("visa_stem_opt"),
                "visa_h1b": row.get("visa_h1b"),
                "h1b_verified": row.get("h1b_verified"),
                "visa_score": row.get("visa_score"),
            },
            "source": row.get("source_name"),
            "source_job_id": row.get("source_job_id") or "",
            "posted_at": row.get("posted_at"),
            "scraped_at": row.get("last_seen_at"),
            "status": row.get("status"),
            "content_hash": row.get("content_hash"),
            "extra_metadata": row.get("extra_metadata") or {},
        }

    def _contact_to_dict(self, contact: Contact, company: Company | None) -> dict:
        return {
            "id": contact.id,
            "full_name": contact.full_name,
            "first_name": contact.first_name,
            "last_name": contact.last_name,
            "title": contact.title,
            "role": contact.role or "other",
            "company": company.name if company else "",
            "company_domain": contact.company_domain,
            "email": contact.email,
            "linkedin_url": contact.linkedin_url,
            "linkedin_search_url": contact.linkedin_search_url,
            "source": contact.source_name,
            "confidence": contact.confidence,
            "related_job_id": contact.related_job_id,
            "discovered_at": contact.first_seen_at,
            "last_verified_at": contact.last_verified_at,
            "source_payload": contact.source_payload or {},
        }


def upsert_company(db: Session, company_name: str) -> Company | None:
    if not company_name:
        return None
    normalized = normalize_text(company_name)
    stmt = insert(Company).values(name=company_name, normalized_name=normalized)
    stmt = stmt.on_conflict_do_update(
        index_elements=[Company.normalized_name],
        set_={"name": company_name, "updated_at": func.now()},
    ).returning(Company)
    return db.execute(stmt).scalar_one()

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
from app.services.global_visa_rules import COUNTRY_RULES, TARGET_COUNTRIES, in_target_country, resolve_country
from app.utils.job_quality import clean_job_company, clean_job_description, infer_posted_at


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
        filters = filters or {}
        if self._master_jobs_available():
            with self.session() as db:
                stmt = select(
                    MasterJob.id,
                    MasterJob.title,
                    MasterJob.company,
                    MasterJob.location,
                    MasterJob.country,
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
                fetch_limit = self._job_fetch_limit(limit, filters)
                stmt = stmt.order_by(MasterJob.last_seen_at.desc()).limit(fetch_limit).offset(offset)
                rows = db.execute(stmt).mappings().all()
                return self._filter_target_jobs([self._master_job_mapping_to_dict(row) for row in rows])[:limit]
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
            fetch_limit = self._job_fetch_limit(limit, filters)
            stmt = stmt.order_by(Job.last_seen_at.desc()).limit(fetch_limit).offset(offset)
            rows = db.execute(stmt).mappings().all()
            return self._filter_target_jobs([self._job_mapping_to_dict(row) for row in rows])[:limit]

    async def get_jobs_source_balanced(
        self,
        filters: dict = None,
        limit: int = 200,
        offset: int = 0,
        per_source: int = 80,
    ) -> list[dict]:
        """Return a fresh candidate pool without letting one source dominate.

        The Jobs page does additional role/visa/quality filtering in Python.
        A newest-first query can be overwhelmed by a high-volume source like
        Dice, so this query first caps each source, then lets the API rank the
        mixed pool for the user.
        """
        if not self._master_jobs_available():
            return await self.get_jobs(filters=filters, limit=limit, offset=offset)
        filters = filters or {}
        with self.session() as db:
            base = select(
                MasterJob.id,
                MasterJob.title,
                MasterJob.company,
                MasterJob.location,
                MasterJob.country,
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
                func.row_number().over(
                    partition_by=MasterJob.source_name,
                    order_by=MasterJob.last_seen_at.desc(),
                ).label("source_rank"),
            )
            base = self._apply_master_job_filters(base, filters).subquery()
            stmt = (
                select(base)
                .where(base.c.source_rank <= per_source)
                .order_by(base.c.last_seen_at.desc())
                .limit(limit)
                .offset(offset)
            )
            rows = db.execute(stmt).mappings().all()
            return self._filter_target_jobs([self._master_job_mapping_to_dict(row) for row in rows])[:limit]

    def _job_fetch_limit(self, limit: int, filters: dict | None) -> int:
        """Bound broad pages tightly, but let taxonomy filters scan enough rows.

        Role/category/search filters are finalized in the API after taxonomy,
        visa, language, scam, and JD-quality checks. A hard 500-row DB cap made
        some dropdown selections look empty even when matching jobs existed
        deeper in master_jobs.
        """
        filters = filters or {}
        if filters.get("coverage_scan") or limit > 500:
            return min(max(limit, 500), 12000)
        return min(max(limit * 5, limit + 20), 500)

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

    async def update_job_description(
        self,
        job_id: str,
        description: str,
        *,
        source_url: str | None = None,
        extra_metadata: dict | None = None,
    ) -> int:
        if not job_id or not description:
            return 0
        params = {
            "job_id": job_id,
            "description": description,
            "source_url": source_url,
            "extra_metadata": json.dumps(extra_metadata or {}, default=json_default),
        }
        with self.session() as db:
            total = 0
            if self._master_jobs_available():
                result = db.execute(
                    text(
                        """
                        update master_jobs
                           set description = :description,
                               source_url = coalesce(:source_url, source_url),
                               extra_metadata = coalesce(extra_metadata, '{}'::jsonb) || cast(:extra_metadata as jsonb)
                         where id = :job_id
                        """
                    ),
                    params,
                )
                total += int(result.rowcount or 0)
            result = db.execute(
                text(
                    """
                    update jobs
                       set description = :description,
                           source_url = coalesce(:source_url, source_url),
                           extra_metadata = coalesce(extra_metadata, '{}'::jsonb) || cast(:extra_metadata as jsonb)
                     where id = :job_id
                    """
                ),
                params,
            )
            total += int(result.rowcount or 0)
            return total

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
        if filters.get("country"):
            stmt = stmt.where(func.upper(Job.country) == str(filters["country"]).upper())
        effective_job_date = func.coalesce(Job.posted_at, Job.last_seen_at)
        if filters.get("effective_since"):
            stmt = stmt.where(effective_job_date >= filters["effective_since"])
        if filters.get("effective_before"):
            stmt = stmt.where(effective_job_date < filters["effective_before"])
        if filters.get("seen_since"):
            stmt = stmt.where(Job.last_seen_at >= filters["seen_since"])
        if filters.get("seen_before"):
            stmt = stmt.where(Job.last_seen_at < filters["seen_before"])
        if filters.get("posted_since"):
            stmt = stmt.where(Job.posted_at >= filters["posted_since"])
        if filters.get("posted_before"):
            stmt = stmt.where(Job.posted_at < filters["posted_before"])
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
        if filters.get("visa_program"):
            stmt = stmt.where(Job.extra_metadata.op("->")("visa_programs").op("?")(filters["visa_program"]))
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
        if filters.get("country"):
            stmt = stmt.where(func.upper(MasterJob.country) == str(filters["country"]).upper())
        effective_job_date = func.coalesce(MasterJob.posted_at, MasterJob.last_seen_at)
        if filters.get("effective_since"):
            stmt = stmt.where(effective_job_date >= filters["effective_since"])
        if filters.get("effective_before"):
            stmt = stmt.where(effective_job_date < filters["effective_before"])
        if filters.get("seen_since"):
            stmt = stmt.where(MasterJob.last_seen_at >= filters["seen_since"])
        if filters.get("seen_before"):
            stmt = stmt.where(MasterJob.last_seen_at < filters["seen_before"])
        if filters.get("posted_since"):
            stmt = stmt.where(MasterJob.posted_at >= filters["posted_since"])
        if filters.get("posted_before"):
            stmt = stmt.where(MasterJob.posted_at < filters["posted_before"])
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
        if filters.get("visa_program"):
            stmt = stmt.where(MasterJob.extra_metadata.op("->")("visa_programs").op("?")(filters["visa_program"]))
        return stmt

    def _visa_payload(
        self,
        *,
        meta: dict,
        visa_opt: bool,
        visa_stem_opt: bool,
        visa_h1b: bool,
        h1b_verified: bool,
        visa_score: int,
        country: str | None = None,
        location: str | None = None,
    ) -> dict:
        location_country = resolve_country(location, default=country)
        visa_country = location_country or meta.get("visa_country") or country
        target_country = str(visa_country or "").upper() in TARGET_COUNTRIES
        meta_country = str(meta.get("visa_country") or "").upper()
        metadata_country_matches = not meta_country or meta_country == str(visa_country or "").upper()
        is_us_role = str(visa_country or "").upper() == "US"
        if not target_country or not is_us_role:
            visa_opt = False
            visa_stem_opt = False
            visa_h1b = False
            h1b_verified = False
        visa_programs = meta.get("visa_programs") or []
        visa_program_names = meta.get("visa_program_names") or []
        if not target_country:
            visa_score = 0
            visa_programs = []
            visa_program_names = []
        elif not metadata_country_matches:
            visa_programs = []
            visa_program_names = []
        elif not is_us_role:
            legacy_us_codes = {"h1b", "stem_opt", "opt", "o1", "l1", "eb23"}
            legacy_us_names = {"h-1b", "stem opt", "opt", "o-1", "l-1", "eb-2/eb-3"}
            visa_programs = [code for code in visa_programs if str(code).lower() not in legacy_us_codes]
            visa_program_names = [
                name for name in visa_program_names
                if str(name).strip().lower() not in legacy_us_names
            ]
        return {
            "visa_opt": visa_opt,
            "visa_stem_opt": visa_stem_opt,
            "visa_h1b": visa_h1b,
            "h1b_verified": h1b_verified,
            "visa_score": visa_score,
            "visa_country": visa_country,
            "visa_country_name": COUNTRY_RULES.get(str(visa_country or "").upper()).name if target_country else meta.get("visa_country_name"),
            "visa_programs": visa_programs,
            "visa_program_names": visa_program_names,
            "sponsor_verified": bool(target_country and metadata_country_matches and (meta.get("sponsor_verified") or h1b_verified)),
            "sponsor_source": meta.get("sponsor_source"),
            "english_friendly": bool(target_country and meta.get("english_friendly")),
        }

    def _filter_target_jobs(self, jobs: list[dict]) -> list[dict]:
        filtered: list[dict] = []
        for job in jobs:
            ok, _country = in_target_country(job.get("location"), default=job.get("country"))
            if ok:
                filtered.append(job)
        return filtered

    def _master_job_to_dict(self, job: MasterJob) -> dict:
        meta = job.extra_metadata or {}
        raw_description = job.description or ""
        company = clean_job_company(job.company or "", raw_description, job.title)
        posted_at = infer_posted_at(job.posted_at, raw_description)
        description = clean_job_description(raw_description)
        return {
            "id": job.id,
            "title": job.title,
            "company": company,
            "location": job.location or "",
            "country": job.country,
            "description": description,
            "job_url": job.source_url or "",
            "category": meta.get("category") or "Other",
            "job_type": job.employment_type or "",
            "salary": {
                "min_salary": float(job.salary_min) if job.salary_min is not None else None,
                "max_salary": float(job.salary_max) if job.salary_max is not None else None,
                "currency": job.currency or "USD",
            },
            "visa": self._visa_payload(
                meta=meta,
                country=job.country,
                location=job.location,
                visa_opt=job.visa_opt,
                visa_stem_opt=job.visa_stem_opt,
                visa_h1b=job.visa_h1b,
                h1b_verified=job.h1b_verified,
                visa_score=job.visa_score,
            ),
            "source": job.source_name,
            "source_job_id": job.source_job_id or "",
            "posted_at": posted_at,
            "scraped_at": job.last_seen_at,
            "status": job.status,
            "content_hash": job.canonical_key,
            "extra_metadata": meta | {"merged_sources": job.merged_sources or []},
        }

    def _master_job_mapping_to_dict(self, row) -> dict:
        meta = row.get("extra_metadata") or {}
        raw_description = row.get("description") or ""
        company = clean_job_company(row.get("company") or "", raw_description, row.get("title"))
        posted_at = infer_posted_at(row.get("posted_at"), raw_description)
        description = clean_job_description(raw_description)
        return {
            "id": row.get("id"),
            "title": row.get("title"),
            "company": company,
            "location": row.get("location") or "",
            "country": row.get("country"),
            "description": description,
            "job_url": row.get("source_url") or "",
            "category": meta.get("category") or "Other",
            "job_type": row.get("employment_type") or "",
            "salary": {
                "min_salary": float(row.get("salary_min")) if row.get("salary_min") is not None else None,
                "max_salary": float(row.get("salary_max")) if row.get("salary_max") is not None else None,
                "currency": row.get("currency") or "USD",
            },
            "visa": self._visa_payload(
                meta=meta,
                country=row.get("country"),
                location=row.get("location"),
                visa_opt=bool(row.get("visa_opt")),
                visa_stem_opt=bool(row.get("visa_stem_opt")),
                visa_h1b=bool(row.get("visa_h1b")),
                h1b_verified=bool(row.get("h1b_verified")),
                visa_score=int(row.get("visa_score") or 0),
            ),
            "source": row.get("source_name"),
            "source_job_id": row.get("source_job_id") or "",
            "posted_at": posted_at,
            "scraped_at": row.get("last_seen_at"),
            "status": row.get("status"),
            "content_hash": row.get("canonical_key"),
            "extra_metadata": meta | {"merged_sources": row.get("merged_sources") or []},
        }

    def _job_to_dict(self, job: Job, company: Company | None) -> dict:
        raw_description = job.description or ""
        company_name = clean_job_company(company.name if company else "", raw_description, job.title)
        posted_at = infer_posted_at(job.posted_at, raw_description)
        description = clean_job_description(raw_description)
        return {
            "id": job.id,
            "title": job.title,
            "company": company_name,
            "location": job.location or "",
            "description": description,
            "job_url": job.source_url or "",
            "category": job.category or "Other",
            "job_type": job.employment_type or "",
            "salary": {
                "min_salary": float(job.salary_min) if job.salary_min is not None else None,
                "max_salary": float(job.salary_max) if job.salary_max is not None else None,
                "currency": job.currency or "USD",
            },
            "visa": self._visa_payload(
                meta=job.extra_metadata or {},
                country=getattr(job, "country", None),
                location=job.location,
                visa_opt=job.visa_opt,
                visa_stem_opt=job.visa_stem_opt,
                visa_h1b=job.visa_h1b,
                h1b_verified=job.h1b_verified,
                visa_score=job.visa_score,
            ),
            "source": job.source_name,
            "source_job_id": job.source_job_id or "",
            "posted_at": posted_at,
            "scraped_at": job.last_seen_at,
            "status": job.status,
            "content_hash": job.content_hash,
            "extra_metadata": job.extra_metadata or {},
        }

    def _job_mapping_to_dict(self, row) -> dict:
        raw_description = row.get("description") or ""
        company = clean_job_company(row.get("company") or "", raw_description, row.get("title"))
        posted_at = infer_posted_at(row.get("posted_at"), raw_description)
        description = clean_job_description(raw_description)
        return {
            "id": row.get("id"),
            "title": row.get("title"),
            "company": company,
            "location": row.get("location") or "",
            "description": description,
            "job_url": row.get("source_url") or "",
            "category": row.get("category") or "Other",
            "job_type": row.get("employment_type") or "",
            "salary": {
                "min_salary": float(row.get("salary_min")) if row.get("salary_min") is not None else None,
                "max_salary": float(row.get("salary_max")) if row.get("salary_max") is not None else None,
                "currency": row.get("currency") or "USD",
            },
            "visa": self._visa_payload(
                meta=row.get("extra_metadata") or {},
                country=row.get("country"),
                location=row.get("location"),
                visa_opt=bool(row.get("visa_opt")),
                visa_stem_opt=bool(row.get("visa_stem_opt")),
                visa_h1b=bool(row.get("visa_h1b")),
                h1b_verified=bool(row.get("h1b_verified")),
                visa_score=int(row.get("visa_score") or 0),
            ),
            "source": row.get("source_name"),
            "source_job_id": row.get("source_job_id") or "",
            "posted_at": posted_at,
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

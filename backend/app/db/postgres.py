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
from app.db.schema import Company, Contact, H1BSponsor, Job, MasterJob, StagingRecord, VisaSponsor
from app.services.global_visa_rules import COUNTRY_RULES, TARGET_COUNTRIES, in_target_country, resolve_country
from app.utils.job_quality import clean_job_company, clean_job_description, infer_posted_at


def json_default(value):
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _company_link_url(meta: dict) -> Optional[str]:
    """Official company POSTING URL resolved by the company link worker.

    Only job-specific ATS postings qualify for the Apply button. A generic
    "/careers" landing page must never replace the original job link — users
    clicking Apply on a specific role were getting dumped on company home
    careers pages with no way to find the job.
    """
    link = meta.get("company_link") if isinstance(meta, dict) else None
    if isinstance(link, dict) and link.get("link_type") == "ats_posting":
        url = str(link.get("url") or "").strip()
        if url.startswith("http"):
            return url
    return None


def _salary_payload(minimum, maximum, currency: str | None) -> Optional[dict]:
    min_value = float(minimum) if minimum is not None and float(minimum) > 0 else None
    max_value = float(maximum) if maximum is not None and float(maximum) > 0 else None
    if min_value is None and max_value is None:
        return None
    return {"min_salary": min_value, "max_salary": max_value, "currency": currency or "USD"}


def stable_hash(payload: dict) -> str:
    raw = json.dumps(payload, sort_keys=True, default=json_default)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def normalize_text(value: str) -> str:
    return " ".join((value or "").lower().strip().split())


class PostgresClient:
    """Postgres-backed data access used by FastAPI and ETL workers."""

    def __init__(self, database_url: Optional[str] = None):
        # Bounded pool so N Cloud Run instances cannot exhaust Cloud SQL's
        # max_connections under load. Per-instance ceiling = pool_size +
        # max_overflow; multiply by max-instances when sizing the DB tier
        # (see SCALING_PLAYBOOK.md). Tunable via DB_POOL_SIZE / DB_MAX_OVERFLOW.
        timeout_ms = int(getattr(settings, "db_statement_timeout_ms", 0) or 0)
        connect_args = (
            {"options": f"-c statement_timeout={timeout_ms}"} if timeout_ms > 0 else {}
        )
        self.engine = create_engine(
            database_url or settings.database_url,
            pool_pre_ping=True,
            pool_size=int(getattr(settings, "db_pool_size", 5) or 5),
            max_overflow=int(getattr(settings, "db_max_overflow", 10) or 10),
            pool_recycle=1800,
            pool_timeout=15,
            connect_args=connect_args,
        )
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
                description_expr = (
                    MasterJob.description
                    if self._needs_full_description(filters)
                    else func.substr(MasterJob.description, 1, 900)
                )
                stmt = select(
                    MasterJob.id,
                    MasterJob.title,
                    MasterJob.company,
                    MasterJob.location,
                    MasterJob.country,
                    description_expr.label("description"),
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
                    MasterJob.first_seen_at,
                    MasterJob.last_seen_at,
                    MasterJob.status,
                    MasterJob.canonical_key,
                    MasterJob.extra_metadata,
                    MasterJob.merged_sources,
                )
                stmt = self._apply_master_job_filters(stmt, filters)
                fetch_limit = self._job_fetch_limit(limit, filters)
                # id tiebreaker: bulk-scraped rows share last_seen_at, and
                # Postgres returns tied rows in ARBITRARY order per query —
                # without this, page 2 could fetch a reshuffled pool whose
                # slice repeats page 1 ("same jobs on every page").
                ordered = stmt.order_by(MasterJob.last_seen_at.desc(), MasterJob.id).limit(fetch_limit).offset(offset)
                rows = list(db.execute(ordered).mappings().all())

                # Guaranteed first-party representation: high-volume aggregator
                # scrapes (LinkedIn/Indeed/Dice) refresh last_seen_at constantly
                # and can fill the ENTIRE recency-ordered pool, so direct
                # ATS/career-page postings never even reached the API-level
                # ranking. Top up the pool with the freshest first-party rows
                # under the same filters; the feed ranking then orders them
                # ahead of aggregator copies.
                if not filters.get("source") and offset == 0:
                    from app.scrape_constants import FIRST_PARTY_ATS_SOURCES
                    fp_stmt = self._apply_master_job_filters(
                        select(*stmt.selected_columns), filters
                    ).where(
                        MasterJob.source_name.in_(sorted(FIRST_PARTY_ATS_SOURCES))
                    ).order_by(
                        MasterJob.last_seen_at.desc(), MasterJob.id
                    ).limit(min(600, fetch_limit))
                    seen_ids = {row["id"] for row in rows}
                    for row in db.execute(fp_stmt).mappings().all():
                        if row["id"] not in seen_ids:
                            rows.append(row)
                            seen_ids.add(row["id"])
                return self._filter_target_jobs([self._master_job_mapping_to_dict(row) for row in rows])[:limit]
        with self.session() as db:
            description_expr = (
                Job.description
                if self._needs_full_description(filters)
                else func.substr(Job.description, 1, 900)
            )
            stmt = select(
                Job.id,
                Job.title,
                Company.name.label("company"),
                Job.location,
                description_expr.label("description"),
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
                Job.first_seen_at,
                Job.last_seen_at,
                Job.status,
                Job.content_hash,
                Job.extra_metadata,
            ).join(Company, Job.company_id == Company.id, isouter=True)
            stmt = self._apply_job_filters(stmt, filters)
            fetch_limit = self._job_fetch_limit(limit, filters)
            stmt = stmt.order_by(Job.last_seen_at.desc(), Job.id).limit(fetch_limit).offset(offset)
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
            description_expr = (
                MasterJob.description
                if self._needs_full_description(filters)
                else func.substr(MasterJob.description, 1, 900)
            )
            base = select(
                MasterJob.id,
                MasterJob.title,
                MasterJob.company,
                MasterJob.location,
                MasterJob.country,
                description_expr.label("description"),
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
                MasterJob.first_seen_at,
                MasterJob.last_seen_at,
                MasterJob.status,
                MasterJob.canonical_key,
                MasterJob.extra_metadata,
                MasterJob.merged_sources,
                func.row_number().over(
                    partition_by=MasterJob.source_name,
                    order_by=(MasterJob.last_seen_at.desc(), MasterJob.id),
                ).label("source_rank"),
            )
            base = self._apply_master_job_filters(base, filters).subquery()
            stmt = (
                select(base)
                .where(base.c.source_rank <= per_source)
                .order_by(base.c.last_seen_at.desc(), base.c.id)
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
        if filters.get("coverage_scan"):
            # Was 30000. A 30k-row scan for a single category/role click was a
            # top cause of statement-timeout 500s on the Jobs page; 12k still
            # leaves a deep pool after the Python taxonomy/quality filters while
            # keeping the query inside the request budget.
            return min(max(limit, 500), 12000)
        if limit > 500:
            return min(max(limit, 500), 8000)
        return min(max(limit * 5, limit + 20), 500)

    def _needs_full_description(self, filters: dict | None) -> bool:
        """Only free-text search needs full JD text in the pool query.

        title_terms / date filters match on title/company/timestamps, so
        shipping full descriptions for up to 2500 rows made every personalized
        or time-filtered page slow. Pool ranking works on the 900-char prefix;
        the visible page is re-scored against full descriptions separately.
        """
        filters = filters or {}
        return bool(filters.get("coverage_scan") or filters.get("search"))

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

    async def get_job_descriptions(self, job_ids: list[str]) -> dict[str, str]:
        """Full (untruncated) cleaned descriptions for a small set of jobs.

        Used to re-score the visible page of the Jobs list with the exact same
        text the Job Detail endpoint scores, so both surfaces show one number.
        """
        ids = [str(i) for i in job_ids if i]
        if not ids:
            return {}
        with self.session() as db:
            if self._master_jobs_available():
                rows = db.execute(
                    select(MasterJob.id, MasterJob.description).where(MasterJob.id.in_(ids))
                ).all()
            else:
                rows = db.execute(
                    select(Job.id, Job.description).where(Job.id.in_(ids))
                ).all()
        return {str(row[0]): clean_job_description(row[1] or "") for row in rows}

    async def merge_job_metadata(
        self,
        job_id: str,
        metadata: dict,
        *,
        description: str | None = None,
    ) -> int:
        """Merge keys into a job's extra_metadata (master_jobs + jobs); optionally upgrade the JD."""
        if not job_id or not metadata:
            return 0
        params = {
            "job_id": job_id,
            "description": description or "",
            "extra_metadata": json.dumps(metadata, default=json_default),
        }
        with self.session() as db:
            total = 0
            if self._master_jobs_available():
                result = db.execute(
                    text(
                        """
                        update master_jobs
                           set description = coalesce(nullif(:description, ''), description),
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
                       set description = coalesce(nullif(:description, ''), description),
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

    async def jobs_added_daily(self, *, days: int = 14, title_terms: list[str] | None = None) -> list[dict]:
        """Count NEW postings per calendar day by first_seen_at (not last_seen).

        Powers the Alerts "positions added" chart. Using first_seen_at means the
        numbers reflect genuinely new inventory instead of the near-constant
        re-scrape activity that last_seen_at records.
        """
        days = max(1, min(int(days), 90))
        use_master = self._master_jobs_available()
        table = "master_jobs" if use_master else "jobs"
        title_col = "title"
        clauses = ["first_seen_at >= now() - (:days || ' days')::interval", "status = 'active'"]
        params: dict = {"days": days}
        terms = [str(t).strip() for t in (title_terms or []) if str(t).strip()][:40]
        if terms:
            ors = []
            for i, term in enumerate(terms):
                key = f"t{i}"
                ors.append(f"{title_col} ILIKE :{key}")
                params[key] = f"%{term}%"
            clauses.append("(" + " OR ".join(ors) + ")")
        where = " AND ".join(clauses)
        sql = f"""
            SELECT to_char(date_trunc('day', first_seen_at), 'YYYY-MM-DD') AS day,
                   COUNT(*) AS count
              FROM {table}
             WHERE {where}
             GROUP BY 1
             ORDER BY 1
        """
        with self.session() as db:
            rows = db.execute(text(sql), params).mappings().all()
        by_day = {row["day"]: int(row["count"]) for row in rows}
        # Dense series: fill missing days with 0 so the chart has no gaps.
        from datetime import timedelta
        today = datetime.utcnow().date()
        series = []
        for offset in range(days - 1, -1, -1):
            d = (today - timedelta(days=offset)).isoformat()
            series.append({"date": d, "count": by_day.get(d, 0)})
        return series

    async def top_roles_by_country(self, country: str, *, limit: int = 8) -> list[dict]:
        """Read-only: top role categories the scraper has collected for a country.

        Powers the admin "roles per country" panel. Best-effort and purely a
        read — it never writes and is independent of the ingestion pipeline.
        """
        limit = max(1, min(int(limit), 50))
        if self._master_jobs_available():
            table = "master_jobs"
            role_expr = "COALESCE(NULLIF(extra_metadata->>'category', ''), 'Other')"
        else:
            table = "jobs"
            role_expr = "COALESCE(NULLIF(category, ''), 'Other')"
        sql = f"""
            SELECT {role_expr} AS role, COUNT(*) AS count
              FROM {table}
             WHERE status = 'active' AND upper(country) = upper(:country)
             GROUP BY 1
             ORDER BY 2 DESC
             LIMIT :limit
        """
        with self.session() as db:
            rows = db.execute(text(sql), {"country": country, "limit": limit}).mappings().all()
        return [{"role": row["role"], "count": int(row["count"])} for row in rows]

    async def admin_coverage_snapshot(self, *, top_limit: int = 8, sample_limit: int = 3000) -> dict:
        """Fast snapshot for the private admin coverage charts.

        This intentionally uses the status/last_seen index and summarizes a
        bounded newest-active sample. Full-table grouped counts can exceed the
        request budget while the scraper is busy; admin needs a quick coverage
        picture more than an exact analytical warehouse query.
        """
        top_limit = max(1, min(int(top_limit), 25))
        sample_limit = max(500, min(int(sample_limit), 5000))
        use_master = self._master_jobs_available()
        table = "master_jobs" if use_master else "jobs"
        estimate_sql = """
            SELECT GREATEST(0, reltuples)::bigint AS estimate
              FROM pg_class
             WHERE relname = :table
             LIMIT 1
        """
        with self.session() as db:
            estimate = int(db.execute(text(estimate_sql), {"table": table}).scalar() or 0)
            rows = []
            try:
                db.execute(text("SET LOCAL statement_timeout = '2500ms'"))
                if use_master:
                    sample_sql = f"""
                        SELECT country, extra_metadata
                          FROM {table}
                         WHERE status = 'active'
                         LIMIT :sample_limit
                    """
                else:
                    sample_sql = f"""
                        SELECT country, jsonb_build_object('category', category) AS extra_metadata
                          FROM {table}
                         WHERE status = 'active'
                         LIMIT :sample_limit
                    """
                rows = db.execute(text(sample_sql), {"sample_limit": sample_limit}).mappings().all()
            except Exception:
                try:
                    db.rollback()
                except Exception:
                    pass
                rows = []

        country_counts: dict[str, int] = {}
        country_roles: dict[str, dict[str, int]] = {}
        global_roles: dict[str, int] = {}
        for row in rows:
            country = str(row.get("country") or "UNSPECIFIED").upper()
            meta = row.get("extra_metadata") or {}
            if not isinstance(meta, dict):
                meta = {}
            role = (
                str(meta.get("taxonomy_role") or meta.get("role") or meta.get("category") or "Other")
                .strip()
                or "Other"
            )
            country_counts[country] = country_counts.get(country, 0) + 1
            country_roles.setdefault(country, {})[role] = country_roles.setdefault(country, {}).get(role, 0) + 1
            global_roles[role] = global_roles.get(role, 0) + 1

        per_country = []
        for country, positions in sorted(country_counts.items(), key=lambda item: item[1], reverse=True):
            rule = COUNTRY_RULES.get(country)
            role_counts = country_roles.get(country, {})
            per_country.append({
                "country": country,
                "country_name": rule.name if rule else ("Unspecified" if country == "UNSPECIFIED" else country),
                "positions": positions,
                "top_roles": [
                    {"role": role, "count": count}
                    for role, count in sorted(role_counts.items(), key=lambda item: (-item[1], item[0]))[:top_limit]
                ],
            })

        return {
            "total_positions": max(estimate, len(rows)),
            "sample_size": len(rows),
            "estimated": True,
            "per_country": per_country or [
                {
                    "country": "ALL",
                    "country_name": "All active positions",
                    "positions": max(estimate, len(rows)),
                    "top_roles": [],
                }
            ],
            "top_roles": ([
                {"role": role, "count": count}
                for role, count in sorted(global_roles.items(), key=lambda item: (-item[1], item[0]))[:top_limit]
            ] or [{"role": "Collected active positions", "count": max(estimate, len(rows))}]),
        }

    async def admin_coverage_snapshot_exact(self, *, top_limit: int = 8) -> dict:
        """Exact grouped snapshot retained for offline diagnostics."""
        top_limit = max(1, min(int(top_limit), 25))
        use_master = self._master_jobs_available()
        table = "master_jobs" if use_master else "jobs"
        role_expr = (
            "COALESCE(NULLIF(extra_metadata->>'taxonomy_role', ''), "
            "NULLIF(extra_metadata->>'role', ''), "
            "NULLIF(extra_metadata->>'category', ''), 'Other')"
            if use_master
            else "COALESCE(NULLIF(category, ''), 'Other')"
        )
        country_expr = "upper(COALESCE(NULLIF(country, ''), 'UNSPECIFIED'))"
        country_sql = f"""
            SELECT {country_expr} AS country, COUNT(*) AS positions
              FROM {table}
             WHERE status = 'active'
             GROUP BY 1
             ORDER BY 2 DESC
        """
        roles_sql = f"""
            WITH role_counts AS (
                SELECT {country_expr} AS country,
                       {role_expr} AS role,
                       COUNT(*) AS count
                  FROM {table}
                 WHERE status = 'active'
                 GROUP BY 1, 2
            ),
            ranked AS (
                SELECT country, role, count,
                       ROW_NUMBER() OVER (PARTITION BY country ORDER BY count DESC, role ASC) AS rn
                  FROM role_counts
            )
            SELECT country, role, count
              FROM ranked
             WHERE rn <= :top_limit
             ORDER BY country, count DESC, role ASC
        """
        global_roles_sql = f"""
            SELECT {role_expr} AS role, COUNT(*) AS count
              FROM {table}
             WHERE status = 'active'
             GROUP BY 1
             ORDER BY 2 DESC, 1 ASC
             LIMIT :top_limit
        """
        total_sql = f"SELECT COUNT(*) AS total FROM {table} WHERE status = 'active'"
        with self.session() as db:
            total = int(db.execute(text(total_sql)).scalar() or 0)
            country_rows = db.execute(text(country_sql)).mappings().all()
            role_rows = db.execute(text(roles_sql), {"top_limit": top_limit}).mappings().all()
            global_role_rows = db.execute(text(global_roles_sql), {"top_limit": top_limit}).mappings().all()

        roles_by_country: dict[str, list[dict]] = {}
        for row in role_rows:
            country = str(row["country"] or "UNSPECIFIED").upper()
            roles_by_country.setdefault(country, []).append({
                "role": row["role"] or "Other",
                "count": int(row["count"] or 0),
            })

        per_country = []
        for row in country_rows:
            country = str(row["country"] or "UNSPECIFIED").upper()
            rule = COUNTRY_RULES.get(country)
            per_country.append({
                "country": country,
                "country_name": rule.name if rule else ("Unspecified" if country == "UNSPECIFIED" else country),
                "positions": int(row["positions"] or 0),
                "top_roles": roles_by_country.get(country, []),
            })

        return {
            "total_positions": total,
            "per_country": per_country,
            "top_roles": [
                {"role": row["role"] or "Other", "count": int(row["count"] or 0)}
                for row in global_role_rows
            ],
        }

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

    async def get_visa_sponsors(
        self,
        *,
        country: str | None = None,
        employer: str | None = None,
        region: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        with self.session() as db:
            stmt = select(VisaSponsor)
            if country:
                stmt = stmt.where(func.upper(VisaSponsor.country) == country.upper())
            if employer:
                stmt = stmt.where(VisaSponsor.employer_name.ilike(f"%{employer}%"))
            if region:
                stmt = stmt.where(func.lower(VisaSponsor.region) == region.lower())
            stmt = stmt.order_by(
                VisaSponsor.total_petitions.desc(),
                VisaSponsor.approvals.desc(),
                VisaSponsor.employer_name.asc(),
            ).limit(limit).offset(offset)
            return [row.to_dict() for row in db.execute(stmt).scalars().all()]

    async def count_visa_sponsors(
        self,
        *,
        country: str | None = None,
        employer: str | None = None,
        region: str | None = None,
    ) -> int:
        with self.session() as db:
            stmt = select(func.count()).select_from(VisaSponsor)
            if country:
                stmt = stmt.where(func.upper(VisaSponsor.country) == country.upper())
            if employer:
                stmt = stmt.where(VisaSponsor.employer_name.ilike(f"%{employer}%"))
            if region:
                stmt = stmt.where(func.lower(VisaSponsor.region) == region.lower())
            return int(db.execute(stmt).scalar() or 0)

    async def upsert_visa_sponsors(self, sponsors: list[dict]) -> int:
        with self.session() as db:
            count = 0
            for sponsor in sponsors:
                stmt = insert(VisaSponsor).values(**sponsor)
                stmt = stmt.on_conflict_do_update(
                    index_elements=[VisaSponsor.country, VisaSponsor.source_name, VisaSponsor.source_record_id],
                    set_={k: v for k, v in sponsor.items() if k != "id"},
                )
                db.execute(stmt)
                count += 1
            return count

    def stage_records(self, db: Session, ingest_run_id, source_name: str, records: list[dict]) -> int:
        count = 0
        for record in records:
            payload = self._json_safe(record.get("payload", record))
            record_hash = record.get("record_hash") or stable_hash(payload)
            stmt = insert(StagingRecord).values(
                ingest_run_id=ingest_run_id,
                source_name=source_name,
                source_record_id=record.get("source_record_id"),
                source_url=record.get("source_url"),
                record_hash=record_hash,
                payload=payload,
                normalized_payload=self._json_safe(record.get("normalized_payload")),
                validation_status=record.get("validation_status", "pending"),
                validation_errors=self._json_safe(record.get("validation_errors", [])),
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

    def _json_safe(self, value):
        return json.loads(json.dumps(value, default=json_default))

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
        if filters.get("first_seen_since"):
            stmt = stmt.where(Job.first_seen_at >= filters["first_seen_since"])
        if filters.get("posted_since"):
            stmt = stmt.where(Job.posted_at >= filters["posted_since"])
        if filters.get("posted_before"):
            stmt = stmt.where(Job.posted_at < filters["posted_before"])
        if filters.get("title_terms"):
            terms = [str(t).strip() for t in filters["title_terms"] if str(t).strip()]
            if terms:
                # Role filters belong on job titles. Including company names
                # here disabled the title trigram index and forced a full scan
                # for personalized feeds with many role aliases.
                stmt = stmt.where(or_(*[Job.title.ilike(f"%{term}%") for term in terms[:80]]))
        if filters.get("search"):
            q = f"%{filters['search']}%"
            stmt = stmt.where(or_(Job.title.ilike(q), Company.name.ilike(q), Job.description.ilike(q)))
        if filters.get("visa_only"):
            stmt = stmt.where(Job.visa_score >= 30)
        if filters.get("visa_program"):
            stmt = stmt.where(Job.extra_metadata.op("->")("visa_programs").op("?")(filters["visa_program"]))
        if filters.get("min_salary") is not None:
            # A row qualifies when its top of range clears the floor; keep
            # rows with unknown salary so the filter narrows without hiding
            # postings that simply do not publish pay.
            floor = float(filters["min_salary"])
            stmt = stmt.where(or_(Job.salary_max >= floor, Job.salary_min >= floor, Job.salary_max.is_(None)))
        if filters.get("job_type"):
            jt = f"%{str(filters['job_type']).strip()}%"
            stmt = stmt.where(Job.extra_metadata.op("->>")("job_type").ilike(jt))
        return stmt

    def _master_jobs_available(self) -> bool:
        if self._has_master_jobs is None:
            self._has_master_jobs = inspect(self.engine).has_table("master_jobs")
        return bool(self._has_master_jobs)

    def _target_country_prefilter(self, stmt):
        """SQL-level target-country filter.

        The Jobs feed previously fetched a recency-bounded pool (360 rows) and
        THEN dropped out-of-scope countries in Python — so when scrapers pulled
        many non-target rows, users saw a few hundred jobs out of 50k+, and
        pagination pointed at pages that didn't exist. Filtering in SQL keeps
        the pool full of valid rows. NULL/empty country rows pass through for
        the Python location-based check (remote/unspecified roles).
        """
        return stmt.where(
            or_(
                func.upper(MasterJob.country).in_([c.upper() for c in TARGET_COUNTRIES]),
                MasterJob.country.is_(None),
                MasterJob.country == "",
            )
        )

    def _apply_master_job_filters(self, stmt, filters: dict | None):
        filters = filters or {}
        if not filters.get("skip_target_prefilter"):
            stmt = self._target_country_prefilter(stmt)
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
        if filters.get("first_seen_since"):
            stmt = stmt.where(MasterJob.first_seen_at >= filters["first_seen_since"])
        if filters.get("posted_since"):
            stmt = stmt.where(MasterJob.posted_at >= filters["posted_since"])
        if filters.get("posted_before"):
            stmt = stmt.where(MasterJob.posted_at < filters["posted_before"])
        if filters.get("title_terms"):
            terms = [str(t).strip() for t in filters["title_terms"] if str(t).strip()]
            if terms:
                # ix_master_jobs_title_trgm supports these wildcard role
                # searches. OR-ing company ILIKE clauses into the same filter
                # made PostgreSQL abandon that index and hit statement_timeout.
                stmt = stmt.where(or_(*[
                    MasterJob.title.ilike(f"%{term}%") for term in terms[:80]
                ]))
        if filters.get("search"):
            q = f"%{filters['search']}%"
            stmt = stmt.where(or_(MasterJob.title.ilike(q), MasterJob.company.ilike(q), MasterJob.description.ilike(q)))
        if filters.get("visa_only"):
            stmt = stmt.where(MasterJob.visa_score >= 30)
        if filters.get("visa_program"):
            stmt = stmt.where(MasterJob.extra_metadata.op("->")("visa_programs").op("?")(filters["visa_program"]))
        if filters.get("min_salary") is not None:
            floor = float(filters["min_salary"])
            stmt = stmt.where(or_(MasterJob.salary_max >= floor, MasterJob.salary_min >= floor, MasterJob.salary_max.is_(None)))
        if filters.get("job_type"):
            jt = f"%{str(filters['job_type']).strip()}%"
            stmt = stmt.where(MasterJob.extra_metadata.op("->>")("job_type").ilike(jt))
        if filters.get("job_type"):
            # employment_type is free-form across sources ("Full-time", "Full
            # Time", "FULLTIME", "Permanent"...). Match on the core token.
            jt = str(filters["job_type"]).strip().lower()
            token = {
                "full-time": "full", "full time": "full", "fulltime": "full", "permanent": "full",
                "part-time": "part", "part time": "part", "parttime": "part",
                "contract": "contract", "contractor": "contract",
                "internship": "intern", "intern": "intern",
                "temporary": "temp", "temp": "temp",
            }.get(jt, jt)
            stmt = stmt.where(MasterJob.employment_type.ilike(f"%{token}%"))
        if filters.get("min_salary") is not None:
            # A job qualifies when the top of its range meets the floor; rows
            # with no salary data are excluded (expected for a salary filter).
            stmt = stmt.where(MasterJob.salary_max >= filters["min_salary"])
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
            "salary": _salary_payload(job.salary_min, job.salary_max, job.currency),
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
            "first_seen_at": job.first_seen_at,
            "scraped_at": job.last_seen_at,
            "status": job.status,
            "content_hash": job.canonical_key,
            "job_url_direct": _company_link_url(meta),
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
            "salary": _salary_payload(row.get("salary_min"), row.get("salary_max"), row.get("currency")),
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
            "first_seen_at": row.get("first_seen_at"),
            "scraped_at": row.get("last_seen_at"),
            "status": row.get("status"),
            "content_hash": row.get("canonical_key"),
            "job_url_direct": _company_link_url(meta),
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
            "salary": _salary_payload(job.salary_min, job.salary_max, job.currency),
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
            "first_seen_at": job.first_seen_at,
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
            "first_seen_at": row.get("first_seen_at"),
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

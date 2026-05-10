"""
PlaceUp Career — SQLite Local Database
Lightweight local database for development without Firebase.

Provides the same interface as FirestoreClient for seamless switching.
Toggle via DATABASE_BACKEND=sqlite in .env
"""

import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).parent.parent.parent / "data" / "placeup.db"

_SQLITE_SCALAR_COLUMN_KEYS = frozenset(
    {
        "id",
        "title",
        "company",
        "location",
        "description",
        "job_url",
        "category",
        "job_type",
        "experience_level",
        "industry",
        "salary_json",
        "visa_json",
        "source",
        "source_job_id",
        "posted_at",
        "scraped_at",
        "status",
        "content_hash",
        "expires_at",
        "match_score",
        "hiring_manager_name",
        "hiring_manager_email",
        "hiring_manager_linkedin",
        "data_json",
        "salary",
        "visa",
    }
)


def _sqlite_pack_data_json(job_data: dict) -> str:
    """
    Persist every non-column JobPost field (remote flags, ATS metadata, snapshots, …)
    alongside legacy extra_metadata payloads.
    """
    rest = {}
    for key, raw in job_data.items():
        if key in _SQLITE_SCALAR_COLUMN_KEYS:
            continue
        if raw is None:
            continue
        rest[key] = raw

    if not rest:
        return "{}"

    envelope = {"_placeup": 2, "rest": rest}
    return json.dumps(envelope, ensure_ascii=False, default=str)


def _sqlite_parse_data_json(data_raw: Optional[str]) -> dict:
    if not data_raw:
        return {}
    try:
        parsed = json.loads(data_raw)
    except (json.JSONDecodeError, TypeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


class SQLiteClient:
    """SQLite database operations for local development.

    Mirrors the FirestoreClient interface so the app layer
    doesn't need to know which backend is in use.
    """

    def __init__(self):
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        self.db_path = str(DB_PATH)
        self._init_tables()

    def _get_conn(self) -> sqlite3.Connection:
        """Get a new SQLite connection with row factory."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_tables(self):
        """Create tables if they don't exist."""
        conn = self._get_conn()
        try:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    company TEXT NOT NULL,
                    location TEXT DEFAULT '',
                    description TEXT DEFAULT '',
                    job_url TEXT DEFAULT '',
                    category TEXT DEFAULT 'Other',
                    job_type TEXT DEFAULT '',
                    experience_level TEXT DEFAULT '',
                    industry TEXT DEFAULT '',
                    salary_json TEXT DEFAULT '{}',
                    visa_json TEXT DEFAULT '{}',
                    source TEXT DEFAULT 'linkedin',
                    source_job_id TEXT DEFAULT '',
                    posted_at TEXT,
                    scraped_at TEXT,
                    status TEXT DEFAULT 'active',
                    expires_at TEXT,
                    content_hash TEXT DEFAULT '',
                    match_score INTEGER,
                    hiring_manager_name TEXT,
                    hiring_manager_email TEXT,
                    hiring_manager_linkedin TEXT,
                    data_json TEXT DEFAULT '{}'
                );

                CREATE INDEX IF NOT EXISTS idx_jobs_content_hash ON jobs(content_hash);
                CREATE INDEX IF NOT EXISTS idx_jobs_category ON jobs(category);
                CREATE INDEX IF NOT EXISTS idx_jobs_source ON jobs(source);
                CREATE INDEX IF NOT EXISTS idx_jobs_scraped_at ON jobs(scraped_at);

                CREATE TABLE IF NOT EXISTS h1b_sponsors (
                    id TEXT PRIMARY KEY,
                    employer_name TEXT NOT NULL,
                    city TEXT DEFAULT '',
                    state TEXT DEFAULT '',
                    zip_code TEXT DEFAULT '',
                    initial_approvals INTEGER DEFAULT 0,
                    initial_denials INTEGER DEFAULT 0,
                    continuing_approvals INTEGER DEFAULT 0,
                    continuing_denials INTEGER DEFAULT 0,
                    total_petitions INTEGER DEFAULT 0,
                    fiscal_year INTEGER DEFAULT 0,
                    data_json TEXT DEFAULT '{}'
                );

                CREATE INDEX IF NOT EXISTS idx_h1b_employer ON h1b_sponsors(employer_name);

                CREATE TABLE IF NOT EXISTS contacts (
                    id TEXT PRIMARY KEY,
                    full_name TEXT,
                    first_name TEXT,
                    last_name TEXT,
                    title TEXT,
                    role TEXT DEFAULT 'other',
                    company TEXT NOT NULL,
                    company_domain TEXT,
                    email TEXT,
                    linkedin_url TEXT,
                    linkedin_search_url TEXT,
                    source TEXT NOT NULL,
                    confidence TEXT DEFAULT 'unknown',
                    related_job_id TEXT,
                    discovered_at TEXT,
                    last_verified_at TEXT,
                    source_payload_json TEXT DEFAULT '{}'
                );

                CREATE INDEX IF NOT EXISTS idx_contacts_company ON contacts(company);
                CREATE INDEX IF NOT EXISTS idx_contacts_email ON contacts(email);
                CREATE INDEX IF NOT EXISTS idx_contacts_job ON contacts(related_job_id);
                CREATE INDEX IF NOT EXISTS idx_contacts_source ON contacts(source);

                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    email TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    first_name TEXT NOT NULL,
                    last_name TEXT NOT NULL,
                    plan TEXT DEFAULT 'Pro',
                    phone TEXT,
                    location TEXT,
                    visa_status TEXT,
                    experience_years TEXT,
                    current_role TEXT,
                    current_company TEXT,
                    summary TEXT,
                    linkedin_url TEXT,
                    github_url TEXT,
                    portfolio_url TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);

                CREATE TABLE IF NOT EXISTS user_preferences (
                    user_id TEXT PRIMARY KEY,
                    job_preferences TEXT DEFAULT '',
                    notification_new_jobs INTEGER DEFAULT 1,
                    notification_daily_digest INTEGER DEFAULT 1,
                    notification_weekly_summary INTEGER DEFAULT 0,
                    notification_ats_updates INTEGER DEFAULT 1,
                    notification_marketing_emails INTEGER DEFAULT 0,
                    visa_status TEXT,
                    experience_level TEXT,
                    target_roles_json TEXT DEFAULT '[]',
                    target_locations_json TEXT DEFAULT '[]',
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS user_alerts (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    company TEXT DEFAULT '',
                    location TEXT DEFAULT '',
                    salary TEXT DEFAULT '',
                    match_score INTEGER DEFAULT 0,
                    visa TEXT DEFAULT '',
                    message TEXT,
                    unread INTEGER DEFAULT 1,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_user_alerts_user ON user_alerts(user_id);
                CREATE INDEX IF NOT EXISTS idx_user_alerts_created ON user_alerts(created_at);

                CREATE TABLE IF NOT EXISTS user_alert_settings (
                    user_id TEXT PRIMARY KEY,
                    email_alerts INTEGER DEFAULT 1,
                    daily_digest INTEGER DEFAULT 1,
                    weekly_report INTEGER DEFAULT 0,
                    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS user_resumes (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    uploaded_at TEXT NOT NULL,
                    score INTEGER DEFAULT 0,
                    size_bytes INTEGER DEFAULT 0,
                    active INTEGER DEFAULT 0,
                    storage_path TEXT,
                    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_user_resumes_user ON user_resumes(user_id);

                CREATE TABLE IF NOT EXISTS user_applications (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    job_id TEXT,
                    company TEXT,
                    role TEXT,
                    status TEXT DEFAULT 'applied',
                    applied_at TEXT NOT NULL,
                    notes TEXT,
                    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_user_apps_user ON user_applications(user_id);
            """)
            # Idempotent migrations for existing DBs that pre-date the new columns.
            for table, column, ddl in (
                ("users",            "current_company",       "TEXT"),
                ("user_preferences", "target_roles_json",     "TEXT DEFAULT '[]'"),
                ("user_preferences", "target_locations_json", "TEXT DEFAULT '[]'"),
            ):
                try:
                    conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")
                except Exception:
                    pass  # column already exists
            conn.commit()
            logger.info(f"SQLite database initialized at {self.db_path}")
        finally:
            conn.close()

    # ─── Jobs ──────────────────────────────────────────────

    async def get_jobs(self, filters: dict = None, limit: int = 20, offset: int = 0) -> list[dict]:
        """Get jobs with optional filtering."""
        conn = self._get_conn()
        try:
            query = "SELECT * FROM jobs WHERE 1=1"
            params = []

            if filters:
                if filters.get("category"):
                    query += " AND category = ?"
                    params.append(filters["category"])
                if filters.get("source"):
                    query += " AND source = ?"
                    params.append(filters["source"])
                if filters.get("location"):
                    query += " AND location LIKE ?"
                    params.append(f"%{filters['location']}%")
                if filters.get("search"):
                    query += " AND (title LIKE ? OR company LIKE ? OR description LIKE ?)"
                    search_term = f"%{filters['search']}%"
                    params.extend([search_term, search_term, search_term])
                if filters.get("visa_only"):
                    query += " AND json_extract(visa_json, '$.visa_score') >= 30"

            query += " ORDER BY scraped_at DESC LIMIT ? OFFSET ?"
            params.extend([limit, offset])

            rows = conn.execute(query, params).fetchall()
            return [self._row_to_job_dict(row) for row in rows]
        finally:
            conn.close()

    async def get_job(self, job_id: str) -> Optional[dict]:
        """Get a single job by ID."""
        conn = self._get_conn()
        try:
            row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
            return self._row_to_job_dict(row) if row else None
        finally:
            conn.close()

    async def upsert_job(self, job_id: str, job_data: dict) -> None:
        """Insert or update a job."""
        conn = self._get_conn()
        try:
            conn.execute("""
                INSERT OR REPLACE INTO jobs
                (id, title, company, location, description, job_url,
                 category, job_type, experience_level, industry,
                 salary_json, visa_json, source, source_job_id,
                 posted_at, scraped_at, status, content_hash,
                 expires_at,
                 hiring_manager_name, hiring_manager_email, hiring_manager_linkedin,
                 data_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                job_id,
                job_data.get("title", ""),
                job_data.get("company", ""),
                job_data.get("location", ""),
                job_data.get("description", ""),
                job_data.get("job_url", ""),
                (
                    getattr(job_data.get("category"), "value", None)
                    or job_data.get("category")
                    or "Other"
                ),
                job_data.get("job_type", ""),
                job_data.get("experience_level", ""),
                job_data.get("industry", ""),
                json.dumps(job_data.get("salary") or {}),
                json.dumps(job_data.get("visa") or {}),
                (
                    getattr(job_data.get("source"), "value", None)
                    or job_data.get("source")
                    or "linkedin"
                ),
                job_data.get("source_job_id", ""),
                (
                    job_data.get("posted_at").isoformat()
                    if getattr(job_data.get("posted_at"), "isoformat", None)
                    else job_data.get("posted_at")
                ),
                (
                    job_data.get("scraped_at").isoformat()
                    if getattr(job_data.get("scraped_at"), "isoformat", None)
                    else (
                        job_data.get("scraped_at")
                        or datetime.utcnow().isoformat()
                    )
                ),
                job_data.get("status", "active"),
                job_data.get("content_hash", ""),
                (
                    job_data.get("expires_at").isoformat()
                    if getattr(job_data.get("expires_at"), "isoformat", None)
                    else job_data.get("expires_at")
                ),
                job_data.get("hiring_manager_name"),
                job_data.get("hiring_manager_email"),
                job_data.get("hiring_manager_linkedin"),
                _sqlite_pack_data_json(job_data),
            ))
            conn.commit()
        finally:
            conn.close()

    async def upsert_jobs_batch(self, jobs: list[dict]) -> int:
        """Batch upsert multiple jobs."""
        count = 0
        for job in jobs:
            job_id = job.get("id", "")
            if job_id:
                await self.upsert_job(job_id, job)
                count += 1
        return count

    async def get_existing_hashes(self) -> set:
        """Get all existing content hashes for deduplication."""
        conn = self._get_conn()
        try:
            rows = conn.execute("SELECT content_hash FROM jobs WHERE content_hash != ''").fetchall()
            return {row["content_hash"] for row in rows}
        finally:
            conn.close()

    async def count_jobs(self, filters: dict = None) -> int:
        """Count total jobs matching filters."""
        conn = self._get_conn()
        try:
            query = "SELECT COUNT(*) as cnt FROM jobs WHERE 1=1"
            params = []
            if filters:
                if filters.get("category"):
                    query += " AND category = ?"
                    params.append(filters["category"])
                if filters.get("source"):
                    query += " AND source = ?"
                    params.append(filters["source"])
                if filters.get("location"):
                    query += " AND location LIKE ?"
                    params.append(f"%{filters['location']}%")
            row = conn.execute(query, params).fetchone()
            return row["cnt"] if row else 0
        finally:
            conn.close()

    def _parse_json_field(self, raw: Optional[str], default):
        if not raw:
            return default
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return default

    def _row_to_job_dict(self, row: sqlite3.Row) -> dict:
        if row is None:
            return {}

        job = dict(row)
        salary = self._parse_json_field(job.pop("salary_json", None), {})
        visa = self._parse_json_field(job.pop("visa_json", None), {})
        extra = self._parse_json_field(job.pop("data_json", None), {})

        if isinstance(extra, dict):
            if extra.get("_placeup") == 2 and isinstance(extra.get("rest"), dict):
                extra = extra["rest"]
            job.update(extra)

        job["salary"] = salary
        job["visa"] = visa
        return job

    async def deactivate_old_jobs(self, days_old: int = 15) -> int:
        """Mark jobs as inactive if they are older than the specified days."""
        conn = self._get_conn()
        try:
            # We use scraped_at as the reference point
            conn.execute(
                "UPDATE jobs SET status = 'inactive' WHERE status = 'active' AND scraped_at < datetime('now', ?)",
                (f"-{days_old} days",)
            )
            changes = conn.total_changes
            conn.commit()
            return changes
        finally:
            conn.close()

    # ─── H1B Sponsors ──────────────────────────────────────

    async def get_h1b_sponsors(self, employer: str = None, limit: int = 20) -> list[dict]:
        """Get H1B sponsor records."""
        conn = self._get_conn()
        try:
            query = "SELECT * FROM h1b_sponsors WHERE 1=1"
            params = []
            if employer:
                query += " AND employer_name LIKE ?"
                params.append(f"%{employer}%")
            query += " ORDER BY total_petitions DESC LIMIT ?"
            params.append(limit)

            rows = conn.execute(query, params).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    async def upsert_h1b_sponsors(self, sponsors: list[dict]) -> int:
        """Batch upsert H1B sponsor records."""
        conn = self._get_conn()
        try:
            count = 0
            for sponsor in sponsors:
                conn.execute("""
                    INSERT OR REPLACE INTO h1b_sponsors
                    (id, employer_name, city, state, zip_code,
                     initial_approvals, initial_denials,
                     continuing_approvals, continuing_denials,
                     total_petitions, fiscal_year)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    sponsor.get("id", ""),
                    sponsor.get("employer_name", ""),
                    sponsor.get("city", ""),
                    sponsor.get("state", ""),
                    sponsor.get("zip_code", ""),
                    sponsor.get("initial_approvals", 0),
                    sponsor.get("initial_denials", 0),
                    sponsor.get("continuing_approvals", 0),
                    sponsor.get("continuing_denials", 0),
                    sponsor.get("total_petitions", 0),
                    sponsor.get("fiscal_year", 0),
                ))
                count += 1
            conn.commit()
            return count
        finally:
            conn.close()

    # ─── Contacts ─────────────────────────────────────────

    async def get_contacts(self, company=None, job_id=None, limit=50):
        """Get cached contacts, optionally filtered by company or job."""
        conn = self._get_conn()
        try:
            query = "SELECT * FROM contacts WHERE 1=1"
            params = []
            if company:
                query += " AND lower(company) = lower(?)"
                params.append(company)
            if job_id:
                query += " AND related_job_id = ?"
                params.append(job_id)
            query += " ORDER BY discovered_at DESC LIMIT ?"
            params.append(limit)
            rows = conn.execute(query, params).fetchall()
            return [self._row_to_contact_dict(row) for row in rows]
        finally:
            conn.close()

    async def upsert_contacts(self, contacts):
        """Insert or update a batch of contacts (idempotent on id)."""
        if not contacts:
            return 0
        conn = self._get_conn()
        try:
            count = 0
            for c in contacts:
                conn.execute("""
                    INSERT OR REPLACE INTO contacts (
                        id, full_name, first_name, last_name, title, role,
                        company, company_domain, email, linkedin_url,
                        linkedin_search_url, source, confidence, related_job_id,
                        discovered_at, last_verified_at, source_payload_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    c.get("id", ""),
                    c.get("full_name"),
                    c.get("first_name"),
                    c.get("last_name"),
                    c.get("title"),
                    c.get("role", "other"),
                    c.get("company", ""),
                    c.get("company_domain"),
                    (c.get("email") or "").lower() or None,
                    c.get("linkedin_url"),
                    c.get("linkedin_search_url"),
                    c.get("source", "unknown"),
                    c.get("confidence", "unknown"),
                    c.get("related_job_id"),
                    c.get("discovered_at"),
                    c.get("last_verified_at"),
                    json.dumps(c.get("source_payload") or {}),
                ))
                count += 1
            conn.commit()
            return count
        finally:
            conn.close()

    async def count_contacts(self, company=None):
        conn = self._get_conn()
        try:
            if company:
                row = conn.execute(
                    "SELECT COUNT(*) AS n FROM contacts WHERE lower(company) = lower(?)",
                    (company,),
                ).fetchone()
            else:
                row = conn.execute("SELECT COUNT(*) AS n FROM contacts").fetchone()
            return int(row["n"]) if row else 0
        finally:
            conn.close()

    def _row_to_contact_dict(self, row):
        d = dict(row)
        try:
            d["source_payload"] = json.loads(d.pop("source_payload_json") or "{}")
        except Exception:
            d["source_payload"] = {}
        return d

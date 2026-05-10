"""SQLAlchemy schema for the central PostgreSQL backend."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )


class IngestRun(Base):
    __tablename__ = "ingest_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_name: Mapped[str] = mapped_column(String(120), nullable=False)
    pipeline_name: Mapped[str] = mapped_column(String(120), nullable=False)
    schedule_type: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="running")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    records_seen: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    records_staged: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    records_inserted: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    records_updated: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    records_failed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text)


class StagingRecord(Base):
    __tablename__ = "staging_records"
    __table_args__ = (
        UniqueConstraint("source_name", "record_hash", name="uq_staging_source_hash"),
        Index("ix_staging_source_seen", "source_name", "last_seen_at"),
        Index("ix_staging_run", "ingest_run_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ingest_run_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("ingest_runs.id"))
    source_name: Mapped[str] = mapped_column(String(120), nullable=False)
    source_record_id: Mapped[str | None] = mapped_column(String(240))
    source_url: Mapped[str | None] = mapped_column(Text)
    record_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    normalized_payload: Mapped[dict | None] = mapped_column(JSONB)
    validation_status: Mapped[str] = mapped_column(String(30), default="pending", nullable=False)
    validation_errors: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)


class Company(Base, TimestampMixin):
    __tablename__ = "companies"
    __table_args__ = (UniqueConstraint("normalized_name", name="uq_companies_normalized_name"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(300), nullable=False)
    domain: Mapped[str | None] = mapped_column(String(255))
    linkedin_url: Mapped[str | None] = mapped_column(Text)
    website_url: Mapped[str | None] = mapped_column(Text)

    jobs: Mapped[list["Job"]] = relationship(back_populates="company")


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (
        UniqueConstraint("source_name", "source_job_id", name="uq_jobs_source_job_id"),
        UniqueConstraint("content_hash", name="uq_jobs_content_hash"),
        Index("ix_jobs_company", "company_id"),
        Index("ix_jobs_status_seen", "status", "last_seen_at"),
        Index("ix_jobs_source", "source_name"),
        Index("ix_jobs_visa", "visa_score"),
    )

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    company_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"))
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    normalized_title: Mapped[str | None] = mapped_column(String(500))
    location: Mapped[str | None] = mapped_column(String(300))
    country: Mapped[str | None] = mapped_column(String(80))
    category: Mapped[str | None] = mapped_column(String(120))
    source_name: Mapped[str] = mapped_column(String(120), nullable=False)
    source_job_id: Mapped[str | None] = mapped_column(String(240))
    source_url: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    employment_type: Mapped[str | None] = mapped_column(String(120))
    remote_type: Mapped[str | None] = mapped_column(String(120))
    salary_min: Mapped[float | None] = mapped_column(Numeric(12, 2))
    salary_max: Mapped[float | None] = mapped_column(Numeric(12, 2))
    currency: Mapped[str | None] = mapped_column(String(12))
    visa_opt: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    visa_stem_opt: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    visa_h1b: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    h1b_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    visa_score: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="active", nullable=False)
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    extra_metadata: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)

    company: Mapped[Company | None] = relationship(back_populates="jobs")


class Contact(Base):
    __tablename__ = "contacts"
    __table_args__ = (
        UniqueConstraint("email", name="uq_contacts_email"),
        UniqueConstraint("linkedin_url", name="uq_contacts_linkedin_url"),
        Index("ix_contacts_company", "company_id"),
    )

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    company_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"))
    full_name: Mapped[str | None] = mapped_column(String(300))
    title: Mapped[str | None] = mapped_column(String(300))
    email: Mapped[str | None] = mapped_column(String(320))
    linkedin_url: Mapped[str | None] = mapped_column(Text)
    source_name: Mapped[str | None] = mapped_column(String(120))
    confidence: Mapped[str | None] = mapped_column(String(80))
    related_job_id: Mapped[str | None] = mapped_column(String(80), ForeignKey("jobs.id"))
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class H1BSponsor(Base):
    __tablename__ = "h1b_sponsors"
    __table_args__ = (Index("ix_h1b_employer", "employer_name"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    employer_name: Mapped[str] = mapped_column(String(300), nullable=False)
    city: Mapped[str | None] = mapped_column(String(120))
    state: Mapped[str | None] = mapped_column(String(40))
    zip_code: Mapped[str | None] = mapped_column(String(40))
    initial_approvals: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    initial_denials: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    continuing_approvals: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    continuing_denials: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_petitions: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    fiscal_year: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    data_json: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "employer_name": self.employer_name,
            "city": self.city or "",
            "state": self.state or "",
            "zip_code": self.zip_code or "",
            "initial_approvals": self.initial_approvals,
            "initial_denials": self.initial_denials,
            "continuing_approvals": self.continuing_approvals,
            "continuing_denials": self.continuing_denials,
            "total_petitions": self.total_petitions,
            "fiscal_year": self.fiscal_year,
            "data_json": self.data_json or {},
        }

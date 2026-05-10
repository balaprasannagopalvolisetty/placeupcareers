"""initial ETL schema

Revision ID: 20260510_0001
Revises:
Create Date: 2026-05-10
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260510_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute('create extension if not exists "pgcrypto"')

    op.create_table(
        "ingest_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("source_name", sa.String(120), nullable=False),
        sa.Column("pipeline_name", sa.String(120), nullable=False),
        sa.Column("schedule_type", sa.String(40), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="running"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("records_seen", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("records_staged", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("records_inserted", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("records_updated", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("records_failed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text()),
    )

    op.create_table(
        "staging_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("ingest_run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("ingest_runs.id")),
        sa.Column("source_name", sa.String(120), nullable=False),
        sa.Column("source_record_id", sa.String(240)),
        sa.Column("source_url", sa.Text()),
        sa.Column("record_hash", sa.String(128), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("normalized_payload", postgresql.JSONB()),
        sa.Column("validation_status", sa.String(30), nullable=False, server_default="pending"),
        sa.Column("validation_errors", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("source_name", "record_hash", name="uq_staging_source_hash"),
    )
    op.create_index("ix_staging_source_seen", "staging_records", ["source_name", "last_seen_at"])
    op.create_index("ix_staging_run", "staging_records", ["ingest_run_id"])

    op.create_table(
        "companies",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(300), nullable=False),
        sa.Column("normalized_name", sa.String(300), nullable=False),
        sa.Column("domain", sa.String(255)),
        sa.Column("linkedin_url", sa.Text()),
        sa.Column("website_url", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("normalized_name", name="uq_companies_normalized_name"),
    )

    op.create_table(
        "jobs",
        sa.Column("id", sa.String(80), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("companies.id")),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("normalized_title", sa.String(500)),
        sa.Column("location", sa.String(300)),
        sa.Column("country", sa.String(80)),
        sa.Column("category", sa.String(120)),
        sa.Column("source_name", sa.String(120), nullable=False),
        sa.Column("source_job_id", sa.String(240)),
        sa.Column("source_url", sa.Text()),
        sa.Column("description", sa.Text()),
        sa.Column("employment_type", sa.String(120)),
        sa.Column("remote_type", sa.String(120)),
        sa.Column("salary_min", sa.Numeric(12, 2)),
        sa.Column("salary_max", sa.Numeric(12, 2)),
        sa.Column("currency", sa.String(12)),
        sa.Column("visa_opt", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("visa_stem_opt", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("visa_h1b", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("h1b_verified", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("visa_score", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("content_hash", sa.String(128), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="active"),
        sa.Column("posted_at", sa.DateTime(timezone=True)),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("extra_metadata", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.UniqueConstraint("source_name", "source_job_id", name="uq_jobs_source_job_id"),
        sa.UniqueConstraint("content_hash", name="uq_jobs_content_hash"),
    )
    op.create_index("ix_jobs_company", "jobs", ["company_id"])
    op.create_index("ix_jobs_status_seen", "jobs", ["status", "last_seen_at"])
    op.create_index("ix_jobs_source", "jobs", ["source_name"])
    op.create_index("ix_jobs_visa", "jobs", ["visa_score"])

    op.create_table(
        "contacts",
        sa.Column("id", sa.String(80), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("companies.id")),
        sa.Column("full_name", sa.String(300)),
        sa.Column("title", sa.String(300)),
        sa.Column("email", sa.String(320)),
        sa.Column("linkedin_url", sa.Text()),
        sa.Column("source_name", sa.String(120)),
        sa.Column("confidence", sa.String(80)),
        sa.Column("related_job_id", sa.String(80), sa.ForeignKey("jobs.id")),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("last_verified_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("email", name="uq_contacts_email"),
        sa.UniqueConstraint("linkedin_url", name="uq_contacts_linkedin_url"),
    )
    op.create_index("ix_contacts_company", "contacts", ["company_id"])

    op.create_table(
        "h1b_sponsors",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("employer_name", sa.String(300), nullable=False),
        sa.Column("city", sa.String(120)),
        sa.Column("state", sa.String(40)),
        sa.Column("zip_code", sa.String(40)),
        sa.Column("initial_approvals", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("initial_denials", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("continuing_approvals", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("continuing_denials", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_petitions", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("fiscal_year", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("data_json", postgresql.JSONB(), nullable=False, server_default="{}"),
    )
    op.create_index("ix_h1b_employer", "h1b_sponsors", ["employer_name"])


def downgrade() -> None:
    op.drop_index("ix_h1b_employer", table_name="h1b_sponsors")
    op.drop_table("h1b_sponsors")
    op.drop_index("ix_contacts_company", table_name="contacts")
    op.drop_table("contacts")
    op.drop_index("ix_jobs_visa", table_name="jobs")
    op.drop_index("ix_jobs_source", table_name="jobs")
    op.drop_index("ix_jobs_status_seen", table_name="jobs")
    op.drop_index("ix_jobs_company", table_name="jobs")
    op.drop_table("jobs")
    op.drop_table("companies")
    op.drop_index("ix_staging_run", table_name="staging_records")
    op.drop_index("ix_staging_source_seen", table_name="staging_records")
    op.drop_table("staging_records")
    op.drop_table("ingest_runs")

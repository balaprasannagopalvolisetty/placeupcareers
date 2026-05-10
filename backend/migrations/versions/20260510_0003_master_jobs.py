"""master jobs dedupe table

Revision ID: 20260510_0003
Revises: 20260510_0002
Create Date: 2026-05-10
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260510_0003"
down_revision = "20260510_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute('create extension if not exists "pgcrypto"')
    op.create_table(
        "master_jobs",
        sa.Column("id", sa.String(120), primary_key=True),
        sa.Column("canonical_key", sa.String(128), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("company", sa.String(300), nullable=False, server_default=""),
        sa.Column("location", sa.String(300)),
        sa.Column("country", sa.String(80)),
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
        sa.Column("status", sa.String(30), nullable=False, server_default="active"),
        sa.Column("posted_at", sa.DateTime(timezone=True)),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("source_priority", sa.Integer(), nullable=False, server_default="50"),
        sa.Column("merged_sources", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("extra_metadata", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.UniqueConstraint("canonical_key", name="uq_master_jobs_canonical_key"),
    )
    op.create_index("ix_master_jobs_status_seen", "master_jobs", ["status", "last_seen_at"])
    op.create_index("ix_master_jobs_company", "master_jobs", ["company"])
    op.create_index("ix_master_jobs_source", "master_jobs", ["source_name"])
    op.create_index("ix_master_jobs_visa", "master_jobs", ["visa_score"])


def downgrade() -> None:
    op.drop_index("ix_master_jobs_visa", table_name="master_jobs")
    op.drop_index("ix_master_jobs_source", table_name="master_jobs")
    op.drop_index("ix_master_jobs_company", table_name="master_jobs")
    op.drop_index("ix_master_jobs_status_seen", table_name="master_jobs")
    op.drop_table("master_jobs")

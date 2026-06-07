"""Add global visa sponsor directory.

Revision ID: 20260606_0002
Revises: 20260521_0001
Create Date: 2026-06-06
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260606_0002"
down_revision = "20260521_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "visa_sponsors",
        sa.Column("id", sa.String(length=96), nullable=False),
        sa.Column("employer_name", sa.String(length=400), nullable=False),
        sa.Column("normalized_name", sa.String(length=400), nullable=False),
        sa.Column("country", sa.String(length=8), nullable=False),
        sa.Column("country_name", sa.String(length=120), nullable=True),
        sa.Column("visa_route", sa.String(length=160), nullable=True),
        sa.Column("city", sa.String(length=160), nullable=True),
        sa.Column("region", sa.String(length=160), nullable=True),
        sa.Column("postal_code", sa.String(length=80), nullable=True),
        sa.Column("status", sa.String(length=80), nullable=False, server_default="Active"),
        sa.Column("approvals", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("denials", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_petitions", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("fiscal_year", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("source_name", sa.String(length=120), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("source_record_id", sa.String(length=180), nullable=False),
        sa.Column("last_verified_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("data_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("country", "source_name", "source_record_id", name="uq_visa_sponsor_source_record"),
    )
    op.create_index("ix_visa_sponsors_country_employer", "visa_sponsors", ["country", "employer_name"])
    op.create_index("ix_visa_sponsors_country_route", "visa_sponsors", ["country", "visa_route"])
    op.create_index("ix_visa_sponsors_verified", "visa_sponsors", ["country", "last_verified_at"])


def downgrade() -> None:
    op.drop_index("ix_visa_sponsors_verified", table_name="visa_sponsors")
    op.drop_index("ix_visa_sponsors_country_route", table_name="visa_sponsors")
    op.drop_index("ix_visa_sponsors_country_employer", table_name="visa_sponsors")
    op.drop_table("visa_sponsors")

"""Add production contact enrichment fields.

Revision ID: 20260510_0004
Revises: 20260510_0003
Create Date: 2026-05-10
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260510_0004"
down_revision = "20260510_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    existing = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("contacts")}
    if "first_name" not in existing:
        op.add_column("contacts", sa.Column("first_name", sa.String(length=150), nullable=True))
    if "last_name" not in existing:
        op.add_column("contacts", sa.Column("last_name", sa.String(length=150), nullable=True))
    if "role" not in existing:
        op.add_column("contacts", sa.Column("role", sa.String(length=80), nullable=True))
    if "company_domain" not in existing:
        op.add_column("contacts", sa.Column("company_domain", sa.String(length=255), nullable=True))
    if "linkedin_search_url" not in existing:
        op.add_column("contacts", sa.Column("linkedin_search_url", sa.Text(), nullable=True))
    if "source_payload" not in existing:
        op.add_column(
            "contacts",
            sa.Column(
                "source_payload",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
                server_default=sa.text("'{}'::jsonb"),
            ),
        )
        op.alter_column("contacts", "source_payload", server_default=None)


def downgrade() -> None:
    op.drop_column("contacts", "source_payload")
    op.drop_column("contacts", "linkedin_search_url")
    op.drop_column("contacts", "company_domain")
    op.drop_column("contacts", "role")
    op.drop_column("contacts", "last_name")
    op.drop_column("contacts", "first_name")

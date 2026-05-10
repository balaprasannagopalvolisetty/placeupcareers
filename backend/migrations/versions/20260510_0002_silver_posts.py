"""silver posts table for Firestore bronze loader

Revision ID: 20260510_0002
Revises: 20260510_0001
Create Date: 2026-05-10
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260510_0002"
down_revision = "20260510_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "silver_posts",
        sa.Column("job_id", sa.BigInteger(), primary_key=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("organization", sa.Text()),
        sa.Column("organization_url", sa.Text()),
        sa.Column("job_url", sa.Text()),
        sa.Column("source_type", sa.Text()),
        sa.Column("source", sa.Text()),
        sa.Column("source_domain", sa.Text()),
        sa.Column("employer_domain", sa.Text()),
        sa.Column("date_posted", sa.DateTime(timezone=True)),
        sa.Column("date_created", sa.DateTime(timezone=True)),
        sa.Column("date_valid_through", sa.DateTime(timezone=True)),
        sa.Column("location_type", sa.Text()),
        sa.Column("employment_type", postgresql.ARRAY(sa.Text())),
        sa.Column("remote_flag", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("city", sa.Text()),
        sa.Column("county", sa.Text()),
        sa.Column("region", sa.Text()),
        sa.Column("country", sa.Text()),
        sa.Column("full_location", sa.Text()),
        sa.Column("timezone", sa.Text()),
        sa.Column("latitude", sa.Float()),
        sa.Column("longitude", sa.Float()),
        sa.Column("street_address", sa.Text()),
        sa.Column("postal_code", sa.Text()),
        sa.Column("address_locality", sa.Text()),
        sa.Column("address_region", sa.Text()),
        sa.Column("address_country", sa.Text()),
        sa.Column("description_text", sa.Text()),
        sa.Column("locations_raw", postgresql.JSONB()),
        sa.Column("salary_raw", postgresql.JSONB()),
        sa.Column("record_source", sa.Text()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("silver_created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("silver_updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_silver_posts_active_posted", "silver_posts", ["is_active", "date_posted"])
    op.create_index("ix_silver_posts_location", "silver_posts", ["country", "region", "city"])
    op.create_index("ix_silver_posts_organization", "silver_posts", ["organization"])
    op.create_index("ix_silver_posts_source", "silver_posts", ["source"])


def downgrade() -> None:
    op.drop_index("ix_silver_posts_source", table_name="silver_posts")
    op.drop_index("ix_silver_posts_organization", table_name="silver_posts")
    op.drop_index("ix_silver_posts_location", table_name="silver_posts")
    op.drop_index("ix_silver_posts_active_posted", table_name="silver_posts")
    op.drop_table("silver_posts")

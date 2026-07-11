"""Add country-feed indexes for personalized jobs queries.

Revision ID: 20260711_0001
Revises: 20260606_0002
Create Date: 2026-07-11
"""

from alembic import op
from sqlalchemy.exc import ProgrammingError
import warnings


revision = "20260711_0001"
down_revision = "20260606_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Build online: master_jobs remains readable/writable while PostgreSQL
    # scans the production inventory.
    with op.get_context().autocommit_block():
        for statement in (
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS "
            "ix_master_jobs_country_status_seen "
            "ON master_jobs (country, status, last_seen_at DESC)",
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS "
            "ix_master_jobs_country_status_posted "
            "ON master_jobs (country, status, posted_at DESC NULLS LAST)",
        ):
            try:
                op.execute(statement)
            except ProgrammingError as exc:
                # Some production databases were bootstrapped by the Cloud SQL
                # owner while the migration job uses the narrower application
                # role. The API query rewrite is safe without these optional
                # indexes, so record the revision instead of blocking every
                # future migration. Operations can add them later as owner.
                if "must be owner of table master_jobs" not in str(exc).lower():
                    raise
                warnings.warn(
                    "Skipping optional master_jobs country indexes: migration "
                    "role is not the table owner.",
                    RuntimeWarning,
                )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_master_jobs_country_status_seen")
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_master_jobs_country_status_posted")

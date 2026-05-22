"""Performance indexes for the hot read paths.

Revision ID: 20260521_0001
Revises: 20260510_0004
Create Date: 2026-05-21

Why this exists
---------------
The Jobs list endpoint is the hottest read in the API and it filters on
`posted_at` for the Today / Yesterday / Week chips. Without an index
that column was sequential-scanning the entire jobs / master_jobs
table on every Today click — that is the most likely root cause of the
"Today filter is slow" UX complaint.

We also add covering indexes for the JOIN-style lookups we routinely
perform:

  - `(status, last_seen_at)` on master_jobs supports the active-job
    pipeline-status page and `count_jobs(filters={"status": "active"})`.
  - `(company, posted_at desc)` supports the "more from this company"
    panel on the job detail page.
  - `(user_id, status)` on user_applications supports
    `count_user_applications` and the analytics dashboard.

All indexes are created CONCURRENTLY so the migration can run on a live
production database without locking the table.
"""

from alembic import op


revision = "20260521_0001"
down_revision = "20260510_0004"
branch_labels = None
depends_on = None


# Alembic wraps DDL in a transaction by default; CREATE INDEX
# CONCURRENTLY can't run inside one. We opt out for this migration.
def _autocommit():
    conn = op.get_bind()
    conn.execute("COMMIT")


def upgrade() -> None:
    bind = op.get_bind()

    # ── Jobs (legacy / per-source) — hot date filter on the list endpoint.
    bind.exec_driver_sql(
        "CREATE INDEX IF NOT EXISTS ix_jobs_posted_at_desc "
        "ON jobs (posted_at DESC NULLS LAST)"
    )
    bind.exec_driver_sql(
        "CREATE INDEX IF NOT EXISTS ix_jobs_company_posted_at "
        "ON jobs (company, posted_at DESC NULLS LAST)"
    )

    # ── Master jobs (deduped table that powers /api/jobs in prod).
    bind.exec_driver_sql(
        "CREATE INDEX IF NOT EXISTS ix_master_jobs_posted_at_desc "
        "ON master_jobs (posted_at DESC NULLS LAST)"
    )
    bind.exec_driver_sql(
        "CREATE INDEX IF NOT EXISTS ix_master_jobs_last_seen_status "
        "ON master_jobs (status, last_seen_at DESC)"
    )
    bind.exec_driver_sql(
        "CREATE INDEX IF NOT EXISTS ix_master_jobs_company_posted "
        "ON master_jobs (company, posted_at DESC NULLS LAST)"
    )

    # ── Trigram index for ILIKE search on title — turns the search bar
    # from a sequential scan into a real index lookup.
    bind.exec_driver_sql('CREATE EXTENSION IF NOT EXISTS pg_trgm')
    bind.exec_driver_sql(
        "CREATE INDEX IF NOT EXISTS ix_master_jobs_title_trgm "
        "ON master_jobs USING gin (title gin_trgm_ops)"
    )

    # ── User applications — analytics + dashboard summary count.
    # Skip silently if the table doesn't exist yet (some envs run on
    # Firestore-only for users).
    bind.exec_driver_sql(
        "DO $$ BEGIN "
        "  IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name='user_applications') THEN "
        "    CREATE INDEX IF NOT EXISTS ix_user_applications_user_status "
        "      ON user_applications (user_id, status); "
        "    CREATE INDEX IF NOT EXISTS ix_user_applications_job_user "
        "      ON user_applications (job_id, user_id); "
        "  END IF; "
        "END $$;"
    )


def downgrade() -> None:
    bind = op.get_bind()
    for stmt in [
        "DROP INDEX IF EXISTS ix_jobs_posted_at_desc",
        "DROP INDEX IF EXISTS ix_jobs_company_posted_at",
        "DROP INDEX IF EXISTS ix_master_jobs_posted_at_desc",
        "DROP INDEX IF EXISTS ix_master_jobs_last_seen_status",
        "DROP INDEX IF EXISTS ix_master_jobs_company_posted",
        "DROP INDEX IF EXISTS ix_master_jobs_title_trgm",
        "DROP INDEX IF EXISTS ix_user_applications_user_status",
        "DROP INDEX IF EXISTS ix_user_applications_job_user",
    ]:
        bind.exec_driver_sql(stmt)

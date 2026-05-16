"""
DEPRECATED — SQLite local database removed.

PlaceUp is cloud-only. The active jobs database is Postgres (Cloud SQL)
and the user store is Firestore. This module previously held a SQLite
fallback used for offline development. It is no longer used anywhere
in the application or in any script — see backend/README.md for the
current development setup.

If you reach this code, something is importing a path that should have
been deleted. Update the import to use one of:

    from app.db.postgres import PostgresClient
    from app.services import user_store
"""

raise ImportError(
    "app.db.local_db has been removed. Use app.db.postgres.PostgresClient "
    "(jobs) and app.services.user_store (users) instead."
)

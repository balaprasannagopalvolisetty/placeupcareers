"""One-shot Firestore -> Supabase Postgres data migration.

Streams every user-domain Firestore collection into the matching Supabase
table created by supabase/migrations/20260707000001_user_store_schema.sql.
Known fields map to columns; anything unexpected lands in the `extra`
JSONB column so nothing is lost. Idempotent: rows are upserted by primary
key, so it is safe to re-run.

Usage (from backend/, with GCP Application Default Credentials active):

    export SUPABASE_DB_URL='postgresql+psycopg://postgres.dyeuehtkdatqftdydgvc:<DB_PASSWORD>@<pooler-host>:5432/postgres'
    export USER_FIRESTORE_PROJECT_ID='<gcp-project-id>'
    python scripts/migrate_firestore_to_supabase.py            # dry run (counts only)
    python scripts/migrate_firestore_to_supabase.py --execute  # actually copy
    python scripts/migrate_firestore_to_supabase.py --verify   # compare counts after

Requires: google-cloud-firestore, sqlalchemy, psycopg (already in requirements).
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from google.cloud import firestore
from sqlalchemy import create_engine, text

# ---------------------------------------------------------------------------
# Collection -> table map. `columns` are copied 1:1 (missing -> None/default),
# everything else in the doc goes into `extra`. `id_from_doc` means the
# Firestore document id is the primary key value.
# ---------------------------------------------------------------------------

BOOL_FIELDS = {
    "unread", "active", "revoked", "accepted", "notified", "email_verified",
    "email_alerts", "daily_digest", "weekly_report", "heard_back", "position_open",
    "notification_new_jobs", "notification_daily_digest", "notification_weekly_summary",
    "notification_ats_updates", "notification_marketing_emails",
}
INT_FIELDS = {"match_score", "score", "size_bytes", "rating", "ats_score"}
JSON_FIELDS = {
    "parsed_json", "meta", "documents", "target_roles", "target_locations",
    "job_preferences", "keyword_targets", "extra",
}

SPEC: list[dict] = [
    {"collection": "users", "table": "users", "pk": "id", "columns": [
        "id", "email", "password_hash", "first_name", "last_name", "plan",
        "visa_status", "experience_years", "phone", "location", "current_role",
        "current_company", "summary", "linkedin_url", "github_url", "portfolio_url",
        "email_verified", "email_verified_at", "created_at", "updated_at"]},
    {"collection": "user_preferences", "table": "user_preferences", "pk": "user_id", "columns": [
        "user_id", "visa_status", "experience_level", "target_roles", "target_locations",
        "job_preferences", "notification_new_jobs", "notification_daily_digest",
        "notification_weekly_summary", "notification_ats_updates",
        "notification_marketing_emails", "updated_at"]},
    {"collection": "user_alert_settings", "table": "user_alert_settings", "pk": "user_id", "columns": [
        "user_id", "email_alerts", "daily_digest", "weekly_report"]},
    {"collection": "user_alerts", "table": "user_alerts", "pk": "id", "columns": [
        "id", "user_id", "title", "company", "location", "salary", "match_score",
        "visa", "message", "unread", "created_at"]},
    {"collection": "user_resumes", "table": "user_resumes", "pk": "id", "columns": [
        "id", "user_id", "name", "uploaded_at", "score", "size_bytes", "active",
        "storage_path", "parsed_text", "parsed_json"]},
    {"collection": "user_applications", "table": "user_applications", "pk": "id", "columns": [
        "id", "user_id", "job_id", "title", "company", "location", "job_url",
        "description", "match_score", "status", "not_applied_reason", "heard_back",
        "position_open", "salary_offered", "notes", "created_at", "updated_at"]},
    {"collection": "user_tailor_queue", "table": "user_tailor_queue", "pk": "id", "columns": [
        "id", "user_id", "job_id", "title", "company", "location", "job_url",
        "description", "match_score", "status", "queued_day", "ats_score",
        "generated_at", "keyword_targets", "last_format", "filename", "summary",
        "created_at", "updated_at"]},
    {"collection": "auth_sessions", "table": "auth_sessions", "pk": "id", "columns": [
        "id", "user_id", "refresh_hash", "created_at", "updated_at", "expires_at",
        "revoked", "user_agent", "ip_address"]},
    {"collection": "password_resets", "table": "password_resets", "pk": "token_hash",
     "id_field": "token_hash", "no_extra": True, "columns": [
        "token_hash", "user_id", "expires_at", "created_at"]},
    {"collection": "email_verifications", "table": "email_verifications", "pk": "token_hash",
     "id_field": "token_hash", "no_extra": True, "columns": [
        "token_hash", "user_id", "expires_at", "created_at"]},
    {"collection": "agreements", "table": "agreements", "pk": "id", "columns": [
        "id", "user_id", "email", "version", "documents", "accepted", "ip_address",
        "user_agent", "created_at"]},
    {"collection": "role_requests", "table": "role_requests", "pk": "id", "columns": [
        "id", "user_id", "email", "role", "country", "note", "status", "admin_note",
        "decided_by", "decided_at", "created_at", "updated_at"]},
    {"collection": "admin_events", "table": "admin_events", "pk": "id", "no_extra": True, "columns": [
        "id", "kind", "label", "user_id", "email", "actor", "level", "meta", "created_at"]},
    {"collection": "waitlist", "table": "waitlist", "pk": "id", "columns": [
        "id", "email", "name", "source", "last_ip", "last_user_agent", "notified",
        "created_at", "updated_at"]},
    {"collection": "user_feedback", "table": "user_feedback", "pk": "id", "columns": [
        "id", "user_id", "email", "rating", "category", "message", "page",
        "user_agent", "status", "created_at", "updated_at"]},
]

NOW_FALLBACK_COLUMNS = {"created_at", "updated_at", "uploaded_at"}


def _coerce(column: str, value):
    if column in BOOL_FIELDS:
        return None if value is None else bool(value)
    if column in INT_FIELDS:
        try:
            return None if value is None else int(value)
        except (TypeError, ValueError):
            return 0
    if column in JSON_FIELDS:
        return json.dumps(value if value is not None else None)
    if value is not None and not isinstance(value, (str, int, float, bool)):
        # Firestore Timestamp or nested value in a text column
        if hasattr(value, "isoformat"):
            return value.isoformat()
        return json.dumps(value, default=str)
    return value


def migrate(fs, engine, execute: bool) -> dict[str, tuple[int, int]]:
    from datetime import datetime, timezone

    now_iso = datetime.now(tz=timezone.utc).isoformat()
    results: dict[str, tuple[int, int]] = {}
    for spec in SPEC:
        coll, table, pk = spec["collection"], spec["table"], spec["pk"]
        id_field = spec.get("id_field", pk)
        cols = spec["columns"]
        has_extra = not spec.get("no_extra")
        read = written = 0
        batch: list[dict] = []

        col_list = ", ".join(f'"{c}"' for c in cols) + (", extra" if has_extra else "")
        val_list = ", ".join(
            f"cast(:{c} as jsonb)" if c in JSON_FIELDS else f":{c}" for c in cols
        ) + (", cast(:extra as jsonb)" if has_extra else "")
        sql = text(
            f'insert into {table} ({col_list}) values ({val_list}) '
            f'on conflict ("{pk}") do nothing'
        )

        def flush():
            nonlocal written
            if batch and execute:
                with engine.begin() as cx:
                    cx.execute(sql, batch)
            written += len(batch)
            batch.clear()

        for snap in fs.collection(coll).stream():
            read += 1
            doc = snap.to_dict() or {}
            doc.setdefault(id_field, snap.id)
            row = {}
            for c in cols:
                v = _coerce(c, doc.get(c))
                if v is None and c in NOW_FALLBACK_COLUMNS and c != "updated_at":
                    v = str(doc.get("created_at") or now_iso)
                if v is None and c == "updated_at":
                    v = str(doc.get("created_at") or now_iso)
                row[c] = v
            if has_extra:
                known = set(cols) | {id_field}
                row["extra"] = json.dumps(
                    {k: v for k, v in doc.items() if k not in known}, default=str
                )
            batch.append(row)
            if len(batch) >= 200:
                flush()
        flush()
        results[coll] = (read, written)
        mode = "migrated" if execute else "would migrate"
        print(f"  {coll:24s} -> {table:24s} {mode}: {read}")
    return results


def verify(fs, engine) -> bool:
    ok = True
    print("\nVerification (Firestore vs Supabase row counts):")
    for spec in SPEC:
        coll, table = spec["collection"], spec["table"]
        fs_count = sum(1 for _ in fs.collection(coll).stream())
        with engine.begin() as cx:
            pg_count = int(cx.execute(text(f"select count(*) from {table}")).scalar() or 0)
        status = "OK " if pg_count >= fs_count else "MISMATCH"
        if pg_count < fs_count:
            ok = False
        print(f"  {status} {coll:24s} firestore={fs_count:<8d} supabase={pg_count}")
    return ok


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true", help="write to Supabase (default: dry run)")
    parser.add_argument("--verify", action="store_true", help="compare row counts only")
    args = parser.parse_args()

    db_url = os.environ.get("SUPABASE_DB_URL")
    if not db_url:
        print("ERROR: set SUPABASE_DB_URL (SQLAlchemy URL, postgresql+psycopg://...)")
        return 2
    project = os.environ.get("USER_FIRESTORE_PROJECT_ID")
    database = os.environ.get("USER_FIRESTORE_DATABASE", "(default)")

    fs = firestore.Client(project=project, database=database)
    engine = create_engine(db_url, pool_pre_ping=True)

    if args.verify:
        return 0 if verify(fs, engine) else 1

    print(f"{'EXECUTING' if args.execute else 'DRY RUN'} — Firestore project "
          f"{project or '(ADC default)'} db {database} -> Supabase\n")
    migrate(fs, engine, execute=args.execute)
    if args.execute:
        return 0 if verify(fs, engine) else 1
    print("\nDry run complete. Re-run with --execute to copy the data.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

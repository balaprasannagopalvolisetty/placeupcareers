# PlaceUp — GCloud → Supabase Migration Runbook

> CURRENT DECISION (2026-07-07): this is now a legacy/full-exit runbook.
> For the active hybrid architecture, follow `HYBRID_ARCHITECTURE.md`:
> migrate the jobs database to Supabase, keep Firebase Hosting and Firestore
> for client/user data, and skip the Firestore/user-store cutover phases here.

Target: everything in Supabase project `dyeuehtkdatqftdydgvc`, then a safe,
ordered teardown of GCP so billing stops. **Follow the phases in order —
do not delete anything on GCP until Phase 6 verification passes.**

What moves where:

| Today (GCP)                                   | After                                  |
|-----------------------------------------------|----------------------------------------|
| Cloud SQL Postgres `jobssilverdb` (jobs/ETL)   | Supabase Postgres (same schema)        |
| Firestore (users, sessions, resumes, …)        | Supabase Postgres (new tables)         |
| Cloud Run (FastAPI backend)                    | New host — decide in Phase 5           |
| Firebase Hosting (frontend)                    | Cloudflare Pages (recommended — you already use CF) |

Auth is unaffected: PlaceUp uses its own bcrypt + JWT (Firebase was only a
datastore), so there is **no** Firebase Auth → Supabase Auth migration.

---

## Phase 0 — Prerequisites (once)

On your machine you need: `gcloud` (logged in), `supabase` CLI, `psql`/`pg_dump`
(Postgres 15+ client), and Python with the backend requirements.

```powershell
# From the repo root
supabase login
supabase link --project-ref dyeuehtkdatqftdydgvc
```

Collect from the Supabase dashboard (Settings → Database):
- **Direct connection string** (port 5432) — for the import.
- **Session pooler connection string** (IPv4, port 5432) — for the app.
- Database password.

Set a variable for the rest of this runbook (PowerShell):

```powershell
$SUPA_DB = "postgresql://postgres.dyeuehtkdatqftdydgvc:<DB_PASSWORD>@<pooler-or-direct-host>:5432/postgres"
```

## Phase 1 — Take safety backups (before touching anything)

```powershell
# 1a. Cloud SQL logical dump to a local file (via Cloud SQL Auth Proxy)
#     In terminal A:
cloud-sql-proxy steel-shine-492401-u6:us-east1:placeup-backend --port 5433
#     In terminal B:
pg_dump "host=127.0.0.1 port=5433 user=placeup dbname=jobssilverdb" `
  --no-owner --no-privileges -Fc -f placeup_cloudsql_backup.dump

# 1b. Firestore export to a bucket, then download it
gcloud firestore export gs://<any-bucket-you-own>/firestore-final-export
gsutil -m cp -r gs://<any-bucket-you-own>/firestore-final-export ./firestore-final-export
```

Keep both files somewhere safe (external drive / cloud storage outside GCP).
These are your only copies once GCP is gone.

## Phase 2 — Create the Supabase schema

```powershell
# Applies supabase/migrations/*.sql:
#   20260707000001_user_store_schema.sql  (user tables from Firestore)
#   20260707000002_security_lockdown.sql  (deny-all for API roles, RLS on)
supabase db push
```

If you later add schema changes: `supabase migration new <name>`, edit the
generated SQL file, `supabase db push` again.

## Phase 3 — Copy the data

### 3a. Cloud SQL (jobs/ETL) → Supabase

```powershell
# Restore the dump from Phase 1a into Supabase (direct connection, not pooler):
pg_restore --no-owner --no-privileges -d "$SUPA_DB" placeup_cloudsql_backup.dump

# The dump was created before the lockdown existed on these tables,
# so re-apply the lockdown to cover the restored jobs tables:
psql "$SUPA_DB" -f supabase/migrations/20260707000002_security_lockdown.sql
```

### 3b. Firestore (user data) → Supabase

```powershell
cd backend
$env:SUPABASE_DB_URL = "postgresql+psycopg://postgres.dyeuehtkdatqftdydgvc:<DB_PASSWORD>@<direct-host>:5432/postgres"
$env:USER_FIRESTORE_PROJECT_ID = "<your-gcp-project-id>"

python scripts/migrate_firestore_to_supabase.py            # dry run, prints counts
python scripts/migrate_firestore_to_supabase.py --execute  # copies + auto-verifies
```

The script is idempotent (upsert-by-id) — safe to re-run. It prints a
Firestore-vs-Supabase row-count comparison at the end; every line must say `OK`.

## Phase 4 — Cut the app over

Backend env changes (wherever the backend runs):

```
DATABASE_URL=postgresql+psycopg://postgres.dyeuehtkdatqftdydgvc:<DB_PASSWORD>@<SESSION-POOLER-host>:5432/postgres
USER_DATABASE_BACKEND=postgres
# FIREBASE_CREDENTIALS_PATH / USER_FIRESTORE_* no longer needed
```

Notes:
- Use the **session pooler** (port 5432) string for the app — SQLAlchemy keeps
  its own pool, which is incompatible with the transaction pooler (6543).
- `USER_DATABASE_BACKEND=postgres` flips users/sessions/waitlist/feedback to
  the new `app/db/postgres_user_store.py`. Firestore code stays as fallback
  until teardown.

Deploy, then smoke-test: sign-up, login, refresh token, password reset,
resume upload/list, applications, alerts, admin console, job search.

**Freeze window:** between Phase 3 and Phase 4, new writes still land in the
old databases. For a clean cutover, put the API in maintenance for ~15 min:
re-run 3a/3b (both are idempotent), then flip the env vars.

## Phase 5 — Move hosting off GCP (required before deleting the project)

Your backend container currently runs on **Cloud Run** and the frontend on
**Firebase Hosting**. Both die when the project is deleted, so re-home them first:

- **Frontend** → Cloudflare Pages (you already proxy through Cloudflare;
  `firebase.json` headers/rewrites translate to `_headers` + `_redirects` files).
- **Backend (Docker/FastAPI)** → any container host: Railway, Fly.io, Render,
  or a small VPS. Point `api.placeupcareer.com` CNAME at the new host in
  Cloudflare — your WAF setup in CLOUDFLARE.md carries over unchanged.

Update `FRONTEND_URL`/CORS and the frontend's API base URL accordingly.
Tell me which host you pick and I'll write the deploy config.

## Phase 6 — Verify before deleting ANYTHING

All must pass:

```powershell
# Row counts match (user data)
python scripts/migrate_firestore_to_supabase.py --verify

# Jobs tables spot check
psql "$SUPA_DB" -c "select count(*) from master_jobs;"   # compare vs Cloud SQL
psql "$SUPA_DB" -c "select count(*) from users;"

# Security: anon key must see NOTHING (both must return 401/permission denied)
curl "https://dyeuehtkdatqftdydgvc.supabase.co/rest/v1/users?select=id" -H "apikey: <ANON_KEY>"
curl "https://dyeuehtkdatqftdydgvc.supabase.co/rest/v1/master_jobs?select=*" -H "apikey: <ANON_KEY>"
```

Then run production on Supabase only for **at least 3–7 days** with the GCP
resources stopped-but-not-deleted (Cloud Run scaled to 0, no traffic). If
nothing breaks, proceed.

## Phase 7 — GCP teardown (ordered, cheapest-risk first)

```powershell
$PROJECT = "<your-gcp-project-id>"   # steel-shine-492401-u6

# 1. Stop traffic / scheduled jobs
gcloud scheduler jobs list --project $PROJECT          # delete any
gcloud run services list --project $PROJECT
gcloud run services delete placeup-api --region us-east1 --project $PROJECT
gcloud run jobs list --project $PROJECT                # delete any (silver loader etc.)

# 2. Cloud SQL — the big cost. Final snapshot already taken in Phase 1a.
gcloud sql instances delete placeup-backend --project $PROJECT

# 3. Firestore data (kept exported in Phase 1b)
#    Deleting the project (step 6) removes it; explicit wipe is optional:
gcloud firestore databases delete --database='(default)' --project $PROJECT

# 4. Storage buckets (exports, build artifacts, container images)
gsutil ls -p $PROJECT
gsutil -m rm -r gs://<each-bucket>          # AFTER downloading anything you need
gcloud artifacts repositories list --project $PROJECT   # delete image repos

# 5. Disable billing-relevant leftovers
gcloud services list --enabled --project $PROJECT

# 6. Nuke the whole project (30-day recovery window, then gone)
gcloud projects delete $PROJECT
```

Finally: remove the billing account link (Console → Billing) and check the
next invoice is $0. Rotate/delete any GCP service-account keys still on disk
(`backend/service-account.json`) and scrub GCP secrets from CI.

---

## Supabase security hardening — "no API leaks"

The SQL lockdown (migration `...0002`) already makes the Data API useless to
outsiders: `anon`/`authenticated` have zero grants, RLS is on everywhere with
no policies. Finish with these dashboard/settings steps:

1. **Disable the Data API entirely** (best): Settings → API → Data API →
   toggle off, or remove `public` from "Exposed schemas". Your backend uses
   the Postgres connection, not PostgREST, so nothing breaks.
2. **Never ship the `service_role` key** to the frontend, git, or logs. It
   bypasses RLS. It belongs only in backend env vars — and with the Data API
   off you don't need it at all.
3. **Rotate the anon key** if it was ever committed anywhere (Settings → API).
4. **Enforce SSL** on database connections: Settings → Database → SSL enforcement.
5. **Network restrictions** (Pro feature): allowlist your backend host's egress
   IPs for direct DB access if available.
6. Keep the **database password** out of the repo — `backend/.env` is already
   gitignored; verify with `git log -p -- backend/.env` that it never landed in history.
7. Enable **Point-in-Time Recovery** or scheduled backups (Settings → Database →
   Backups) — you're about to delete the old copies.
8. Frontend never talks to Supabase directly (no supabase-js, no keys in the
   bundle) — keep it that way; everything goes through your FastAPI + JWT.

## Rollback

Until Phase 7 nothing is destroyed. To roll back at any point: set
`USER_DATABASE_BACKEND=firestore` and `DATABASE_URL` back to Cloud SQL,
redeploy. After Phase 7, restore from `placeup_cloudsql_backup.dump` and the
Firestore export (importable into any new Firestore project — or re-run the
migration script against them).

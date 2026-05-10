# PlaceUp Backend + ETL Framework

This backend now supports a production PostgreSQL data path alongside the
existing SQLite local fallback.

## Production Shape

```text
FastAPI API service (Cloud Run)
  -> Cloud SQL PostgreSQL

Cloud Scheduler
  -> Cloud Run Job: placeup-job-scraper-6h
  -> Cloud Run Job: placeup-external-api-12h
  -> Cloud Run Function: clean-and-load-jobs (Firestore bronze -> silver_posts every 12h)

ETL path
  scraper/API fetch
  -> staging_records
  -> normalized companies/jobs/contacts
  -> master_jobs dedupe table
  -> ingest_runs metrics
```

## Local Start

```powershell
cd backend
docker compose up -d postgres
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:DATABASE_BACKEND="postgres"
$env:DATABASE_URL="postgresql+psycopg://placeup:placeup_dev@localhost:5432/placeup"
alembic upgrade head
python -m app.etl.jobs_scraper --dry-run --queries "software engineer" --max-per-source 10
python -m app.etl.jobs_scraper --queries "software engineer" --max-per-source 10
uvicorn app.main:app --reload --port 8000
```

## GCP Deployment Order

```powershell
cd backend
.\deploy\setup_gcp.ps1 -ProjectId YOUR_PROJECT_ID -DbPassword "A_STRONG_PASSWORD"
.\deploy\deploy_backend.ps1 -ProjectId YOUR_PROJECT_ID
.\deploy\run_migrations.ps1 -ProjectId YOUR_PROJECT_ID
.\deploy\schedule_jobs.ps1 -ProjectId YOUR_PROJECT_ID
.\deploy\deploy_silver_loader.ps1 -ProjectId steel-shine-492401-u6 -Region us-east1 -DbInstance placeup-backend
.\deploy\schedule_silver_loader.ps1 -ProjectId steel-shine-492401-u6 -Region us-east1
```

`setup_gcp.ps1` creates Cloud SQL, Artifact Registry, service accounts, and
baseline secrets. API provider keys should be added later with Secret Manager.
Create the `SILVER_DB_PASS` secret before deploying the silver loader:

```powershell
"YOUR_DATABASE_PASSWORD" | gcloud secrets create SILVER_DB_PASS --data-file=-
```

Prepare the silver database once before the first scheduled run. The table
definition is in `cloudrun_silver_loader/schema.sql`; apply it to
`jobssilverdb` with Cloud SQL Studio, `psql`, or your migration runner.

## ETL Contracts

All new sources should:

1. Fetch records from the provider.
2. Store raw provider payloads in `staging_records`.
3. Store normalized data in `normalized_payload`.
4. Upsert canonical tables from normalized payloads.
5. Rebuild or upsert `master_jobs` so the API sees deduplicated positions.
6. Record metrics in `ingest_runs`.

Do not write scraper output directly to final tables without staging it first.

`master_jobs` is the API-facing jobs table in production. It combines:

- `jobs` from the 6-hour scraper pipeline
- `silver_posts` from the 12-hour Firestore bronze loader

Deduplication uses a canonical hash of title, company, and location. The
scraper source wins when the same role appears in both sources because it
usually has richer visa and salary metadata.

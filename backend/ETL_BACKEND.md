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

ETL path
  scraper/API fetch
  -> staging_records
  -> normalized companies/jobs/contacts
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
```

`setup_gcp.ps1` creates Cloud SQL, Artifact Registry, service accounts, and
baseline secrets. API provider keys should be added later with Secret Manager.

## ETL Contracts

All new sources should:

1. Fetch records from the provider.
2. Store raw provider payloads in `staging_records`.
3. Store normalized data in `normalized_payload`.
4. Upsert canonical tables from normalized payloads.
5. Record metrics in `ingest_runs`.

Do not write scraper output directly to final tables without staging it first.

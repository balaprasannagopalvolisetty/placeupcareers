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
  -> Cloud Run Job: placeup-linkedin-jd-repair
  -> Cloud Run Job: placeup-stale-jobs-sweeper
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

## Current 6-Hour Scraper Contract

`placeup-job-scraper-6h` runs `python -m app.etl.jobs_scraper_6h`.

Production settings:

- `SCRAPER_PUBLIC_BATCH_CONCURRENCY=8`
- `SCRAPER_ROLE_BATCH_SIZE=4` by default
- `SCRAPE_MAX_CONCURRENCY=10`
- `SCRAPEGRAPH_DISCOVERY_MAX_URLS=220`
- `SCRAPEGRAPH_DISCOVERY_CONCURRENCY=3`
- Cloud Run job `--max-retries=0`

The scraper covers the full current taxonomy: 12 categories, 100 roles, and 533
scrape terms. The older "64 batches" number was from 255 focused backfill terms
split into groups of 4; it was not the number of positions in the app.

Scheduled production scraping is free/open-source only. The 6-hour job no longer
uses paid LinkedIn providers or broad anonymous aggregator scraping sources that
commonly block Cloud Run. Current scheduled sources are:

- `usajobs`
- `dice`
- `h1b_sponsor`
- `tier1_ats`

Future global sources should follow the same rule: official government APIs,
official downloadable registries, EURES, or public company ATS JSON endpoints.
Do not add Fantastic.jobs, paid LinkedIn pulls, or blocked aggregator scraping
to the default scheduled pipeline.

`jobs_scraper_6h.py` takes a Postgres advisory lock before scraping. If a
scheduled run starts while a manual run is still active, the second execution
logs that another run is active and exits successfully without overlapping.
Retries are disabled for the 6-hour scraper job so a failed public-board run
does not hold the lock through a second Cloud Run retry cycle.

After a scrape finishes, run the LinkedIn repair job to fix existing/present
LinkedIn rows that still have company=`LinkedIn` or thin descriptions:

```powershell
gcloud run jobs execute placeup-linkedin-jd-repair `
  --region us-east1 `
  --project steel-shine-492401-u6 `
  --wait
```

The repair worker fetches the canonical LinkedIn detail URL, extracts JSON-LD
and page metadata, replaces board company names with the actual company, updates
short descriptions with full JDs when available, then rebuilds `master_jobs`.

## Job Retention

`placeup-stale-jobs-sweeper` marks stale jobs inactive and deletes job snapshots
older than the retention window.

Production retention is 30 days:

```powershell
gcloud run jobs execute placeup-stale-jobs-sweeper `
  --region us-east1 `
  --project steel-shine-492401-u6 `
  --wait
```

The sweeper deletes matching rows from `jobs`, `master_jobs`, and `silver_posts`
when that table exists. It also nulls `contacts.related_job_id` before deleting
jobs so foreign keys do not block cleanup.

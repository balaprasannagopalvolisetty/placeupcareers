# PlaceUp Production Deployment

This deployment runs:

- `placeup-api`: FastAPI backend on Cloud Run.
- `placeup-job-scraper-6h`: Cloud Run Job scheduled every 6 hours.
- `clean-and-load-jobs`: Gen2 Cloud Run Function scheduled every 12 hours for Firestore bronze to Cloud SQL silver.
- `master_jobs`: deduplicated master table combining normalized scraper jobs and `silver_posts`.
- `placeup-frontend`: Vite React app on Cloud Run.

## 1. Local Checks

```powershell
cd D:\Development_Projects\PlaceUp
python -m pytest backend/tests
cd frontend
npm run build
```

## 2. Google Cloud APIs

```powershell
gcloud auth login
gcloud config set project YOUR_PROJECT_ID

gcloud services enable `
  run.googleapis.com `
  cloudfunctions.googleapis.com `
  sqladmin.googleapis.com `
  artifactregistry.googleapis.com `
  cloudbuild.googleapis.com `
  cloudscheduler.googleapis.com `
  secretmanager.googleapis.com `
  firestore.googleapis.com `
  logging.googleapis.com `
  monitoring.googleapis.com
```

## 3. Backend Foundation

Use a fresh password. Do not reuse any password pasted in chat or committed locally.

```powershell
cd backend
.\deploy\setup_gcp.ps1 `
  -ProjectId YOUR_PROJECT_ID `
  -Region us-central1 `
  -DbInstance placeup-postgres `
  -DbPassword "STRONG_NEW_PASSWORD"
```

This creates:

- Artifact Registry repo: `placeup`
- Cloud SQL database: `placeup`
- Service accounts:
  - `placeup-api-sa`
  - `placeup-etl-sa`
  - `placeup-scheduler-sa`
- Secrets:
  - `DATABASE_URL`
  - `JWT_SECRET`

Add optional provider secrets when you have keys:

```powershell
"YOUR_KEY" | gcloud secrets create RAPIDAPI_KEY --data-file=-
"YOUR_KEY" | gcloud secrets create USAJOBS_API_KEY --data-file=-
"YOUR_EMAIL" | gcloud secrets create USAJOBS_EMAIL --data-file=-
"YOUR_KEY" | gcloud secrets create GROQ_API_KEY --data-file=-
```

## 4. Backend Deploy, Migrate, Schedule

```powershell
cd backend
.\deploy\deploy_backend.ps1 `
  -ProjectId YOUR_PROJECT_ID `
  -Region us-central1 `
  -DbInstance placeup-postgres

.\deploy\run_migrations.ps1 `
  -ProjectId YOUR_PROJECT_ID `
  -Region us-central1 `
  -DbInstance placeup-postgres

.\deploy\schedule_jobs.ps1 `
  -ProjectId YOUR_PROJECT_ID `
  -Region us-central1 `
  -TimeZone America/Chicago
```

The migration creates `jobs`, `silver_posts`, and `master_jobs`.

The 6-hour scraper writes normalized jobs into `jobs`, then rebuilds `master_jobs`.

## 5. Silver Loader

For your existing project/database:

- Project: `steel-shine-492401-u6`
- Region: `us-east1`
- Cloud SQL instance: `placeup-backend`
- Database: `jobssilverdb`
- Firestore database: `ra-jobs`
- Firestore collection: `jobs`

Create the DB password secret:

```powershell
"STRONG_NEW_SILVER_DB_PASSWORD" | gcloud secrets create SILVER_DB_PASS --data-file=-
```

Prepare the silver database once. Apply:

```text
backend/cloudrun_silver_loader/schema.sql
```

You can apply it through Cloud SQL Studio or `psql`. It creates:

- `silver_posts`
- `master_jobs`
- indexes
- `pgcrypto` extension for dedupe hashes

Deploy and schedule:

```powershell
cd backend
.\deploy\deploy_silver_loader.ps1 `
  -ProjectId steel-shine-492401-u6 `
  -Region us-east1 `
  -DbInstance placeup-backend `
  -DbName jobssilverdb `
  -DbUser postgres `
  -FirestoreDatabase ra-jobs `
  -FirestoreCollection jobs

.\deploy\schedule_silver_loader.ps1 `
  -ProjectId steel-shine-492401-u6 `
  -Region us-east1 `
  -ScheduleRegion us-east1 `
  -TimeZone America/Chicago
```

This runs every 12 hours. Each run upserts `silver_posts` and syncs those rows into `master_jobs`.

## 6. Frontend Deploy

After backend deploy, get the backend URL:

```powershell
gcloud run services describe placeup-api `
  --region us-central1 `
  --format "value(status.url)"
```

Deploy frontend with that URL:

```powershell
cd frontend
.\deploy_frontend.ps1 `
  -ProjectId YOUR_PROJECT_ID `
  -Region us-central1 `
  -ApiBase "https://YOUR_BACKEND_RUN_URL"
```

Then update backend CORS:

```powershell
gcloud run services update placeup-api `
  --region us-central1 `
  --set-env-vars "FRONTEND_URL=https://YOUR_FRONTEND_RUN_URL,APP_ENV=production,DATABASE_BACKEND=postgres"
```

If you use custom domains, set `FRONTEND_URL` to the custom frontend origin. Multiple origins can be comma-separated.

## 7. Verify Production

Backend health:

```powershell
curl https://YOUR_BACKEND_RUN_URL/api/health
```

Jobs:

```powershell
curl "https://YOUR_BACKEND_RUN_URL/api/jobs?page=1&page_size=5"
```

Visa:

```powershell
curl "https://YOUR_BACKEND_RUN_URL/api/visa/dashboard"
```

Schedulers:

```powershell
gcloud scheduler jobs list --location us-central1
gcloud scheduler jobs list --location us-east1
```

Manual job run:

```powershell
gcloud run jobs execute placeup-job-scraper-6h --region us-central1 --wait
```

Manual silver loader run:

```powershell
gcloud scheduler jobs run placeup-silver-loader-12h --location us-east1
```

Master table check in Cloud SQL:

```sql
SELECT COUNT(*) FROM master_jobs;
SELECT source_name, COUNT(*) FROM master_jobs GROUP BY source_name ORDER BY COUNT(*) DESC;
```

## 8. Why Jobs May Show Empty

Jobs will be empty until at least one of these has run successfully:

- `placeup-job-scraper-6h`
- `clean-and-load-jobs`

Also confirm the API service points to the same Cloud SQL database where `master_jobs` is populated.

## 9. Operational Notes

- Local development scheduler is 6 hours and uses `backend/data/.last_scrape_at`; restarting the backend no longer immediately scrapes unless the timer is due.
- If `placeup_jobs.csv` is open in Excel, exports write a timestamped sidecar instead of failing the scrape.
- Analytics now returns real user data only. Empty accounts show empty states.
- Each user is limited to one active resume; uploading a new resume replaces prior resume metadata for that user.

# PlaceUp Production Deployment

This deployment runs:

- `placeup-api`: FastAPI backend on Cloud Run.
- `placeup-job-scraper-6h`: Cloud Run Job scheduled every 6 hours.
- `clean-and-load-jobs`: Gen2 Cloud Run Function scheduled every 12 hours for Firestore bronze to Cloud SQL silver.
- `master_jobs`: deduplicated master table combining normalized scraper jobs and `silver_posts`.
- `placeup-frontend`: Vite React app on Firebase Hosting or Cloud Run.
- `placeup-firebase-641222668282`: separate Firebase/Firestore project for users, profiles, preferences, alerts, and resume metadata.

## Current Production Projects

- Backend/jobs/API project: `steel-shine-492401-u6`
- Backend project number: `641222668282`
- Backend region: `us-east1`
- Backend Cloud Run URL: `https://placeup-api-rui2a74muq-ue.a.run.app`
- Cloud SQL instance: `placeup-backend`
- Cloud SQL database: `jobssilverdb`
- Firebase/user project: `placeup-firebase-641222668282`
- Firebase/user project number: `264310798329`
- User Firestore database: `(default)` in `nam5`
- Frontend Cloud Run URL: `https://placeup-frontend-76tybrmgya-ue.a.run.app`

The backend service account
`placeup-api-sa@steel-shine-492401-u6.iam.gserviceaccount.com`
must have `roles/datastore.user` on the Firebase/user project.

Current direct Cloud Run status: backend and frontend are deployed, healthy, and
public through disabled Cloud Run Invoker IAM checks. This avoids the org policy
that blocks public `allUsers` IAM bindings.

Current domain status: `placeupcareer.com` is verified for
`operations@placeupcareer.com`. Cloud Run domain mappings exist for
`placeupcareer.com` and `www.placeupcareer.com`. DNS now resolves to the Google
Cloud Run records. Cloud Run certificate provisioning is pending.

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
gcloud config set project steel-shine-492401-u6

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
  monitoring.googleapis.com `
  --project steel-shine-492401-u6

gcloud services enable `
  cloudresourcemanager.googleapis.com `
  serviceusage.googleapis.com `
  firebase.googleapis.com `
  firebaserules.googleapis.com `
  firestore.googleapis.com `
  firebasehosting.googleapis.com `
  identitytoolkit.googleapis.com `
  --project placeup-firebase-641222668282
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
  -ProjectId steel-shine-492401-u6 `
  -Region us-east1 `
  -DbInstance placeup-backend `
  -UserDatabaseBackend firestore `
  -UserFirestoreProjectId placeup-firebase-641222668282 `
  -UserFirestoreDatabase "(default)"

.\deploy\run_migrations.ps1 `
  -ProjectId steel-shine-492401-u6 `
  -Region us-east1 `
  -DbInstance placeup-backend

.\deploy\schedule_jobs.ps1 `
  -ProjectId steel-shine-492401-u6 `
  -Region us-east1 `
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

## 6. Separate Firebase/User Project

The Firebase/user project is separate from the backend project. This keeps user
profiles and app data isolated from scraper jobs, Cloud SQL, and backend
infrastructure.

```powershell
cd backend
.\deploy\setup_firebase_users.ps1 `
  -ProjectId placeup-firebase-641222668282 `
  -BackendProjectId steel-shine-492401-u6 `
  -Region us-east1 `
  -FirestoreDatabase "(default)" `
  -FirestoreLocation nam5
```

Deploy or update the backend so user/profile calls go to the Firebase project:

```powershell
cd backend
.\deploy\deploy_backend.ps1 `
  -ProjectId steel-shine-492401-u6 `
  -Region us-east1 `
  -DbInstance placeup-backend `
  -UserDatabaseBackend firestore `
  -UserFirestoreProjectId placeup-firebase-641222668282 `
  -UserFirestoreDatabase "(default)"
```

Verify:

```powershell
gcloud run services describe placeup-api `
  --region us-east1 `
  --project steel-shine-492401-u6 `
  --format "value(spec.template.spec.containers[0].env)"
```

Expected env values:

```text
USER_DATABASE_BACKEND=firestore
USER_FIRESTORE_PROJECT_ID=placeup-firebase-641222668282
USER_FIRESTORE_DATABASE=(default)
```

## 7. Frontend Deploy

Current status: the separate Google Cloud project and Firestore database exist,
but Firebase registration for Hosting is blocked by `projects.addFirebase` with
`403 PERMISSION_DENIED` for the current CLI identity. An org/Firebase admin must
enable Firebase for `placeup-firebase-641222668282` in the Firebase console or
grant the CLI identity permission to add Firebase to the project.

### Recommended: Separate Cloud Run Servers

This keeps the API server in `steel-shine-492401-u6` and deploys the frontend as
its own Cloud Run service in `placeup-firebase-641222668282`. The script builds
the backend, reads the backend Cloud Run URL, builds the frontend with that URL
as `VITE_API_BASE`, then updates backend CORS with the frontend Cloud Run origin.

```powershell
cd D:\Development_Projects\PlaceUp
.\deploy_separate_cloud_run.ps1 `
  -BackendProjectId steel-shine-492401-u6 `
  -FrontendProjectId placeup-firebase-641222668282 `
  -Region us-east1 `
  -DbInstance placeup-backend
```

If the backend is already deployed and you only need to redeploy the separate
frontend server:

```powershell
.\deploy_separate_cloud_run.ps1 `
  -BackendProjectId steel-shine-492401-u6 `
  -FrontendProjectId placeup-firebase-641222668282 `
  -Region us-east1 `
  -DbInstance placeup-backend `
  -SkipBackend
```

If you already know a custom frontend origin, pass it so CORS is set directly:

```powershell
.\deploy_separate_cloud_run.ps1 `
  -BackendProjectId steel-shine-492401-u6 `
  -FrontendProjectId placeup-firebase-641222668282 `
  -Region us-east1 `
  -DbInstance placeup-backend `
  -FrontendUrl "https://app.placeupcareer.com"
```

### Option A: Firebase Hosting Static Frontend

Firebase Hosting serves the React app from `placeup-firebase-641222668282`.
Because the backend intentionally remains in `steel-shine-492401-u6`, do not use
a Firebase Hosting Cloud Run rewrite unless you also deploy a proxy service in
the Firebase project. Firebase Hosting Cloud Run rewrites identify only a
service and region, so they are not the right place to point directly at a
Cloud Run service in another project.

First reauthenticate gcloud if needed:

```powershell
gcloud auth login
gcloud config set project placeup-firebase-641222668282
```

Deploy frontend to Firebase Hosting with the deployed backend URL:

```powershell
cd frontend
.\deploy_firebase_hosting.ps1 `
  -ProjectId placeup-firebase-641222668282 `
  -ApiBase "https://placeup-api-641222668282.us-east1.run.app"
```

Do not omit `-ApiBase` for Firebase Hosting unless you have intentionally added
a same-project API proxy rewrite.

After Firebase prints the hosting URL, update backend CORS with that exact origin:

```powershell
gcloud run services update placeup-api `
  --region us-east1 `
  --project steel-shine-492401-u6 `
  --set-env-vars "FRONTEND_URL=https://YOUR_FIREBASE_HOSTING_DOMAIN,APP_ENV=production,DATABASE_BACKEND=postgres,USER_DATABASE_BACKEND=firestore,USER_FIRESTORE_PROJECT_ID=placeup-firebase-641222668282,USER_FIRESTORE_DATABASE=(default)"
```

If organization policy keeps `placeup-api` private, the browser cannot call it
directly with only the app JWT. In that case, deploy a small frontend-project
API proxy, grant it `roles/run.invoker` on the backend service, and point
`VITE_API_BASE` at that proxy.

### Option B: Cloud Run Frontend

After backend deploy, get the backend URL:

```powershell
gcloud run services describe placeup-api `
  --region us-east1 `
  --project steel-shine-492401-u6 `
  --format "value(status.url)"
```

Deploy frontend with that URL:

```powershell
cd frontend
.\deploy_frontend.ps1 `
  -ProjectId placeup-firebase-641222668282 `
  -Region us-east1 `
  -ApiBase "https://placeup-api-641222668282.us-east1.run.app"
```

Then update backend CORS:

```powershell
gcloud run services update placeup-api `
  --region us-east1 `
  --project steel-shine-492401-u6 `
  --set-env-vars "FRONTEND_URL=https://YOUR_FRONTEND_RUN_URL,APP_ENV=production,DATABASE_BACKEND=postgres,USER_DATABASE_BACKEND=firestore,USER_FIRESTORE_PROJECT_ID=placeup-firebase-641222668282,USER_FIRESTORE_DATABASE=(default)"
```

If you use custom domains, set `FRONTEND_URL` to the custom frontend origin. Multiple origins can be comma-separated.

Note: The current organization policy blocks `allUsers` on Cloud Run. Public
access is enabled with `--no-invoker-iam-check`, which is the Google-recommended
path when domain-restricted sharing blocks `allUsers` invoker bindings.

To map `placeupcareer.com`, first verify the domain:

```powershell
gcloud domains verify placeupcareer.com
gcloud domains list-user-verified
```

Then create the Cloud Run domain mappings:

```powershell
gcloud beta run domain-mappings create `
  --service placeup-frontend `
  --domain placeupcareer.com `
  --region us-east1 `
  --project placeup-firebase-641222668282

gcloud beta run domain-mappings create `
  --service placeup-frontend `
  --domain www.placeupcareer.com `
  --region us-east1 `
  --project placeup-firebase-641222668282
```

After Cloud Run prints DNS records, replace the current Squarespace DNS records
with the Cloud Run records.

Current Cloud Run DNS records:

```text
A     @     216.239.32.21
A     @     216.239.34.21
A     @     216.239.36.21
A     @     216.239.38.21
AAAA  @     2001:4860:4802:32::15
AAAA  @     2001:4860:4802:34::15
AAAA  @     2001:4860:4802:36::15
AAAA  @     2001:4860:4802:38::15
CNAME www   ghs.googlehosted.com.
```

Remove the Squarespace `A @` records, the Squarespace `CNAME www` record, and
the Squarespace `HTTPS @` record before adding the Cloud Run records. Keep Google
Workspace email records, SPF, DKIM, Microsoft verification, and
`_domainconnect`.

## 8. Verify Production

Backend health:

```powershell
$token = gcloud auth print-identity-token
curl -H "Authorization: Bearer $token" https://placeup-api-641222668282.us-east1.run.app/api/health
```

Jobs:

```powershell
curl -H "Authorization: Bearer $token" "https://placeup-api-641222668282.us-east1.run.app/api/jobs?page=1&page_size=5"
```

Visa:

```powershell
curl -H "Authorization: Bearer $token" "https://placeup-api-641222668282.us-east1.run.app/api/visa/dashboard"
```

Schedulers:

```powershell
gcloud scheduler jobs list --location us-east1
```

Manual job run:

```powershell
gcloud run jobs execute placeup-job-scraper-6h --region us-east1 --wait --project steel-shine-492401-u6
```

Manual silver loader run:

```powershell
gcloud scheduler jobs run placeup-silver-loader-12h --location us-east1 --project steel-shine-492401-u6
```

Master table check in Cloud SQL:

```sql
SELECT COUNT(*) FROM master_jobs;
SELECT source_name, COUNT(*) FROM master_jobs GROUP BY source_name ORDER BY COUNT(*) DESC;
```

Verify user/profile Firestore in the separate Firebase project:

```powershell
gcloud firestore databases describe `
  --database "(default)" `
  --project placeup-firebase-641222668282
```

## 9. Why Jobs May Show Empty

Jobs will be empty until at least one of these has run successfully:

- `placeup-job-scraper-6h`
- `clean-and-load-jobs`

Also confirm the API service points to the same Cloud SQL database where `master_jobs` is populated.

## 10. Operational Notes

- Local development scheduler is 6 hours and uses `backend/data/.last_scrape_at`; restarting the backend no longer immediately scrapes unless the timer is due.
- If `placeup_jobs.csv` is open in Excel, exports write a timestamped sidecar instead of failing the scrape.
- Analytics now returns real user data only. Empty accounts show empty states.
- Each user is limited to one active resume; uploading a new resume replaces prior resume metadata for that user.
- Do not print passwords or secret values in deployment notes. Store production credentials in Secret Manager and rotate anything pasted into chat or terminals.

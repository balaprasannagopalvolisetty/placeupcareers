param(
  [string]$BackendProjectId = "steel-shine-492401-u6",
  [string]$FrontendProjectId = "placeup-firebase-641222668282",
  [string]$Region = "us-east1",
  [string]$DbInstance = "placeup-backend",
  [string]$UserFirestoreProjectId = "",
  [string]$UserFirestoreDatabase = "(default)",
  [string]$BackendUrl = "",
  [string]$FrontendUrl = "",
  [switch]$SkipBackend,
  [switch]$SkipFrontend,
  [switch]$SkipCorsUpdate,
  [switch]$SkipScheduler
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $UserFirestoreProjectId) {
  $UserFirestoreProjectId = $FrontendProjectId
}

function Test-GcpSecretExists([string]$ProjectId, [string]$SecretName) {
  $previousErrorAction = $ErrorActionPreference
  $ErrorActionPreference = "Continue"
  try {
    & gcloud.cmd secrets describe $SecretName --project $ProjectId --format="value(name)" *> $null
    return $LASTEXITCODE -eq 0
  } finally {
    $ErrorActionPreference = $previousErrorAction
  }
}

function Add-OptionalSecretBinding([string]$ProjectId, [string]$CurrentBindings, [string]$SecretName) {
  if (Test-GcpSecretExists $ProjectId $SecretName) {
    return "$CurrentBindings,$SecretName=$SecretName`:latest"
  }

  Write-Host "Secret $SecretName not found; skipping optional binding."
  return $CurrentBindings
}

if (-not $SkipBackend) {
  $backendArgs = @{
    ProjectId = $BackendProjectId
    Region = $Region
    DbInstance = $DbInstance
    UserDatabaseBackend = "firestore"
    UserFirestoreProjectId = $UserFirestoreProjectId
    UserFirestoreDatabase = $UserFirestoreDatabase
  }
  if ($FrontendUrl) {
    $backendArgs.FrontendUrl = $FrontendUrl
  }

  Push-Location (Join-Path $Root "backend")
  try {
    & ".\deploy\deploy_backend.ps1" @backendArgs
  } finally {
    Pop-Location
  }
}

if (-not $SkipBackend -and -not $SkipScheduler) {
  Push-Location (Join-Path $Root "backend")
  try {
    & ".\deploy\schedule_jobs.ps1" `
      -ProjectId $BackendProjectId `
      -Region $Region `
      -TimeZone "America/Chicago"
  } finally {
    Pop-Location
  }
}

if (-not $BackendUrl) {
  $BackendUrl = gcloud.cmd run services describe placeup-api `
    --region $Region `
    --project $BackendProjectId `
    --format "value(status.url)"
}

if (-not $BackendUrl) {
  throw "Could not resolve backend Cloud Run URL. Pass -BackendUrl explicitly."
}

Write-Host "Backend API URL: $BackendUrl"

if (-not $SkipFrontend) {
  Push-Location (Join-Path $Root "frontend")
  try {
    # ApiBase MUST stay empty (relative /api) for the Cloud Run + nginx
    # deployment: the SPA's CSP is connect-src 'self' and refresh cookies are
    # SameSite=Strict, so the browser BLOCKS direct calls to the run.app
    # backend ("Failed to fetch" on sign-in). All API traffic goes through
    # nginx's /api/ proxy; BackendOrigin points that proxy at the live API.
    & ".\deploy_frontend.ps1" `
      -ProjectId $FrontendProjectId `
      -Region $Region `
      -ApiBase "" `
      -BackendOrigin $BackendUrl
  } finally {
    Pop-Location
  }
}

if (-not $FrontendUrl) {
  $FrontendUrl = gcloud.cmd run services describe placeup-frontend `
    --region $Region `
    --project $FrontendProjectId `
    --format "value(status.url)"
}

if (-not $FrontendUrl) {
  throw "Could not resolve frontend Cloud Run URL. Pass -FrontendUrl explicitly."
}

Write-Host "Frontend URL: $FrontendUrl"

if (-not $SkipCorsUpdate) {
  $apiEnv = "FRONTEND_URL=$FrontendUrl,APP_ENV=production,DATABASE_BACKEND=postgres,USER_DATABASE_BACKEND=firestore,USER_FIRESTORE_PROJECT_ID=$UserFirestoreProjectId,USER_FIRESTORE_DATABASE=$UserFirestoreDatabase,SCRAPE_INTERVAL_HOURS=8"

  # --update-env-vars (merge), NEVER --set-env-vars (replace): replacing wiped
  # OTP/email/OIDC settings on every deploy and broke sign-in/sign-up.
  gcloud.cmd run services update placeup-api `
    --region $Region `
    --project $BackendProjectId `
    --update-env-vars $apiEnv

  Write-Host "Backend CORS updated for frontend origin: $FrontendUrl"
}

if (-not $SkipBackend) {
  # Cloud Run JOB (not service) — runs out-of-band ATS scoring so the
  # API container stays small and fast. Triggered by Cloud Scheduler
  # (see backend/deploy/README.md). Safe to re-run: --no-traffic on
  # services doesn't apply to jobs; this re-points to the latest image.
  Write-Host "Deploying ATS worker Cloud Run Job..."
  $imageTag = "$Region-docker.pkg.dev/$BackendProjectId/placeup/backend:latest"
  # Tiny DB connection budget for background jobs so they can never starve
  # the user-facing API of Cloud SQL connections while running.
  $workerEnv = "APP_ENV=production,DATABASE_BACKEND=postgres,DB_POOL_SIZE=2,DB_MAX_OVERFLOW=2,USER_DATABASE_BACKEND=firestore,USER_FIRESTORE_PROJECT_ID=$UserFirestoreProjectId,USER_FIRESTORE_DATABASE=$UserFirestoreDatabase"

  gcloud.cmd run jobs deploy placeup-ats-worker `
    --image $imageTag `
    --region $Region `
    --project $BackendProjectId `
    --service-account "placeup-api-sa@$BackendProjectId.iam.gserviceaccount.com" `
    --set-cloudsql-instances "$BackendProjectId`:$Region`:$DbInstance" `
    --set-env-vars $workerEnv `
    --set-secrets "DATABASE_URL=DATABASE_URL:latest" `
    --memory 1Gi `
    --cpu 1 `
    --task-timeout 1800s `
    --command python `
    --args="-m,app.workers.ats_worker" `
    --max-retries 1

  # Daily ops digest — emails the deduped company + location list to
  # operations@placeupcareer.com and (optionally) syncs to a Google
  # Sheet. SMTP creds + sheet ID come from Secret Manager. Cloud
  # Scheduler trigger is set up in schedule_jobs.ps1.
  Write-Host "Deploying companies-export Cloud Run Job..."
  $exportEnv = "$workerEnv,COMPANIES_EXPORT_TO=operations@placeupcareer.com,COMPANIES_EXPORT_CREATE_SHEET=true,COMPANIES_EXPORT_SHARE_EMAIL=operations@placeupcareer.com"
  # Best-effort secret binding — the job still runs (email skipped, log only)
  # if these secrets are not present yet. Add them once with:
  #   gcloud secrets create SMTP_HOST --data-file=- <<< "smtp.gmail.com"
  #   gcloud secrets create SMTP_PORT --data-file=- <<< "587"
  #   gcloud secrets create SMTP_USER --data-file=- <<< "no-reply@placeupcareer.com"
  #   gcloud secrets create SMTP_PASSWORD --data-file=- <<< "<app password>"
  #   gcloud secrets create COMPANIES_EXPORT_SHEET_ID --data-file=- <<< "<sheet id>"
  $exportSecrets = "DATABASE_URL=DATABASE_URL:latest"
  foreach ($secretName in @("SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASSWORD", "COMPANIES_EXPORT_SHEET_ID")) {
    $exportSecrets = Add-OptionalSecretBinding $BackendProjectId $exportSecrets $secretName
  }

  gcloud.cmd run jobs deploy placeup-companies-export `
    --image $imageTag `
    --region $Region `
    --project $BackendProjectId `
    --service-account "placeup-api-sa@$BackendProjectId.iam.gserviceaccount.com" `
    --set-cloudsql-instances "$BackendProjectId`:$Region`:$DbInstance" `
    --set-env-vars $exportEnv `
    --set-secrets $exportSecrets `
    --memory 512Mi `
    --cpu 1 `
    --task-timeout 600s `
    --command python `
    --args="-m,app.workers.companies_export" `
    --max-retries 2

  # Daily stale-jobs sweeper — UPDATE-only, tiny resource footprint.
  # Just needs Cloud SQL access + DATABASE_URL.
  Write-Host "Deploying stale-jobs sweeper Cloud Run Job..."
  gcloud.cmd run jobs deploy placeup-stale-jobs-sweeper `
    --image $imageTag `
    --region $Region `
    --project $BackendProjectId `
    --service-account "placeup-api-sa@$BackendProjectId.iam.gserviceaccount.com" `
    --set-cloudsql-instances "$BackendProjectId`:$Region`:$DbInstance" `
    --set-env-vars $workerEnv `
    --set-secrets "DATABASE_URL=DATABASE_URL:latest" `
    --memory 512Mi `
    --cpu 1 `
    --task-timeout 300s `
    --command python `
    --args="-m,app.workers.stale_jobs_sweeper" `
    --max-retries 2
}

# ---- Post-deploy auth smoke test --------------------------------------------
# Sign-in/sign-up has historically broken when deploys wiped auth/email env
# vars. This gate verifies the live auth surface end-to-end after EVERY
# deploy and fails the script loudly if anything is wrong.
Write-Host ""
Write-Host "Running auth smoke test (backend direct)..."
& (Join-Path $Root "backend\deploy\smoke_auth.ps1") -ApiBase $BackendUrl -Origin "https://placeupcareer.com"
if ($LASTEXITCODE -ne 0) {
  throw "Auth smoke test FAILED - sign-in/sign-up is broken on this deploy. Fix before announcing the release. (Previous Cloud Run revision may still be serving traffic if the new one failed to boot.)"
}

# Same checks through the REAL user path: custom domain -> nginx /api proxy.
# Catches broken BACKEND_ORIGIN, CSP/API-base mismatches, and domain issues
# that the direct backend test cannot see.
Write-Host ""
Write-Host "Running auth smoke test (through placeupcareer.com proxy)..."
& (Join-Path $Root "backend\deploy\smoke_auth.ps1") -ApiBase "https://placeupcareer.com" -Origin "https://placeupcareer.com"
if ($LASTEXITCODE -ne 0) {
  throw "Auth smoke test through the custom domain FAILED - users cannot sign in even though the backend is healthy. Check the frontend service's BACKEND_ORIGIN env var and the nginx /api proxy."
}

Write-Host "Separate Cloud Run deployment complete."

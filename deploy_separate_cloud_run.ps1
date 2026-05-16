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
  [switch]$SkipCorsUpdate
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $UserFirestoreProjectId) {
  $UserFirestoreProjectId = $FrontendProjectId
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
    & ".\deploy_frontend.ps1" `
      -ProjectId $FrontendProjectId `
      -Region $Region `
      -ApiBase $BackendUrl
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
  $apiEnv = "FRONTEND_URL=$FrontendUrl,APP_ENV=production,DATABASE_BACKEND=postgres,USER_DATABASE_BACKEND=firestore,USER_FIRESTORE_PROJECT_ID=$UserFirestoreProjectId,USER_FIRESTORE_DATABASE=$UserFirestoreDatabase,SCRAPE_INTERVAL_HOURS=6"

  gcloud.cmd run services update placeup-api `
    --region $Region `
    --project $BackendProjectId `
    --set-env-vars $apiEnv

  Write-Host "Backend CORS updated for frontend origin: $FrontendUrl"
}

if (-not $SkipBackend) {
  # Cloud Run JOB (not service) — runs out-of-band ATS scoring so the
  # API container stays small and fast. Triggered by Cloud Scheduler
  # (see backend/deploy/README.md). Safe to re-run: --no-traffic on
  # services doesn't apply to jobs; this re-points to the latest image.
  Write-Host "Deploying ATS worker Cloud Run Job..."
  $imageTag = "us-east1-docker.pkg.dev/$BackendProjectId/placeup/backend:latest"
  $workerEnv = "APP_ENV=production,DATABASE_BACKEND=postgres,USER_DATABASE_BACKEND=firestore,USER_FIRESTORE_PROJECT_ID=$UserFirestoreProjectId,USER_FIRESTORE_DATABASE=$UserFirestoreDatabase"

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
}

Write-Host "Separate Cloud Run deployment complete."

param(
  [Parameter(Mandatory=$true)][string]$ProjectId,
  [string]$Region = "us-east1",
  [string]$DbInstance = "placeup-backend",
  [string]$UserDatabaseBackend = "firestore",
  [string]$UserFirestoreProjectId = "placeup-firebase-641222668282",
  [string]$UserFirestoreDatabase = "(default)",
  [string]$FrontendUrl = ""
)

$ErrorActionPreference = "Stop"
$Image = "$Region-docker.pkg.dev/$ProjectId/placeup/backend:latest"
$ApiEnv = "APP_ENV=production,DATABASE_BACKEND=postgres,USER_DATABASE_BACKEND=$UserDatabaseBackend,USER_FIRESTORE_PROJECT_ID=$UserFirestoreProjectId,USER_FIRESTORE_DATABASE=$UserFirestoreDatabase,SCRAPE_INTERVAL_HOURS=6,SCRAPEGRAPH_ENABLED=false,ADMIN_EMAILS=jobs@placeupcareer.com"
if ($FrontendUrl) {
  $ApiEnv = "$ApiEnv,FRONTEND_URL=$FrontendUrl"
}
$ScraperEnv = "APP_ENV=production,DATABASE_BACKEND=postgres,SCRAPEGRAPH_ENABLED=false,SCRAPEGRAPH_DISCOVERY_ENABLED=true,SCRAPEGRAPH_DISCOVERY_MAX_URLS=220,SCRAPEGRAPH_DISCOVERY_CONCURRENCY=3,SCRAPE_MAX_CONCURRENCY=10,SCRAPER_PUBLIC_BATCH_CONCURRENCY=8"
$ApiSecrets = "DATABASE_URL=DATABASE_URL:latest,JWT_SECRET=JWT_SECRET:latest,RAPIDAPI_KEY=RAPIDAPI_KEY:latest,USAJOBS_API_KEY=USAJOBS_API_KEY:latest,USAJOBS_EMAIL=USAJOBS_EMAIL:latest,HUNTER_API_KEY=HUNTER_API_KEY:latest,FINALSCOUT_API_KEY=FINALSCOUT_API_KEY:latest"
$ScraperSecrets = "DATABASE_URL=DATABASE_URL:latest,RAPIDAPI_KEY=RAPIDAPI_KEY:latest,USAJOBS_API_KEY=USAJOBS_API_KEY:latest,USAJOBS_EMAIL=USAJOBS_EMAIL:latest,HUNTER_API_KEY=HUNTER_API_KEY:latest,FINALSCOUT_API_KEY=FINALSCOUT_API_KEY:latest"
$ExternalSecrets = "DATABASE_URL=DATABASE_URL:latest,RAPIDAPI_KEY=RAPIDAPI_KEY:latest,USAJOBS_API_KEY=USAJOBS_API_KEY:latest,USAJOBS_EMAIL=USAJOBS_EMAIL:latest"

gcloud.cmd config set project $ProjectId
function Test-SecretExists([string]$SecretName) {
  $previousErrorAction = $ErrorActionPreference
  $ErrorActionPreference = "Continue"
  try {
    & gcloud.cmd secrets describe $SecretName --project $ProjectId --format="value(name)" *> $null
    return $LASTEXITCODE -eq 0
  } finally {
    $ErrorActionPreference = $previousErrorAction
  }
}

$OpenAiSecret = Test-SecretExists "OPENAI_API_KEY"
if ($OpenAiSecret) {
  $ApiSecrets = "$ApiSecrets,OPENAI_API_KEY=OPENAI_API_KEY:latest"
  $ScraperSecrets = "$ScraperSecrets,OPENAI_API_KEY=OPENAI_API_KEY:latest"
}

$OpenRouterSecret = Test-SecretExists "OPENROUTER_API_KEY"
if ($OpenRouterSecret) {
  $ApiSecrets = "$ApiSecrets,OPENROUTER_API_KEY=OPENROUTER_API_KEY:latest"
  $ScraperSecrets = "$ScraperSecrets,OPENROUTER_API_KEY=OPENROUTER_API_KEY:latest"
}

$FinalScoutKeysSecret = Test-SecretExists "FINALSCOUT_API_KEYS"
if ($FinalScoutKeysSecret) {
  $ApiSecrets = "$ApiSecrets,FINALSCOUT_API_KEYS=FINALSCOUT_API_KEYS:latest"
  $ScraperSecrets = "$ScraperSecrets,FINALSCOUT_API_KEYS=FINALSCOUT_API_KEYS:latest"
}

foreach ($PaymentSecretName in @("PAYMENT_BASIC_CHECKOUT_URL", "PAYMENT_PRO_CHECKOUT_URL", "PAYMENT_ELITE_CHECKOUT_URL")) {
  if (Test-SecretExists $PaymentSecretName) {
    $ApiSecrets = "$ApiSecrets,$PaymentSecretName=$PaymentSecretName`:latest"
  }
}

$InternalApiSecret = Test-SecretExists "INTERNAL_API_KEY"
if ($InternalApiSecret) {
  $ApiSecrets = "$ApiSecrets,INTERNAL_API_KEY=INTERNAL_API_KEY:latest"
}
$GoogleClientIdSecret = Test-SecretExists "OIDC_GOOGLE_CLIENT_ID"
if ($GoogleClientIdSecret) {
  $ApiSecrets = "$ApiSecrets,OIDC_GOOGLE_CLIENT_ID=OIDC_GOOGLE_CLIENT_ID:latest"
}
$GoogleClientSecret = Test-SecretExists "OIDC_GOOGLE_CLIENT_SECRET"
if ($GoogleClientSecret) {
  $ApiSecrets = "$ApiSecrets,OIDC_GOOGLE_CLIENT_SECRET=OIDC_GOOGLE_CLIENT_SECRET:latest"
}
$GoogleRedirectSecret = Test-SecretExists "OIDC_GOOGLE_REDIRECT_URI"
if ($GoogleRedirectSecret) {
  $ApiSecrets = "$ApiSecrets,OIDC_GOOGLE_REDIRECT_URI=OIDC_GOOGLE_REDIRECT_URI:latest"
}
gcloud.cmd builds submit . --tag $Image

gcloud.cmd run deploy placeup-api `
  --image $Image `
  --region $Region `
  --service-account "placeup-api-sa@$ProjectId.iam.gserviceaccount.com" `
  --no-invoker-iam-check `
  --set-cloudsql-instances "$ProjectId`:$Region`:$DbInstance" `
  --set-env-vars $ApiEnv `
  --set-secrets $ApiSecrets `
  --memory 2Gi `
  --cpu 1 `
  --min-instances 2 `
  --max-instances 20 `
  --concurrency 5

gcloud.cmd run jobs deploy placeup-job-scraper-6h `
  --image $Image `
  --region $Region `
  --service-account "placeup-etl-sa@$ProjectId.iam.gserviceaccount.com" `
  --command python `
  --args="-m,app.etl.jobs_scraper_6h" `
  --set-cloudsql-instances "$ProjectId`:$Region`:$DbInstance" `
  --set-env-vars $ScraperEnv `
  --set-secrets $ScraperSecrets `
  --memory 2Gi `
  --cpu 2 `
  --max-retries 0 `
  --task-timeout 21600

gcloud.cmd run jobs deploy placeup-external-api-12h `
  --image $Image `
  --region $Region `
  --service-account "placeup-etl-sa@$ProjectId.iam.gserviceaccount.com" `
  --command python `
  --args="-m,app.etl.external_api_ingest,--schedule-type,12h" `
  --set-cloudsql-instances "$ProjectId`:$Region`:$DbInstance" `
  --set-env-vars "APP_ENV=production,DATABASE_BACKEND=postgres" `
  --set-secrets $ExternalSecrets `
  --memory 1Gi `
  --cpu 1 `
  --max-retries 1 `
  --task-timeout 7200

gcloud.cmd run jobs deploy placeup-taxonomy-role-backfill `
  --image $Image `
  --region $Region `
  --service-account "placeup-etl-sa@$ProjectId.iam.gserviceaccount.com" `
  --command python `
  --args="-m,app.etl.taxonomy_role_backfill" `
  --set-cloudsql-instances "$ProjectId`:$Region`:$DbInstance" `
  --set-env-vars "APP_ENV=production,DATABASE_BACKEND=postgres" `
  --set-secrets $ExternalSecrets `
  --memory 2Gi `
  --cpu 2 `
  --max-retries 1 `
  --task-timeout 7200

gcloud.cmd run jobs deploy placeup-h1b-import `
  --image $Image `
  --region $Region `
  --service-account "placeup-etl-sa@$ProjectId.iam.gserviceaccount.com" `
  --command python `
  --args="-m,app.etl.import_h1b_sponsors,--force" `
  --set-cloudsql-instances "$ProjectId`:$Region`:$DbInstance" `
  --set-env-vars "APP_ENV=production,DATABASE_BACKEND=postgres" `
  --set-secrets "DATABASE_URL=DATABASE_URL:latest"

gcloud.cmd run jobs deploy placeup-daily-match-digest `
  --image $Image `
  --region $Region `
  --service-account "placeup-api-sa@$ProjectId.iam.gserviceaccount.com" `
  --command python `
  --args="-m,app.etl.daily_match_digest" `
  --set-cloudsql-instances "$ProjectId`:$Region`:$DbInstance" `
  --set-env-vars $ApiEnv `
  --set-secrets $ApiSecrets `
  --memory 1Gi `
  --cpu 1 `
  --max-retries 1 `
  --task-timeout 1800

gcloud.cmd run jobs deploy placeup-linkedin-jd-repair `
  --image $Image `
  --region $Region `
  --service-account "placeup-etl-sa@$ProjectId.iam.gserviceaccount.com" `
  --command python `
  --args="-m,app.workers.linkedin_jd_repair,--limit,1000" `
  --set-cloudsql-instances "$ProjectId`:$Region`:$DbInstance" `
  --set-env-vars "APP_ENV=production,DATABASE_BACKEND=postgres" `
  --set-secrets "DATABASE_URL=DATABASE_URL:latest" `
  --memory 1Gi `
  --cpu 1 `
  --max-retries 1 `
  --task-timeout 3600

gcloud.cmd run jobs deploy placeup-stale-jobs-sweeper `
  --image $Image `
  --region $Region `
  --service-account "placeup-etl-sa@$ProjectId.iam.gserviceaccount.com" `
  --command python `
  --args="-m,app.workers.stale_jobs_sweeper,--retention-days,30" `
  --set-cloudsql-instances "$ProjectId`:$Region`:$DbInstance" `
  --set-env-vars "APP_ENV=production,DATABASE_BACKEND=postgres,JOB_RETENTION_DAYS=30" `
  --set-secrets "DATABASE_URL=DATABASE_URL:latest" `
  --memory 512Mi `
  --cpu 1 `
  --max-retries 1 `
  --task-timeout 600

$DigestScheduleUri = "https://$Region-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/$ProjectId/jobs/placeup-daily-match-digest:run"
$DigestScheduleJob = gcloud.cmd scheduler jobs describe placeup-daily-match-digest-9am `
  --location $Region `
  --format "value(name)" 2>$null

if ($DigestScheduleJob) {
  gcloud.cmd scheduler jobs update http placeup-daily-match-digest-9am `
    --location $Region `
    --schedule "0 9 * * *" `
    --time-zone "America/Chicago" `
    --uri $DigestScheduleUri `
    --http-method POST `
    --oauth-service-account-email "placeup-api-sa@$ProjectId.iam.gserviceaccount.com"
} else {
  gcloud.cmd scheduler jobs create http placeup-daily-match-digest-9am `
    --location $Region `
    --schedule "0 9 * * *" `
    --time-zone "America/Chicago" `
    --uri $DigestScheduleUri `
    --http-method POST `
    --oauth-service-account-email "placeup-api-sa@$ProjectId.iam.gserviceaccount.com"
}

Write-Host "Backend image, API, and ETL jobs deployed."

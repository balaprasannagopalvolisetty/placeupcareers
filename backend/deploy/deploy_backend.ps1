param(
  [Parameter(Mandatory=$true)][string]$ProjectId,
  [string]$Region = "us-east1",
  [string]$DbInstance = "placeup-backend",
  [string]$UserDatabaseBackend = "firestore",
  [string]$UserFirestoreProjectId = "placeup-firebase-641222668282",
  [string]$UserFirestoreDatabase = "(default)",
  [string]$FrontendUrl = "https://placeupcareer.com",
  # Scaling knobs. Defaults fit the CURRENT 20-vCPU regional quota
  # (2 vCPU x 10 instances). After a quota increase, raise ApiMaxInstances
  # here instead of editing the script body. See SCALING_PLAYBOOK.md.
  # ApiMinInstances was 3 (three 2-vCPU/2-GiB containers kept warm 24/7 =
  # the bulk of Cloud Run cost). Lowered to 1 for preview-stage traffic: one
  # warm instance keeps logins fast while cutting ~2/3 of always-on cost.
  # Set to 0 to scale fully to zero (cheapest; adds a cold start on the first
  # request after idle).
  [int]$ApiMinInstances = 1,
  [int]$ApiMaxInstances = 10
)

$ErrorActionPreference = "Stop"
$Image = "$Region-docker.pkg.dev/$ProjectId/placeup/backend:latest"
# DB_STATEMENT_TIMEOUT_MS=15000: API queries fail fast into the stale-page
# cache instead of hanging when the scraper has Cloud SQL busy.
$ApiEnv = "APP_ENV=production,DATABASE_BACKEND=postgres,DB_POOL_SIZE=5,DB_MAX_OVERFLOW=10,DB_STATEMENT_TIMEOUT_MS=15000,USER_DATABASE_BACKEND=$UserDatabaseBackend,USER_FIRESTORE_PROJECT_ID=$UserFirestoreProjectId,USER_FIRESTORE_DATABASE=$UserFirestoreDatabase,SCRAPE_INTERVAL_HOURS=6,SCRAPEGRAPH_ENABLED=false,ADMIN_EMAILS=operations@placeupcareer.com,FREE_ACCESS_ENABLED=true,SIGNUP_REQUIRE_PAYMENT=false,INVITE_GATE_ENABLED=false,CONTACT_RECIPIENT_EMAIL=operations@placeupcareer.com"
if ($FrontendUrl) {
  $ApiEnv = "$ApiEnv,FRONTEND_URL=$FrontendUrl"
}
# DB_POOL_SIZE/DB_MAX_OVERFLOW=2: background jobs get a tiny connection
# budget so a running scrape can NEVER starve the user-facing API of
# database connections (the API keeps the default 5+10 per instance).
$ScraperEnv = "APP_ENV=production,DATABASE_BACKEND=postgres,DB_POOL_SIZE=3,DB_MAX_OVERFLOW=3,SCRAPE_INTERVAL_HOURS=6,SCRAPEGRAPH_ENABLED=false,SCRAPEGRAPH_DISCOVERY_ENABLED=false,SCRAPEGRAPH_DISCOVERY_MAX_URLS=220,SCRAPEGRAPH_DISCOVERY_CONCURRENCY=3,SCRAPLING_DISCOVERY_MAX_TARGETS=1800,SCRAPLING_H1B_EXCEL_COMPANY_LIMIT=1400,SCRAPLING_DISCOVERY_CONCURRENCY=2,SCRAPE_MAX_CONCURRENCY=4,SCRAPER_PUBLIC_SOURCES=linkedin~indeed~glassdoor~ziprecruiter~google~usajobs~dice,SCRAPER_ROLE_BATCH_SIZE=4,SCRAPER_PUBLIC_BATCH_CONCURRENCY=3,SCRAPER_PUBLIC_MAX_BATCHES_PER_RUN=0,SCRAPER_RUN_BUDGET_SECONDS=0,SCRAPER_PROVIDER_BLOCK_COOLDOWN_SECONDS=1800,SCRAPER_PROVIDER_EMPTY_CIRCUIT_THRESHOLD=4,SCRAPER_PURGE_EXCEPT_TODAY=false,SCRAPER_COVERAGE_FLOOR_ENABLED=true,API_CONNECTOR_SOURCES=greenhouse~lever~ashby~smartrecruiters~career_site_feed~remoteok~remotive~jobicy,CAREER_SITE_FEED_LIMIT=2000,SCRAPE_GLASSDOOR_JOBSPY_ENABLED=true,SCRAPE_ZIPRECRUITER_JOBSPY_ENABLED=true,SCRAPER_JD_HYDRATE_MAX_JOBS=2500,SCRAPER_JD_HYDRATE_CONCURRENCY=8,SCRAPER_JD_HYDRATE_TIMEOUT_SECONDS=28,LINKEDIN_REQUESTS_PER_MINUTE=2,LINKEDIN_THIN_DESCRIPTION_CHARS=1200,LINKEDIN_ENRICH_MAX_JOBS_PER_RUN=0,LINKEDIN_ENRICH_CONCURRENCY=1,SCRAPER_CANONICAL_ROLE_BATCH_SIZE=3"
$ApiSecrets = "DATABASE_URL=DATABASE_URL:latest,JWT_SECRET=JWT_SECRET:latest,USAJOBS_API_KEY=USAJOBS_API_KEY:latest,USAJOBS_EMAIL=USAJOBS_EMAIL:latest,HUNTER_API_KEY=HUNTER_API_KEY:latest"
$ScraperSecrets = "DATABASE_URL=DATABASE_URL:latest,USAJOBS_API_KEY=USAJOBS_API_KEY:latest,USAJOBS_EMAIL=USAJOBS_EMAIL:latest,HUNTER_API_KEY=HUNTER_API_KEY:latest"
$ExternalSecrets = "DATABASE_URL=DATABASE_URL:latest,USAJOBS_API_KEY=USAJOBS_API_KEY:latest,USAJOBS_EMAIL=USAJOBS_EMAIL:latest"

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

# Hosted payment links intentionally not bound while FREE_ACCESS_ENABLED=true.

# Email provider secrets - REQUIRED for OTP/MFA emails, signup verification,
# and password reset. Bound automatically whenever the secret exists so a
# redeploy can never strip email capability from the API.
foreach ($EmailSecretName in @("RESEND_API_KEY", "SENDGRID_API_KEY", "SMTP_PASSWORD")) {
  if (Test-SecretExists $EmailSecretName) {
    $ApiSecrets = "$ApiSecrets,$EmailSecretName=$EmailSecretName`:latest"
  }
}

$InternalApiSecret = Test-SecretExists "INTERNAL_API_KEY"
if ($InternalApiSecret) {
  $ApiSecrets = "$ApiSecrets,INTERNAL_API_KEY=INTERNAL_API_KEY:latest"
}
$ServiceTokenSecret = Test-SecretExists "SERVICE_TOKEN_SECRET"
if ($ServiceTokenSecret) {
  $ApiSecrets = "$ApiSecrets,SERVICE_TOKEN_SECRET=SERVICE_TOKEN_SECRET:latest"
  $ScraperSecrets = "$ScraperSecrets,SERVICE_TOKEN_SECRET=SERVICE_TOKEN_SECRET:latest"
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
$AdzunaAppIdSecret = Test-SecretExists "ADZUNA_APP_ID"
if ($AdzunaAppIdSecret) {
  $ApiSecrets = "$ApiSecrets,ADZUNA_APP_ID=ADZUNA_APP_ID:latest"
  $ScraperSecrets = "$ScraperSecrets,ADZUNA_APP_ID=ADZUNA_APP_ID:latest"
}
$AdzunaAppKeySecret = Test-SecretExists "ADZUNA_APP_KEY"
if ($AdzunaAppKeySecret) {
  $ApiSecrets = "$ApiSecrets,ADZUNA_APP_KEY=ADZUNA_APP_KEY:latest"
  $ScraperSecrets = "$ScraperSecrets,ADZUNA_APP_KEY=ADZUNA_APP_KEY:latest"
}
$GreenhouseTokensSecret = Test-SecretExists "GREENHOUSE_BOARD_TOKENS"
if ($GreenhouseTokensSecret) {
  $ScraperSecrets = "$ScraperSecrets,GREENHOUSE_BOARD_TOKENS=GREENHOUSE_BOARD_TOKENS:latest"
}
# Resolve the backend source dir from this script's location so the build
# works no matter where the script is invoked from. (It previously assumed a
# ./backend subfolder, which silently FAILED to build a new image when run
# from backend/ - every job then redeployed the stale :latest image.)
$BackendRoot = Split-Path -Parent $PSScriptRoot
gcloud.cmd builds submit $BackendRoot --tag $Image
if ($LASTEXITCODE -ne 0) {
  throw "Cloud Build failed - aborting deploy so services are not re-pointed at a stale image."
}

# IMPORTANT: the API service uses --update-env-vars / --update-secrets (MERGE
# semantics), NOT --set-* (REPLACE semantics). Auth-critical settings that are
# applied out-of-band - OTP_MFA_ENABLED, EMAIL_PROVIDER, EMAIL_FROM,
# RESEND_API_KEY, OIDC overrides (see OTP_MFA_SETUP.md) - used to be silently
# wiped on every deploy, which is what kept breaking sign-in/sign-up after
# each backend push. Merge semantics preserve anything this script doesn't
# explicitly manage.
gcloud.cmd run deploy placeup-api `
  --image $Image `
  --region $Region `
  --service-account "placeup-api-sa@$ProjectId.iam.gserviceaccount.com" `
  --no-invoker-iam-check `
  --set-cloudsql-instances "$ProjectId`:$Region`:$DbInstance" `
  --update-env-vars $ApiEnv `
  --update-secrets $ApiSecrets `
  --memory 2Gi `
  --cpu 2 `
  --min-instances $ApiMinInstances `
  --max-instances $ApiMaxInstances `
  --concurrency 40 `
  --timeout 300
# NOTE: max-instances is capped at 10 because this project's regional quota is
# 20 vCPU (2 vCPU x 10 instances). The previous value of 80 made every deploy
# fail with "Quota violated: CpuAllocPerProjectRegion". 10 instances x 40
# concurrency = 400 concurrent requests, plenty for current traffic. If you
# need more, request a quota increase first: https://cloud.google.com/run/quotas
if ($LASTEXITCODE -ne 0) {
  throw "placeup-api deploy FAILED - the API is still running the previous image. Fix the error above and rerun."
}

gcloud.cmd run jobs deploy placeup-job-scraper-6h `
  --image $Image `
  --region $Region `
  --service-account "placeup-etl-sa@$ProjectId.iam.gserviceaccount.com" `
  --command python `
  --args="-m,app.etl.jobs_scraper_6h" `
  --set-cloudsql-instances "$ProjectId`:$Region`:$DbInstance" `
  --set-env-vars $ScraperEnv `
  --set-secrets $ScraperSecrets `
  --memory 4Gi `
  --cpu 2 `
  --max-retries 2 `
  --task-timeout 168h

gcloud.cmd run jobs deploy placeup-backfill-catchup `
  --image $Image `
  --region $Region `
  --service-account "placeup-etl-sa@$ProjectId.iam.gserviceaccount.com" `
  --command python `
  --args="-m,app.etl.backfill_catchup,--hours-old,720" `
  --set-cloudsql-instances "$ProjectId`:$Region`:$DbInstance" `
  --set-env-vars $ScraperEnv `
  --set-secrets $ScraperSecrets `
  --memory 4Gi `
  --cpu 2 `
  --max-retries 1 `
  --task-timeout 168h

# placeup-external-api-12h is retired. RapidAPI is intentionally not bound to
# scheduled jobs; the free public and ATS connectors remain in the 6h scraper.
# Delete the stale Cloud Run job once if it still exists:
#   gcloud run jobs delete placeup-external-api-12h --region us-east1 --project <ProjectId>

gcloud.cmd run jobs deploy placeup-taxonomy-role-backfill `
  --image $Image `
  --region $Region `
  --service-account "placeup-etl-sa@$ProjectId.iam.gserviceaccount.com" `
  --command python `
  --args="-m,app.etl.taxonomy_role_backfill" `
  --set-cloudsql-instances "$ProjectId`:$Region`:$DbInstance" `
  --set-env-vars "APP_ENV=production,DATABASE_BACKEND=postgres,DB_POOL_SIZE=2,DB_MAX_OVERFLOW=2,LINKEDIN_REQUESTS_PER_MINUTE=4,LINKEDIN_THIN_DESCRIPTION_CHARS=1200,LINKEDIN_REPAIR_THIN_DESCRIPTION_CHARS=1200,LINKEDIN_ENRICH_MAX_JOBS_PER_RUN=500,LINKEDIN_ENRICH_CONCURRENCY=1" `
  --set-secrets $ExternalSecrets `
  --memory 2Gi `
  --cpu 2 `
  --max-retries 1 `
  --task-timeout 21600

# One-shot / re-runnable: relabels stored jobs + master_jobs with the global
# visa metadata (visa_country, visa_programs, english_friendly,
# sponsor_verified via the visa_sponsors/h1b_sponsors registries). Default is
# only rows missing labels; pass --all in an execution override to redo all.
gcloud.cmd run jobs deploy placeup-visa-label-backfill `
  --image $Image `
  --region $Region `
  --service-account "placeup-etl-sa@$ProjectId.iam.gserviceaccount.com" `
  --command python `
  --args="-m,app.etl.visa_label_backfill" `
  --set-cloudsql-instances "$ProjectId`:$Region`:$DbInstance" `
  --set-env-vars "APP_ENV=production,DATABASE_BACKEND=postgres,DB_POOL_SIZE=2,DB_MAX_OVERFLOW=2,DB_STATEMENT_TIMEOUT_MS=0" `
  --set-secrets "DATABASE_URL=DATABASE_URL:latest" `
  --memory 4Gi `
  --cpu 2 `
  --max-retries 1 `
  --task-timeout 21600

gcloud.cmd run jobs deploy placeup-h1b-import `
  --image $Image `
  --region $Region `
  --service-account "placeup-etl-sa@$ProjectId.iam.gserviceaccount.com" `
  --command python `
  --args="-m,app.etl.import_h1b_sponsors,--force" `
  --set-cloudsql-instances "$ProjectId`:$Region`:$DbInstance" `
  --set-env-vars "APP_ENV=production,DATABASE_BACKEND=postgres,DB_POOL_SIZE=2,DB_MAX_OVERFLOW=2" `
  --set-secrets "DATABASE_URL=DATABASE_URL:latest"

gcloud.cmd run jobs deploy placeup-visa-sponsor-import `
  --image $Image `
  --region $Region `
  --service-account "placeup-etl-sa@$ProjectId.iam.gserviceaccount.com" `
  --command python `
  --args="-m,app.etl.import_visa_sponsors,--force-h1b" `
  --set-cloudsql-instances "$ProjectId`:$Region`:$DbInstance" `
  --set-env-vars "APP_ENV=production,DATABASE_BACKEND=postgres,DB_POOL_SIZE=2,DB_MAX_OVERFLOW=2" `
  --set-secrets "DATABASE_URL=DATABASE_URL:latest" `
  --memory 2Gi `
  --cpu 1 `
  --max-retries 1 `
  --task-timeout 7200

# Batch job: no statement timeout (digest queries can be long), tiny pool.
$DigestEnv = $ApiEnv.Replace("DB_STATEMENT_TIMEOUT_MS=15000", "DB_STATEMENT_TIMEOUT_MS=0").Replace("DB_POOL_SIZE=5,DB_MAX_OVERFLOW=10", "DB_POOL_SIZE=2,DB_MAX_OVERFLOW=2")
gcloud.cmd run jobs deploy placeup-daily-match-digest `
  --image $Image `
  --region $Region `
  --service-account "placeup-api-sa@$ProjectId.iam.gserviceaccount.com" `
  --command python `
  --args="-m,app.etl.daily_match_digest" `
  --set-cloudsql-instances "$ProjectId`:$Region`:$DbInstance" `
  --set-env-vars $DigestEnv `
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
  --args="-m,app.workers.linkedin_jd_repair,--limit,5000" `
  --set-cloudsql-instances "$ProjectId`:$Region`:$DbInstance" `
  --set-env-vars "APP_ENV=production,DATABASE_BACKEND=postgres,DB_POOL_SIZE=2,DB_MAX_OVERFLOW=2,LINKEDIN_REQUESTS_PER_MINUTE=4,LINKEDIN_THIN_DESCRIPTION_CHARS=1200,LINKEDIN_REPAIR_THIN_DESCRIPTION_CHARS=1200,LINKEDIN_ENRICH_MAX_JOBS_PER_RUN=500,LINKEDIN_ENRICH_CONCURRENCY=1,LINKEDIN_REPAIR_CONCURRENCY=1" `
  --set-secrets "DATABASE_URL=DATABASE_URL:latest" `
  --memory 1Gi `
  --cpu 1 `
  --max-retries 1 `
  --task-timeout 7200

gcloud.cmd run jobs deploy placeup-job-description-repair `
  --image $Image `
  --region $Region `
  --service-account "placeup-etl-sa@$ProjectId.iam.gserviceaccount.com" `
  --command python `
  --args="-m,app.workers.job_description_repair,--limit,5000,--concurrency,6" `
  --set-cloudsql-instances "$ProjectId`:$Region`:$DbInstance" `
  --set-env-vars "APP_ENV=production,DATABASE_BACKEND=postgres,DB_POOL_SIZE=2,DB_MAX_OVERFLOW=2" `
  --set-secrets "DATABASE_URL=DATABASE_URL:latest" `
  --memory 1Gi `
  --cpu 1 `
  --max-retries 1 `
  --task-timeout 7200

# Walks the COMPLETE sponsor-company universe (visa_sponsors registries for
# every target country + h1b_sponsors) and harvests entire ATS boards:
# first-party postings with direct apply links for ALL employers who can
# sponsor - independent of what third-party scrapers happen to find.
gcloud.cmd run jobs deploy placeup-board-discovery-sweep `
  --image $Image `
  --region $Region `
  --service-account "placeup-etl-sa@$ProjectId.iam.gserviceaccount.com" `
  --command python `
  --args="-m,app.workers.board_discovery_sweep,--limit,800,--concurrency,1" `
  --set-cloudsql-instances "$ProjectId`:$Region`:$DbInstance" `
  --set-env-vars "APP_ENV=production,DATABASE_BACKEND=postgres,DB_POOL_SIZE=2,DB_MAX_OVERFLOW=2" `
  --set-secrets "DATABASE_URL=DATABASE_URL:latest" `
  --memory 1Gi `
  --cpu 1 `
  --max-retries 1 `
  --task-timeout 21600

# Resolves each third-party posting (LinkedIn/Dice/Glassdoor/...) to the
# employer's OFFICIAL careers page / ATS posting and upgrades the JD +
# "Apply on Company Website" link. Runs after every scraper cycle.
gcloud.cmd run jobs deploy placeup-company-link-resolver `
  --image $Image `
  --region $Region `
  --service-account "placeup-etl-sa@$ProjectId.iam.gserviceaccount.com" `
  --command python `
  --args="-m,app.workers.company_link_resolver,--limit,400,--concurrency,5" `
  --set-cloudsql-instances "$ProjectId`:$Region`:$DbInstance" `
  --set-env-vars "APP_ENV=production,DATABASE_BACKEND=postgres,DB_POOL_SIZE=2,DB_MAX_OVERFLOW=2" `
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
  --set-env-vars "APP_ENV=production,DATABASE_BACKEND=postgres,DB_POOL_SIZE=2,DB_MAX_OVERFLOW=2,JOB_RETENTION_DAYS=30" `
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

$VisaSponsorScheduleUri = "https://$Region-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/$ProjectId/jobs/placeup-visa-sponsor-import:run"
$previousErrorAction = $ErrorActionPreference
$ErrorActionPreference = "Continue"
$VisaSponsorScheduleJob = & gcloud.cmd scheduler jobs describe placeup-visa-sponsor-import-monthly `
  --location $Region `
  --format "value(name)" 2>$null
$VisaSponsorScheduleExists = $LASTEXITCODE -eq 0
$ErrorActionPreference = $previousErrorAction

if ($VisaSponsorScheduleExists) {
  gcloud.cmd scheduler jobs update http placeup-visa-sponsor-import-monthly `
    --location $Region `
    --schedule "0 3 1 * *" `
    --time-zone "America/Chicago" `
    --uri $VisaSponsorScheduleUri `
    --http-method POST `
    --oauth-service-account-email "placeup-etl-sa@$ProjectId.iam.gserviceaccount.com"
} else {
  gcloud.cmd scheduler jobs create http placeup-visa-sponsor-import-monthly `
    --location $Region `
    --schedule "0 3 1 * *" `
    --time-zone "America/Chicago" `
    --uri $VisaSponsorScheduleUri `
    --http-method POST `
    --oauth-service-account-email "placeup-etl-sa@$ProjectId.iam.gserviceaccount.com"
}

# Company link resolver: every 2 hours, offset from the 6h scraper so fresh
# rows get official career links + first-party JDs shortly after ingest.
$LinkResolverScheduleUri = "https://$Region-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/$ProjectId/jobs/placeup-company-link-resolver:run"
$previousErrorAction = $ErrorActionPreference
$ErrorActionPreference = "Continue"
$LinkResolverScheduleJob = & gcloud.cmd scheduler jobs describe placeup-company-link-resolver-2h `
  --location $Region `
  --format "value(name)" 2>$null
$LinkResolverScheduleExists = $LASTEXITCODE -eq 0
$ErrorActionPreference = $previousErrorAction

if ($LinkResolverScheduleExists) {
  gcloud.cmd scheduler jobs update http placeup-company-link-resolver-2h `
    --location $Region `
    --schedule "30 */2 * * *" `
    --time-zone "America/Chicago" `
    --uri $LinkResolverScheduleUri `
    --http-method POST `
    --oauth-service-account-email "placeup-etl-sa@$ProjectId.iam.gserviceaccount.com"
} else {
  gcloud.cmd scheduler jobs create http placeup-company-link-resolver-2h `
    --location $Region `
    --schedule "30 */2 * * *" `
    --time-zone "America/Chicago" `
    --uri $LinkResolverScheduleUri `
    --http-method POST `
    --oauth-service-account-email "placeup-etl-sa@$ProjectId.iam.gserviceaccount.com"
}

gcloud.cmd run jobs add-iam-policy-binding placeup-company-link-resolver `
  --region $Region `
  --member "serviceAccount:placeup-etl-sa@$ProjectId.iam.gserviceaccount.com" `
  --role roles/run.invoker

# JD repair: every 2 hours, after the company-link resolver starts, backfills
# thin descriptions that came from public cards or partially populated feeds.
$JobDescriptionRepairScheduleUri = "https://$Region-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/$ProjectId/jobs/placeup-job-description-repair:run"
$previousErrorAction = $ErrorActionPreference
$ErrorActionPreference = "Continue"
$JobDescriptionRepairScheduleJob = & gcloud.cmd scheduler jobs describe placeup-job-description-repair-2h `
  --location $Region `
  --format "value(name)" 2>$null
$JobDescriptionRepairScheduleExists = $LASTEXITCODE -eq 0
$ErrorActionPreference = $previousErrorAction

if ($JobDescriptionRepairScheduleExists) {
  gcloud.cmd scheduler jobs update http placeup-job-description-repair-2h `
    --location $Region `
    --schedule "45 */2 * * *" `
    --time-zone "America/Chicago" `
    --uri $JobDescriptionRepairScheduleUri `
    --http-method POST `
    --oauth-service-account-email "placeup-etl-sa@$ProjectId.iam.gserviceaccount.com"
} else {
  gcloud.cmd scheduler jobs create http placeup-job-description-repair-2h `
    --location $Region `
    --schedule "45 */2 * * *" `
    --time-zone "America/Chicago" `
    --uri $JobDescriptionRepairScheduleUri `
    --http-method POST `
    --oauth-service-account-email "placeup-etl-sa@$ProjectId.iam.gserviceaccount.com"
}

gcloud.cmd run jobs add-iam-policy-binding placeup-job-description-repair `
  --region $Region `
  --member "serviceAccount:placeup-etl-sa@$ProjectId.iam.gserviceaccount.com" `
  --role roles/run.invoker

# Board discovery sweep: every 6 hours, up to 800 sponsor companies per run
# (~3,200/day). Checkpointed in board_sweep_state, so it cycles through the
# full registry and re-visits each company every 30 days.
$BoardSweepScheduleUri = "https://$Region-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/$ProjectId/jobs/placeup-board-discovery-sweep:run"
$previousErrorAction = $ErrorActionPreference
$ErrorActionPreference = "Continue"
$BoardSweepScheduleJob = & gcloud.cmd scheduler jobs describe placeup-board-discovery-sweep-6h `
  --location $Region `
  --format "value(name)" 2>$null
$BoardSweepScheduleExists = $LASTEXITCODE -eq 0
$ErrorActionPreference = $previousErrorAction

if ($BoardSweepScheduleExists) {
  gcloud.cmd scheduler jobs update http placeup-board-discovery-sweep-6h `
    --location $Region `
    --schedule "0 */6 * * *" `
    --time-zone "America/Chicago" `
    --uri $BoardSweepScheduleUri `
    --http-method POST `
    --oauth-service-account-email "placeup-etl-sa@$ProjectId.iam.gserviceaccount.com"
} else {
  gcloud.cmd scheduler jobs create http placeup-board-discovery-sweep-6h `
    --location $Region `
    --schedule "0 */6 * * *" `
    --time-zone "America/Chicago" `
    --uri $BoardSweepScheduleUri `
    --http-method POST `
    --oauth-service-account-email "placeup-etl-sa@$ProjectId.iam.gserviceaccount.com"
}

gcloud.cmd run jobs add-iam-policy-binding placeup-board-discovery-sweep `
  --region $Region `
  --member "serviceAccount:placeup-etl-sa@$ProjectId.iam.gserviceaccount.com" `
  --role roles/run.invoker

Write-Host "Backend image, API, and ETL jobs deployed."

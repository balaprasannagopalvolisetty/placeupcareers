param(
  [Parameter(Mandatory=$true)][string]$ProjectId,
  [string]$Region = "us-east1",
  [string]$DbInstance = "placeup-backend",
  [string]$Image = "",
  [string[]]$Countries = @(
    "US","CA","GB","IE","DE","NL","AU","NZ","SG","AE","JP","PT",
    "FR","ES","SE","DK","NO","CH","FI","BE","AT","PL","EE","QA","SA",
    "IT","LU","KR","TW","HK","CZ","IN"
  ),
  [switch]$CreateSchedulers
)

$ErrorActionPreference = "Stop"

if (-not $Image) {
  $Image = & gcloud.cmd run services describe placeup-api `
    --project $ProjectId --region $Region `
    --format "value(spec.template.spec.containers[0].image)"
  if (-not $Image) { throw "Could not resolve image from placeup-api. Pass -Image." }
}

$baseEnv = "APP_ENV=production,DATABASE_BACKEND=postgres,DB_POOL_SIZE=2,DB_MAX_OVERFLOW=2,SCRAPE_INTERVAL_HOURS=6,SCRAPEGRAPH_ENABLED=false,SCRAPEGRAPH_DISCOVERY_ENABLED=false,SCRAPLING_DISCOVERY_MAX_TARGETS=120,SCRAPLING_H1B_EXCEL_COMPANY_LIMIT=200,SCRAPLING_DISCOVERY_CONCURRENCY=2,SCRAPE_MAX_CONCURRENCY=3,SCRAPER_PUBLIC_SOURCES=linkedin~indeed~glassdoor~ziprecruiter~google~usajobs~dice,SCRAPER_ROLE_BATCH_SIZE=4,SCRAPER_PUBLIC_BATCH_CONCURRENCY=2,SCRAPER_PUBLIC_MAX_BATCHES_PER_RUN=12,SCRAPER_RUN_BUDGET_SECONDS=12600,SCRAPER_RECENCY_HOURS=24,SCRAPER_PROVIDER_BLOCK_COOLDOWN_SECONDS=1800,SCRAPER_PROVIDER_EMPTY_CIRCUIT_THRESHOLD=4,SCRAPER_PURGE_EXCEPT_TODAY=false,SCRAPER_COVERAGE_FLOOR_ENABLED=false,SCRAPER_BOARD_PASS_ENABLED=false,API_CONNECTOR_SOURCES=career_site_feed~remoteok~remotive~jobicy,CAREER_SITE_FEED_LIMIT=250,SCRAPE_GLASSDOOR_JOBSPY_ENABLED=true,SCRAPE_ZIPRECRUITER_JOBSPY_ENABLED=true,SCRAPER_JD_HYDRATE_MAX_JOBS=400,SCRAPER_JD_HYDRATE_CONCURRENCY=8,SCRAPER_JD_HYDRATE_TIMEOUT_SECONDS=22,LINKEDIN_REQUESTS_PER_MINUTE=2,LINKEDIN_THIN_DESCRIPTION_CHARS=1200,LINKEDIN_ENRICH_MAX_JOBS_PER_RUN=0,LINKEDIN_ENRICH_CONCURRENCY=1,SCRAPER_CANONICAL_ROLE_BATCH_SIZE=3"
$secrets = "DATABASE_URL=DATABASE_URL:latest,USAJOBS_API_KEY=USAJOBS_API_KEY:latest,USAJOBS_EMAIL=USAJOBS_EMAIL:latest,HUNTER_API_KEY=HUNTER_API_KEY:latest"

$index = 0
foreach ($country in $Countries) {
  $code = $country.Trim().ToUpperInvariant()
  if (-not $code) { continue }
  $jobName = "placeup-country-scraper-$($code.ToLowerInvariant())"
  $env = "$baseEnv,SCRAPER_TARGET_COUNTRIES=$code"
  Write-Host "Deploying $jobName for $code"
  & gcloud.cmd run jobs deploy $jobName `
    --project $ProjectId `
    --region $Region `
    --image $Image `
    --service-account "placeup-etl-sa@$ProjectId.iam.gserviceaccount.com" `
    --command python `
    --args="-m,app.etl.jobs_scraper_6h" `
    --set-cloudsql-instances "$ProjectId`:$Region`:$DbInstance" `
    --set-env-vars $env `
    --set-secrets $secrets `
    --memory 2Gi `
    --cpu 1 `
    --max-retries 0 `
    --task-timeout 18000
  if ($LASTEXITCODE -ne 0) { throw "$jobName deploy failed." }

  if ($CreateSchedulers) {
    $minute = ($index * 2) % 60
    $hourOffset = [Math]::Floor(($index * 2) / 60)
    $schedule = "$minute */6 * * *"
    $schedulerName = "$jobName-6h"
    $uri = "https://$Region-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/$ProjectId/jobs/$jobName`:run"
    $previousErrorAction = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
      & gcloud.cmd scheduler jobs describe $schedulerName --project $ProjectId --location $Region *> $null
      $schedulerExists = $LASTEXITCODE -eq 0
    } finally {
      $ErrorActionPreference = $previousErrorAction
    }
    if ($schedulerExists) {
      & gcloud.cmd scheduler jobs update http $schedulerName `
        --project $ProjectId --location $Region `
        --schedule $schedule --time-zone "America/Chicago" `
        --uri $uri --http-method POST `
        --oauth-service-account-email "placeup-etl-sa@$ProjectId.iam.gserviceaccount.com" `
        --oauth-token-scope "https://www.googleapis.com/auth/cloud-platform"
    } else {
      & gcloud.cmd scheduler jobs create http $schedulerName `
        --project $ProjectId --location $Region `
        --schedule $schedule --time-zone "America/Chicago" `
        --uri $uri --http-method POST `
        --oauth-service-account-email "placeup-etl-sa@$ProjectId.iam.gserviceaccount.com" `
        --oauth-token-scope "https://www.googleapis.com/auth/cloud-platform"
    }
    if ($LASTEXITCODE -ne 0) { throw "$schedulerName scheduler update failed." }
    $index += 1
  }
}

Write-Host "Done. Deployed $($Countries.Count) country scraper jobs."

param(
  [Parameter(Mandatory=$true)][string]$ProjectId,
  [string]$Region = "us-east1",
  [string]$TimeZone = "America/Chicago"
)

$ErrorActionPreference = "Stop"
gcloud.cmd config set project $ProjectId

$JobRunBase = "https://$Region-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/$ProjectId/jobs"
$SchedulerSa = "placeup-scheduler-sa@$ProjectId.iam.gserviceaccount.com"

function Upsert-SchedulerJob {
  param(
    [string]$Name,
    [string]$Schedule,
    [string]$Uri
  )

  $previousErrorAction = $ErrorActionPreference
  $ErrorActionPreference = "Continue"
  try {
    gcloud.cmd scheduler jobs describe $Name --location $Region --project $ProjectId *> $null
    $exists = $LASTEXITCODE -eq 0
  } finally {
    $ErrorActionPreference = $previousErrorAction
  }

  if ($exists) {
    gcloud.cmd scheduler jobs update http $Name `
      --location $Region `
      --schedule $Schedule `
      --time-zone $TimeZone `
      --uri $Uri `
      --http-method POST `
      --oauth-service-account-email $SchedulerSa
  } else {
    gcloud.cmd scheduler jobs create http $Name `
      --location $Region `
      --schedule $Schedule `
      --time-zone $TimeZone `
      --uri $Uri `
      --http-method POST `
      --oauth-service-account-email $SchedulerSa
  }
}

Upsert-SchedulerJob `
  -Name "placeup-job-scraper-6h" `
  -Schedule "0 */6 * * *" `
  -Uri "$JobRunBase/placeup-job-scraper-6h:run"

Upsert-SchedulerJob `
  -Name "placeup-external-api-12h" `
  -Schedule "30 */12 * * *" `
  -Uri "$JobRunBase/placeup-external-api-12h:run"

Upsert-SchedulerJob `
  -Name "placeup-taxonomy-role-backfill" `
  -Schedule "15 2 * * *" `
  -Uri "$JobRunBase/placeup-taxonomy-role-backfill:run"

# Daily ops digest — pulls deduped (company, location) rows from
# master_jobs, emails the CSV to operations@placeupcareer.com, and
# (when COMPANIES_EXPORT_SHEET_ID is set) syncs to a Google Sheet.
# 06:00 in the configured time zone lands a fresh list in the team's
# inbox right at the start of the workday.
Upsert-SchedulerJob `
  -Name "placeup-companies-export-daily" `
  -Schedule "0 6 * * *" `
  -Uri "$JobRunBase/placeup-companies-export:run"

# Daily stale-jobs sweeper — flips status='inactive' on any posting
# whose last_seen_at is older than job_inactive_after_days (default
# 14d). Keeps the Jobs page honest: roles that fell off the source
# ATS stop appearing as "active" in the dashboard.
Upsert-SchedulerJob `
  -Name "placeup-stale-jobs-sweeper-daily" `
  -Schedule "30 3 * * *" `
  -Uri "$JobRunBase/placeup-stale-jobs-sweeper:run"

# Daily FinalScout multi-key enrichment. Runs at 04:00 local — well
# after stale-jobs sweeper, before the morning ops digest at 06:00, so
# the new emails it discovers land in the operations Sheet the same day.
Upsert-SchedulerJob `
  -Name "placeup-finalscout-batch-daily" `
  -Schedule "0 4 * * *" `
  -Uri "$JobRunBase/placeup-finalscout-batch:run"

Write-Host "Cloud Scheduler jobs created."

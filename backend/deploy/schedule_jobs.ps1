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
    [string]$Uri,
    [string]$Tz = ""
  )
  if (-not $Tz) { $Tz = $TimeZone }

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
      --time-zone $Tz `
      --uri $Uri `
      --http-method POST `
      --oauth-service-account-email $SchedulerSa
  } else {
    gcloud.cmd scheduler jobs create http $Name `
      --location $Region `
      --schedule $Schedule `
      --time-zone $Tz `
      --uri $Uri `
      --http-method POST `
      --oauth-service-account-email $SchedulerSa
  }
}

# Job scraper — twice daily at 11:00 and 20:00 US Eastern (ops request
# 2026-07-11). Two scheduler jobs trigger the same Cloud Run job; the
# in-code advisory lock prevents overlap, and the scraper emails
# operations@placeupcareer.com on failures (SCRAPER_ALERT_EMAIL env).
Upsert-SchedulerJob `
  -Name "placeup-job-scraper-am" `
  -Schedule "0 11 * * *" `
  -Tz "America/New_York" `
  -Uri "$JobRunBase/placeup-job-scraper-6h:run"

Upsert-SchedulerJob `
  -Name "placeup-job-scraper-pm" `
  -Schedule "0 20 * * *" `
  -Tz "America/New_York" `
  -Uri "$JobRunBase/placeup-job-scraper-6h:run"

# Retire the old every-6-hours trigger after the two ET jobs exist:
#   gcloud scheduler jobs delete placeup-job-scraper-6h --location us-east1

# NOTE: the separate placeup-external-api-12h job was removed. RapidAPI is
# intentionally disabled; the 6-hour job uses public and direct ATS sources.
# Delete the old
# scheduler job + Cloud Run job once (see PRODUCTION_DEPLOYMENT notes):
#   gcloud scheduler jobs delete placeup-external-api-12h --location us-east1
#   gcloud run jobs delete placeup-external-api-12h --region us-east1

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

# Verify a rotating batch of active apply URLs after each scraper cycle.
# The worker only deletes high-confidence closures; 403/429/timeouts remain.
Upsert-SchedulerJob `
  -Name "placeup-job-liveness-checker-6h" `
  -Schedule "45 */6 * * *" `
  -Uri "$JobRunBase/placeup-job-liveness-checker:run"

# Daily FinalScout multi-key enrichment. Runs at 04:00 local — well
# after stale-jobs sweeper, before the morning ops digest at 06:00, so
# the new emails it discovers land in the operations Sheet the same day.

# No Upsert-SchedulerJob call follows for FinalScout by design.
Write-Host "Cloud Scheduler jobs created."

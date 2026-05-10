param(
  [Parameter(Mandatory=$true)][string]$ProjectId,
  [string]$Region = "us-central1",
  [string]$TimeZone = "America/Chicago"
)

$ErrorActionPreference = "Stop"
gcloud.cmd config set project $ProjectId

$JobRunBase = "https://$Region-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/$ProjectId/jobs"
$SchedulerSa = "placeup-scheduler-sa@$ProjectId.iam.gserviceaccount.com"

gcloud.cmd scheduler jobs create http placeup-job-scraper-6h `
  --location $Region `
  --schedule "0 */6 * * *" `
  --time-zone $TimeZone `
  --uri "$JobRunBase/placeup-job-scraper-6h:run" `
  --http-method POST `
  --oauth-service-account-email $SchedulerSa 2>$null

gcloud.cmd scheduler jobs create http placeup-external-api-12h `
  --location $Region `
  --schedule "30 */12 * * *" `
  --time-zone $TimeZone `
  --uri "$JobRunBase/placeup-external-api-12h:run" `
  --http-method POST `
  --oauth-service-account-email $SchedulerSa 2>$null

Write-Host "Cloud Scheduler jobs created."

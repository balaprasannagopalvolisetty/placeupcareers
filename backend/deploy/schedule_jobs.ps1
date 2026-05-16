param(
  [Parameter(Mandatory=$true)][string]$ProjectId,
  [string]$Region = "us-central1",
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

  gcloud.cmd scheduler jobs describe $Name --location $Region --project $ProjectId *> $null
  if ($LASTEXITCODE -eq 0) {
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

Write-Host "Cloud Scheduler jobs created."

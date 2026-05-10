param(
  [Parameter(Mandatory=$true)][string]$ProjectId,
  [string]$Region = "us-east1",
  [string]$ScheduleRegion = "us-east1",
  [string]$TimeZone = "America/Chicago"
)

$ErrorActionPreference = "Stop"

gcloud.cmd config set project $ProjectId

$FunctionUrl = gcloud.cmd functions describe clean-and-load-jobs `
  --gen2 `
  --region $Region `
  --format "value(serviceConfig.uri)"

if ([string]::IsNullOrWhiteSpace($FunctionUrl)) {
  throw "Could not resolve function URL for clean-and-load-jobs."
}

gcloud.cmd scheduler jobs create http placeup-silver-loader-12h `
  --location $ScheduleRegion `
  --schedule "0 */12 * * *" `
  --time-zone $TimeZone `
  --uri $FunctionUrl `
  --http-method POST `
  --oidc-service-account-email "placeup-scheduler-sa@$ProjectId.iam.gserviceaccount.com" `
  --oidc-token-audience $FunctionUrl 2>$null

gcloud.cmd scheduler jobs update http placeup-silver-loader-12h `
  --location $ScheduleRegion `
  --schedule "0 */12 * * *" `
  --time-zone $TimeZone `
  --uri $FunctionUrl `
  --http-method POST `
  --oidc-service-account-email "placeup-scheduler-sa@$ProjectId.iam.gserviceaccount.com" `
  --oidc-token-audience $FunctionUrl

Write-Host "Cloud Scheduler job placeup-silver-loader-12h is configured for every 12 hours."

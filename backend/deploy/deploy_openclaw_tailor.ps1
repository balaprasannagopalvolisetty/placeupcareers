param(
    [Parameter(Mandatory = $true)][string]$ProjectId,
    [string]$Region = "us-east1",
    [string]$ProviderSecret = "openclaw-provider-api-key",
    [string]$ServiceTokenSecret = "openclaw-placeup-service-token",
    [string]$Model = "openai/gpt-5-mini"
)

$ErrorActionPreference = "Stop"
$Service = "placeup-openclaw-tailor"
$Image = "gcr.io/$ProjectId/$Service"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..\openclaw_service")

gcloud services enable run.googleapis.com cloudbuild.googleapis.com secretmanager.googleapis.com --project $ProjectId
$OpenClawServiceAccount = "placeup-openclaw-sa@$ProjectId.iam.gserviceaccount.com"
gcloud iam service-accounts describe $OpenClawServiceAccount --project $ProjectId 2>$null
if ($LASTEXITCODE -ne 0) {
    gcloud iam service-accounts create placeup-openclaw-sa --project $ProjectId --display-name "PlaceUp isolated OpenClaw tailoring"
}
gcloud builds submit $Root --tag $Image --project $ProjectId
gcloud run deploy $Service `
    --image $Image `
    --project $ProjectId `
    --region $Region `
    --service-account $OpenClawServiceAccount `
    --no-allow-unauthenticated `
    --ingress internal `
    --memory 2Gi `
    --cpu 2 `
    --concurrency 1 `
    --timeout 180 `
    --set-env-vars "OPENCLAW_MODEL=$Model" `
    --set-secrets "OPENAI_API_KEY=$ProviderSecret`:latest,PLACEUP_SERVICE_TOKEN=$ServiceTokenSecret`:latest"

$ApiServiceAccount = "placeup-api-sa@$ProjectId.iam.gserviceaccount.com"
gcloud run services add-iam-policy-binding $Service `
    --project $ProjectId --region $Region `
    --member "serviceAccount:$ApiServiceAccount" `
    --role roles/run.invoker

$Url = gcloud run services describe $Service --project $ProjectId --region $Region --format "value(status.url)"
Write-Host "OpenClaw tailoring service deployed privately at $Url"
Write-Host "Now set OPENCLAW_TAILOR_URL=$Url, OPENCLAW_TAILOR_ENABLED=true, and bind OPENCLAW_TAILOR_TOKEN on placeup-api."

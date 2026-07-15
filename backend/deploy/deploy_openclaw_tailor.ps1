param(
    [Parameter(Mandatory = $true)][string]$ProjectId,
    [string]$Region = "us-east1",
    [string]$ProviderSecret = "OLLAMA_API_KEY",
    [string]$ServiceTokenSecret = "openclaw-placeup-service-token",
    [string]$Model = "ollama-cloud/glm-5.2:cloud"
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
$ApiServiceAccount = "placeup-api-sa@$ProjectId.iam.gserviceaccount.com"
foreach ($SecretName in @($ProviderSecret, $ServiceTokenSecret)) {
    gcloud secrets describe $SecretName --project $ProjectId 2>$null | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Required Secret Manager secret '$SecretName' does not exist. Create it before deploying."
    }
}
gcloud secrets add-iam-policy-binding $ProviderSecret --project $ProjectId `
    --member "serviceAccount:$OpenClawServiceAccount" --role roles/secretmanager.secretAccessor | Out-Null
gcloud secrets add-iam-policy-binding $ServiceTokenSecret --project $ProjectId `
    --member "serviceAccount:$OpenClawServiceAccount" --role roles/secretmanager.secretAccessor | Out-Null
gcloud secrets add-iam-policy-binding $ServiceTokenSecret --project $ProjectId `
    --member "serviceAccount:$ApiServiceAccount" --role roles/secretmanager.secretAccessor | Out-Null
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
    --set-secrets "OLLAMA_API_KEY=$ProviderSecret`:latest,PLACEUP_SERVICE_TOKEN=$ServiceTokenSecret`:latest"

gcloud run services add-iam-policy-binding $Service `
    --project $ProjectId --region $Region `
    --member "serviceAccount:$ApiServiceAccount" `
    --role roles/run.invoker

$Url = gcloud run services describe $Service --project $ProjectId --region $Region --format "value(status.url)"
gcloud run services update placeup-api --project $ProjectId --region $Region `
    --update-env-vars "OPENCLAW_TAILOR_ENABLED=true,OPENCLAW_TAILOR_URL=$Url,OPENCLAW_TAILOR_TIMEOUT_SECONDS=120" `
    --update-secrets "OPENCLAW_TAILOR_TOKEN=$ServiceTokenSecret`:latest"
Write-Host "OpenClaw tailoring service deployed privately at $Url"
Write-Host "placeup-api is now configured to use the private OpenClaw GLM-5.2 tailoring service."

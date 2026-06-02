param(
  [Parameter(Mandatory=$true)][string]$ProjectId,
  [string]$Region = "us-east1",
  [string]$ApiBase = "",
  [string]$BackendOrigin = "https://placeup-api-641222668282.us-east1.run.app"
)

$ErrorActionPreference = "Stop"
$Image = "$Region-docker.pkg.dev/$ProjectId/placeup/frontend:latest"

function Invoke-Gcloud {
  & gcloud.cmd @args
  if ($LASTEXITCODE -ne 0) {
    throw "gcloud command failed: $($args -join ' ')"
  }
}

Invoke-Gcloud config set project $ProjectId

Invoke-Gcloud services enable `
  run.googleapis.com `
  artifactregistry.googleapis.com `
  cloudbuild.googleapis.com `
  logging.googleapis.com

$repoName = & gcloud.cmd artifacts repositories list `
  --location=$Region `
  --project=$ProjectId `
  --format="value(name)"
if ($LASTEXITCODE -ne 0) {
  throw "gcloud command failed: artifacts repositories list"
}

if (@($repoName) -notcontains "placeup") {
  Invoke-Gcloud artifacts repositories create placeup `
    --repository-format=docker `
    --location=$Region `
    --description="PlaceUp frontend containers"
}

Invoke-Gcloud builds submit . `
  --config cloudbuild.yaml `
  --substitutions "_IMAGE=$Image,_VITE_API_BASE=$ApiBase"

Invoke-Gcloud run deploy placeup-frontend `
  --image $Image `
  --region $Region `
  --no-invoker-iam-check `
  --port 8080 `
  --min-instances 1 `
  --max-instances 20 `
  --concurrency 200 `
  --set-env-vars "APP_ENV=production,BACKEND_ORIGIN=$BackendOrigin"

$FrontendUrl = & gcloud.cmd run services describe placeup-frontend `
  --region $Region `
  --project $ProjectId `
  --format "value(status.url)"
if ($LASTEXITCODE -ne 0) {
  throw "gcloud command failed: run services describe placeup-frontend"
}

Write-Host "Frontend deployed: $FrontendUrl"
Write-Host "If you use a custom domain, point it to this Cloud Run service."

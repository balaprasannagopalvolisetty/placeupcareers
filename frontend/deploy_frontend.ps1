param(
  [Parameter(Mandatory=$true)][string]$ProjectId,
  [string]$Region = "us-central1",
  [string]$ApiBase = ""
)

$ErrorActionPreference = "Stop"
$Image = "$Region-docker.pkg.dev/$ProjectId/placeup/frontend:latest"

gcloud.cmd config set project $ProjectId
gcloud.cmd builds submit . `
  --config cloudbuild.yaml `
  --substitutions "_IMAGE=$Image,_VITE_API_BASE=$ApiBase"

gcloud.cmd run deploy placeup-frontend `
  --image $Image `
  --region $Region `
  --allow-unauthenticated `
  --port 8080 `
  --set-env-vars "APP_ENV=production"

Write-Host "Frontend deployed. If you use a custom domain, point it to this Cloud Run service."

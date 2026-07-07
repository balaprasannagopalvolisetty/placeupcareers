# Deploys the internal APPLICATION SERVER (placeup-app) as a second Cloud Run
# service from the same image as the web API. See HYBRID_ARCHITECTURE.md.
#
#   .\deploy_app_server.ps1                       # reuse placeup-api's image
#   .\deploy_app_server.ps1 -Image <image-url>    # or pin one explicitly
#
# Trust chain: this service refuses every request that doesn't carry a
# service token minted by the web server (SERVER_ROLE=app gate), and
# ingress=internal keeps the public internet from reaching it at all.

param(
  [string]$ProjectId = "steel-shine-492401-u6",
  [string]$Region = "us-east1",
  [string]$WebService = "placeup-api",
  [string]$AppService = "placeup-app",
  [string]$Image = ""
)

$ErrorActionPreference = "Stop"

if (-not $Image) {
  Write-Host "Resolving current image of $WebService..."
  $Image = & gcloud.cmd run services describe $WebService `
    --project $ProjectId --region $Region `
    --format "value(spec.template.spec.containers[0].image)"
  if (-not $Image) { throw "Could not resolve image from $WebService. Pass -Image." }
}
Write-Host "Deploying $AppService from image: $Image"

# Secrets expected in Secret Manager (same values as the web service):
#   DATABASE_URL          -> Supabase session-pooler URL
#   SERVICE_TOKEN_SECRET  -> same strong random value on BOTH services
#   JWT_SECRET            -> same as web (service tokens fall back to it)
& gcloud.cmd run deploy $AppService `
  --project $ProjectId `
  --region $Region `
  --image $Image `
  --ingress internal `
  --no-allow-unauthenticated `
  --min-instances 0 `
  --max-instances 2 `
  --memory 1Gi `
  --set-env-vars "SERVER_ROLE=app,APP_ENV=production,USER_DATABASE_BACKEND=firestore" `
  --set-secrets "DATABASE_URL=DATABASE_URL_SUPABASE:latest,SERVICE_TOKEN_SECRET=SERVICE_TOKEN_SECRET:latest,JWT_SECRET=JWT_SECRET:latest"

Write-Host ""
Write-Host "Done. Next:"
Write-Host " 1. Set APP_SERVER_URL on $WebService to this service's URL:"
& gcloud.cmd run services describe $AppService --project $ProjectId --region $Region --format "value(status.url)"
Write-Host " 2. Point Cloud Scheduler scrape triggers at $AppService (OIDC or service token)."
Write-Host " 3. Verify the gate: curl <app-url>/api/jobs  ->  must return 403."

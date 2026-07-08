param(
  [Parameter(Mandatory=$true)][string]$ProjectId,
  [string]$Region = "us-east1",
  [string]$DbInstance = "placeup-backend",
  [string]$WebService = "placeup-api",
  [string]$AppService = "placeup-app",
  [string]$UserFirestoreProjectId = "placeup-firebase-641222668282",
  [string]$UserFirestoreDatabase = "(default)",
  [string]$Image = ""
)

$ErrorActionPreference = "Stop"

if (-not $Image) {
  $Image = & gcloud.cmd run services describe $WebService `
    --project $ProjectId --region $Region `
    --format "value(spec.template.spec.containers[0].image)"
  if (-not $Image) { throw "Could not resolve image from $WebService. Pass -Image." }
}

foreach ($secret in @("DATABASE_URL", "JWT_SECRET", "SERVICE_TOKEN_SECRET")) {
  & gcloud.cmd secrets describe $secret --project $ProjectId --format="value(name)" *> $null
  if ($LASTEXITCODE -ne 0) {
    throw "Missing required Secret Manager secret: $secret"
  }
}

$appEnv = "SERVER_ROLE=app,APP_ENV=production,DATABASE_BACKEND=postgres,USER_DATABASE_BACKEND=firestore,USER_FIRESTORE_PROJECT_ID=$UserFirestoreProjectId,USER_FIRESTORE_DATABASE=$UserFirestoreDatabase,APP_SERVER_IAM_AUTH=true"
$appSecrets = "DATABASE_URL=DATABASE_URL:latest,JWT_SECRET=JWT_SECRET:latest,SERVICE_TOKEN_SECRET=SERVICE_TOKEN_SECRET:latest"

Write-Host "Deploying internal application server $AppService from $Image"
& gcloud.cmd run deploy $AppService `
  --project $ProjectId `
  --region $Region `
  --image $Image `
  --service-account "placeup-api-sa@$ProjectId.iam.gserviceaccount.com" `
  --ingress internal `
  --no-allow-unauthenticated `
  --set-cloudsql-instances "$ProjectId`:$Region`:$DbInstance" `
  --set-env-vars $appEnv `
  --set-secrets $appSecrets `
  --memory 2Gi `
  --cpu 2 `
  --min-instances 0 `
  --max-instances 4 `
  --concurrency 40 `
  --timeout 900
if ($LASTEXITCODE -ne 0) { throw "$AppService deploy failed." }

$appUrl = & gcloud.cmd run services describe $AppService `
  --project $ProjectId --region $Region --format "value(status.url)"
if (-not $appUrl) { throw "Could not resolve $AppService URL." }

Write-Host "Granting $WebService service account invoke access to $AppService"
& gcloud.cmd run services add-iam-policy-binding $AppService `
  --project $ProjectId `
  --region $Region `
  --member "serviceAccount:placeup-api-sa@$ProjectId.iam.gserviceaccount.com" `
  --role "roles/run.invoker"
if ($LASTEXITCODE -ne 0) { throw "Could not grant run.invoker on $AppService." }

Write-Host "Pointing $WebService at internal app server URL"
& gcloud.cmd run services update $WebService `
  --project $ProjectId `
  --region $Region `
  --update-env-vars "APP_SERVER_URL=$appUrl,APP_SERVER_IAM_AUTH=true" `
  --update-secrets "SERVICE_TOKEN_SECRET=SERVICE_TOKEN_SECRET:latest"
if ($LASTEXITCODE -ne 0) { throw "Could not update $WebService with APP_SERVER_URL." }

Write-Host "Done. Internal app server URL: $appUrl"

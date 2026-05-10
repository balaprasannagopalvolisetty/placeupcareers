param(
  [Parameter(Mandatory=$true)][string]$ProjectId,
  [string]$Region = "us-central1",
  [string]$DbInstance = "placeup-postgres"
)

$ErrorActionPreference = "Stop"
$Image = "$Region-docker.pkg.dev/$ProjectId/placeup/backend:latest"

gcloud.cmd config set project $ProjectId
gcloud.cmd builds submit . --tag $Image

gcloud.cmd run deploy placeup-api `
  --image $Image `
  --region $Region `
  --service-account "placeup-api-sa@$ProjectId.iam.gserviceaccount.com" `
  --add-cloudsql-instances "$ProjectId`:$Region`:$DbInstance" `
  --set-env-vars "APP_ENV=production,DATABASE_BACKEND=postgres" `
  --set-secrets "DATABASE_URL=DATABASE_URL:latest,JWT_SECRET=JWT_SECRET:latest" `
  --allow-unauthenticated

gcloud.cmd run jobs deploy placeup-job-scraper-6h `
  --image $Image `
  --region $Region `
  --service-account "placeup-etl-sa@$ProjectId.iam.gserviceaccount.com" `
  --command python `
  --args "-m,app.etl.jobs_scraper,--schedule-type,6h" `
  --add-cloudsql-instances "$ProjectId`:$Region`:$DbInstance" `
  --set-env-vars "APP_ENV=production,DATABASE_BACKEND=postgres" `
  --set-secrets "DATABASE_URL=DATABASE_URL:latest"

gcloud.cmd run jobs deploy placeup-external-api-12h `
  --image $Image `
  --region $Region `
  --service-account "placeup-etl-sa@$ProjectId.iam.gserviceaccount.com" `
  --command python `
  --args "-m,app.etl.external_api_ingest,--schedule-type,12h" `
  --add-cloudsql-instances "$ProjectId`:$Region`:$DbInstance" `
  --set-env-vars "APP_ENV=production,DATABASE_BACKEND=postgres" `
  --set-secrets "DATABASE_URL=DATABASE_URL:latest"

Write-Host "Backend image, API, and ETL jobs deployed."

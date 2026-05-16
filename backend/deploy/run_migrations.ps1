param(
  [Parameter(Mandatory=$true)][string]$ProjectId,
  [string]$Region = "us-central1",
  [string]$DbInstance = "placeup-postgres"
)

$ErrorActionPreference = "Stop"
$Image = "$Region-docker.pkg.dev/$ProjectId/placeup/backend:latest"

gcloud.cmd run jobs deploy placeup-db-migrate `
  --image $Image `
  --region $Region `
  --service-account "placeup-etl-sa@$ProjectId.iam.gserviceaccount.com" `
  --command alembic `
  --args="upgrade,head" `
  --set-cloudsql-instances "$ProjectId`:$Region`:$DbInstance" `
  --set-env-vars "APP_ENV=production,DATABASE_BACKEND=postgres" `
  --set-secrets "DATABASE_URL=DATABASE_URL:latest"

gcloud.cmd run jobs execute placeup-db-migrate --region $Region --wait

param(
  [Parameter(Mandatory=$true)][string]$ProjectId,
  [string]$Region = "us-east1",
  [string]$DbInstance = "placeup-backend",
  [string]$DbName = "jobssilverdb",
  [string]$DbUser = "placeup",
  [string]$DbPassSecret = "SILVER_DB_PASS",
  [string]$FirestoreDatabase = "ra-jobs",
  [string]$FirestoreCollection = "jobs"
)

$ErrorActionPreference = "Stop"
$BackendRoot = Split-Path -Parent $PSScriptRoot
$SilverLoaderRoot = Join-Path $BackendRoot "cloudrun_silver_loader"

gcloud.cmd config set project $ProjectId

gcloud.cmd functions deploy clean-and-load-jobs `
  --gen2 `
  --runtime python312 `
  --region $Region `
  --source $SilverLoaderRoot `
  --entry-point clean_and_load_jobs `
  --trigger-http `
  --no-allow-unauthenticated `
  --service-account "placeup-etl-sa@$ProjectId.iam.gserviceaccount.com" `
  --set-env-vars "FIRESTORE_DATABASE=$FirestoreDatabase,FIRESTORE_COLLECTION=$FirestoreCollection,DB_NAME=$DbName,DB_USER=$DbUser,DB_HOST=/cloudsql/$ProjectId`:$Region`:$DbInstance" `
  --set-secrets "DB_PASS=$DbPassSecret`:latest" `
  --timeout 3600s `
  --memory 1Gi

gcloud.cmd run services update clean-and-load-jobs `
  --project $ProjectId `
  --region $Region `
  --set-cloudsql-instances "$ProjectId`:$Region`:$DbInstance"

Write-Host "Silver loader function deployed. Next: run .\deploy\schedule_silver_loader.ps1"

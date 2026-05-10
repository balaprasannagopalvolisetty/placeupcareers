param(
  [Parameter(Mandatory=$true)][string]$ProjectId,
  [string]$Region = "us-central1",
  [string]$DbInstance = "placeup-postgres",
  [string]$DbPassword = "CHANGE_ME_STRONG_PASSWORD"
)

$ErrorActionPreference = "Stop"

if ($DbPassword -eq "CHANGE_ME_STRONG_PASSWORD") {
  throw "Provide a real database password with -DbPassword before running production setup."
}

gcloud.cmd config set project $ProjectId

gcloud.cmd services enable `
  run.googleapis.com `
  cloudfunctions.googleapis.com `
  sqladmin.googleapis.com `
  firestore.googleapis.com `
  artifactregistry.googleapis.com `
  cloudbuild.googleapis.com `
  cloudscheduler.googleapis.com `
  secretmanager.googleapis.com `
  cloudtasks.googleapis.com `
  logging.googleapis.com `
  monitoring.googleapis.com

gcloud.cmd artifacts repositories create placeup `
  --repository-format=docker `
  --location=$Region `
  --description="PlaceUp backend containers" 2>$null

gcloud.cmd sql instances create $DbInstance `
  --database-version=POSTGRES_16 `
  --tier=db-f1-micro `
  --region=$Region `
  --storage-size=20GB 2>$null

gcloud.cmd sql databases create placeup --instance=$DbInstance 2>$null
gcloud.cmd sql users create placeup --instance=$DbInstance --password=$DbPassword 2>$null

$databaseUrl = "postgresql+psycopg://placeup:$DbPassword@/placeup?host=/cloudsql/$ProjectId`:$Region`:$DbInstance"
$databaseUrl | gcloud.cmd secrets create DATABASE_URL --data-file=- 2>$null
$jwtBytes = [System.Security.Cryptography.RandomNumberGenerator]::GetBytes(32)
$jwtSecret = [Convert]::ToHexString($jwtBytes).ToLowerInvariant()
$jwtSecret | gcloud.cmd secrets create JWT_SECRET --data-file=- 2>$null

gcloud.cmd iam service-accounts create placeup-api-sa --display-name="PlaceUp API" 2>$null
gcloud.cmd iam service-accounts create placeup-etl-sa --display-name="PlaceUp ETL Jobs" 2>$null
gcloud.cmd iam service-accounts create placeup-scheduler-sa --display-name="PlaceUp Scheduler" 2>$null

foreach ($sa in @("placeup-api-sa", "placeup-etl-sa")) {
  gcloud.cmd projects add-iam-policy-binding $ProjectId `
    --member="serviceAccount:$sa@$ProjectId.iam.gserviceaccount.com" `
    --role="roles/cloudsql.client"
  gcloud.cmd projects add-iam-policy-binding $ProjectId `
    --member="serviceAccount:$sa@$ProjectId.iam.gserviceaccount.com" `
    --role="roles/secretmanager.secretAccessor"
}

gcloud.cmd projects add-iam-policy-binding $ProjectId `
  --member="serviceAccount:placeup-etl-sa@$ProjectId.iam.gserviceaccount.com" `
  --role="roles/datastore.user"

gcloud.cmd projects add-iam-policy-binding $ProjectId `
  --member="serviceAccount:placeup-scheduler-sa@$ProjectId.iam.gserviceaccount.com" `
  --role="roles/run.developer"
gcloud.cmd projects add-iam-policy-binding $ProjectId `
  --member="serviceAccount:placeup-scheduler-sa@$ProjectId.iam.gserviceaccount.com" `
  --role="roles/run.invoker"

Write-Host "GCP foundation created. Next: build image, run Alembic migration, deploy API/jobs."

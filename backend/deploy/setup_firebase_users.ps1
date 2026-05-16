param(
  [Parameter(Mandatory=$true)][string]$ProjectId,
  [string]$BackendProjectId = $ProjectId,
  [string]$Region = "us-east1",
  [string]$FirestoreDatabase = "(default)",
  [string]$FirestoreLocation = "nam5",
  [string]$ApiServiceAccount = "placeup-api-sa"
)

$ErrorActionPreference = "Stop"

gcloud.cmd config set project $ProjectId

gcloud.cmd services enable `
  firebase.googleapis.com `
  firebaserules.googleapis.com `
  firestore.googleapis.com `
  firebasehosting.googleapis.com `
  run.googleapis.com

$existingDbs = gcloud.cmd firestore databases list --project $ProjectId --format="value(name.basename())"
if ($existingDbs -notcontains $FirestoreDatabase) {
  gcloud.cmd firestore databases create `
    --project $ProjectId `
    --database $FirestoreDatabase `
    --location $FirestoreLocation `
    --type firestore-native
}

$apiSaEmail = "$ApiServiceAccount@$BackendProjectId.iam.gserviceaccount.com"
gcloud.cmd projects add-iam-policy-binding $ProjectId `
  --member "serviceAccount:$apiSaEmail" `
  --role "roles/datastore.user"

Write-Host "Firebase/Firestore user database is ready."
Write-Host "Firebase/User project: $ProjectId"
Write-Host "Firestore database: $FirestoreDatabase"
Write-Host "Backend project: $BackendProjectId"
Write-Host "API service account granted roles/datastore.user: $apiSaEmail"

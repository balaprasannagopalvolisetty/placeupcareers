param(
  [Parameter(Mandatory=$true)][string]$ProjectId,
  [string]$ApiBase = "https://placeup-api-641222668282.us-east1.run.app",
  [switch]$AllowRelativeApi
)

$ErrorActionPreference = "Stop"

if ($ApiBase) {
  $env:VITE_API_BASE = $ApiBase
} else {
  if (-not $AllowRelativeApi) {
    throw "Pass -ApiBase with the backend URL for Firebase Hosting, or use -AllowRelativeApi only when the hosting target already routes /api to Cloud Run."
  }
  $env:VITE_API_BASE = ""
}

npm run build
npx --yes firebase-tools deploy --only hosting --project $ProjectId

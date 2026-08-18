param([switch]$DeleteData)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root
$EnvFile = Join-Path $Root ".env.local"
if (-not (Test-Path $EnvFile)) { $EnvFile = Join-Path $Root ".env.local.example" }

$arguments = @("compose", "--env-file", $EnvFile, "--profile", "workers", "--profile", "ai", "--profile", "ats", "down", "--remove-orphans")
if ($DeleteData) { $arguments += "--volumes" }
& docker @arguments
if ($LASTEXITCODE -ne 0) { throw "Could not stop the local PlaceUp stack." }
if ($DeleteData) {
  Write-Host "Stopped PlaceUp and deleted local database, emulator, documents, and model volumes." -ForegroundColor Yellow
} else {
  Write-Host "Stopped PlaceUp. Local data volumes were preserved." -ForegroundColor Green
}

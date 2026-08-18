$ErrorActionPreference = "Continue"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root
$EnvFile = Join-Path $Root ".env.local"
if (-not (Test-Path $EnvFile)) { $EnvFile = Join-Path $Root ".env.local.example" }

& docker compose --env-file $EnvFile --profile workers --profile ai --profile ats ps

foreach ($check in @(
  @{ Name = "Frontend"; Uri = "http://localhost:3000/healthz" },
  @{ Name = "API"; Uri = "http://localhost:8000/api/health" },
  @{ Name = "OpenClaw"; Uri = "http://localhost:8090/healthz" },
  @{ Name = "ATS model"; Uri = "http://localhost:8091/healthz" }
)) {
  try {
    $r = Invoke-WebRequest -UseBasicParsing -Uri $check.Uri -TimeoutSec 4
    Write-Host ("{0,-12} healthy ({1})" -f $check.Name, $r.StatusCode) -ForegroundColor Green
  } catch {
    Write-Host ("{0,-12} not running or still starting" -f $check.Name) -ForegroundColor DarkYellow
  }
}

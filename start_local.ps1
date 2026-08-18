param(
  [switch]$Full,
  [switch]$WithWorkers,
  [switch]$WithAI,
  [switch]$WithAtsModel,
  [switch]$NoBuild
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
  throw @"
Docker Desktop is required for PlaceUp's isolated local PostgreSQL, Firestore,
Redis, Ollama, and application services, but 'docker' is not installed.
Install Docker Desktop, enable WSL 2, start it, and rerun this script.
Official download: https://www.docker.com/products/docker-desktop/
"@
}
& docker info *> $null
if ($LASTEXITCODE -ne 0) {
  throw "Docker Desktop is installed but its engine is not running. Start Docker Desktop and rerun."
}

$EnvFile = Join-Path $Root ".env.local"
$Example = Join-Path $Root ".env.local.example"
if (-not (Test-Path $EnvFile)) {
  $content = Get-Content -Raw -LiteralPath $Example
  function New-HexSecret {
    $bytes = New-Object byte[] 32
    $generator = [Security.Cryptography.RandomNumberGenerator]::Create()
    try {
      $generator.GetBytes($bytes)
    } finally {
      $generator.Dispose()
    }
    return (($bytes | ForEach-Object { $_.ToString("x2") }) -join "")
  }
  foreach ($key in @("JWT_SECRET", "INTERNAL_API_KEY", "SERVICE_TOKEN_SECRET", "OPENCLAW_TAILOR_TOKEN", "ATS_MODEL_SERVICE_TOKEN")) {
    $content = $content.Replace("$key=__GENERATE__", "$key=$(New-HexSecret)")
  }
  [IO.File]::WriteAllText($EnvFile, $content, [Text.UTF8Encoding]::new($false))
  Write-Host "Created private local configuration: $EnvFile" -ForegroundColor Green
}

if ($Full) {
  $WithWorkers = $true
  $WithAI = $true
  $WithAtsModel = $true
}

$profiles = @()
if ($WithWorkers) { $profiles += @("--profile", "workers") }
if ($WithAI) {
  $profiles += @("--profile", "ai")
  $env:LOCAL_AI_ENABLED = "true"
} else {
  $env:LOCAL_AI_ENABLED = "false"
}
if ($WithAtsModel) {
  $profiles += @("--profile", "ats")
  $env:LOCAL_ATS_ANALYSIS_ENABLED = "true"
} else {
  $env:LOCAL_ATS_ANALYSIS_ENABLED = "false"
}

$arguments = @("compose", "--env-file", $EnvFile) + $profiles + @("up", "-d")
if (-not $NoBuild) { $arguments += "--build" }
Write-Host "Starting PlaceUp locally..." -ForegroundColor Cyan
& docker @arguments
if ($LASTEXITCODE -ne 0) { throw "Local PlaceUp startup failed." }

$ready = $false
for ($attempt = 1; $attempt -le 60; $attempt++) {
  try {
    $response = Invoke-WebRequest -UseBasicParsing -Uri "http://localhost:3000/healthz" -TimeoutSec 3
    if ($response.StatusCode -eq 200) { $ready = $true; break }
  } catch { }
  Start-Sleep -Seconds 2
}
if (-not $ready) {
  & docker compose --env-file $EnvFile ps
  throw "Containers started, but the frontend did not become healthy within two minutes. Run .\local_status.ps1."
}

Write-Host "" 
Write-Host "PlaceUp is running locally." -ForegroundColor Green
Write-Host "  Website:           http://localhost:3000"
Write-Host "  Backend API/docs:  http://localhost:8000/docs"
Write-Host "  Firestore emulator:127.0.0.1:8085"
Write-Host "  PostgreSQL:        127.0.0.1:5432"
if ($WithAI) { Write-Host "  OpenClaw health:   http://localhost:8090/healthz" }
if ($WithAtsModel) { Write-Host "  ATS model health:  http://localhost:8091/healthz (first model load occurs on analysis)" }
if (-not $Full) {
  Write-Host "Run '.\start_local.ps1 -Full' when you want workers + both local AI profiles." -ForegroundColor Yellow
}

param(
  [Parameter(Mandatory = $true)]
  [ValidateSet("job-scraper-am", "job-scraper-pm", "daily-match-digest", "jd-repair", "company-link-resolver", "board-discovery", "job-liveness", "stale-jobs", "job-retention", "ats-worker", "taxonomy-report", "master-ats-analysis")]
  [string]$Name
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root
$EnvFile = Join-Path $Root ".env.local"
if (-not (Test-Path $EnvFile)) { throw "Run .\start_local.ps1 first so .env.local is created." }

& docker compose --env-file $EnvFile --profile workers run --rm scheduler python -m app.workers.local_scheduler --run $Name
if ($LASTEXITCODE -ne 0) { throw "Local job '$Name' failed." }

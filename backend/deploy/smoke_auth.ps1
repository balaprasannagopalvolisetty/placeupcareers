param(
  [string]$ApiBase = "https://placeup-api-641222668282.us-east1.run.app",
  [string]$Origin = "https://placeupcareer.com"
)

# Post-deploy auth smoke test.
# Verifies the sign-in/sign-up surface is actually serving after a deploy:
#   1. /api/health                 -> 200 (service up)
#   2. /api/auth/session           -> 200 (public auth read path + middleware OK)
#   3. /api/auth/oidc/providers    -> 200 (Google sign-in config intact)
#   4. /api/auth/signin bad creds  -> 401 (auth route + user store + JWT stack
#                                     work end-to-end; a 5xx here means broken)
# Exits non-zero on any failure so deploy pipelines stop loudly instead of
# shipping a build with dead sign-in.

$ErrorActionPreference = "Stop"
$failures = @()

function Test-Endpoint {
  param(
    [string]$Name,
    [string]$Method,
    [string]$Url,
    [int[]]$ExpectStatus,
    [string]$Body = $null
  )
  $status = $null
  try {
    $params = @{
      Method          = $Method
      Uri             = $Url
      TimeoutSec      = 20
      UseBasicParsing = $true
      Headers         = @{ "Origin" = $script:Origin }
    }
    if ($Body) {
      $params.Body = $Body
      $params.ContentType = "application/json"
    }
    # PowerShell 7 supports -SkipHttpErrorCheck; 5.1 throws on 4xx/5xx instead.
    if ($PSVersionTable.PSVersion.Major -ge 7) { $params.SkipHttpErrorCheck = $true }
    $resp = Invoke-WebRequest @params
    $status = [int]$resp.StatusCode
  } catch {
    # Windows PowerShell 5.1 path: extract the status from the error response.
    $errResp = $_.Exception.Response
    if ($errResp -and $errResp.StatusCode) {
      $status = [int]$errResp.StatusCode
    } else {
      $script:failures += "${Name}: request failed entirely ($($_.Exception.Message))"
      Write-Host "  FAIL  $Name -> no response" -ForegroundColor Red
      return
    }
  }
  if ($ExpectStatus -contains $status) {
    Write-Host "  OK    $Name -> $status" -ForegroundColor Green
  } else {
    $script:failures += "${Name}: expected $($ExpectStatus -join '/'), got $status"
    Write-Host "  FAIL  $Name -> $status (expected $($ExpectStatus -join '/'))" -ForegroundColor Red
  }
}

Write-Host "Auth smoke test against $ApiBase" -ForegroundColor Cyan

Test-Endpoint -Name "health"          -Method GET  -Url "$ApiBase/api/health"               -ExpectStatus 200
Test-Endpoint -Name "auth session"    -Method GET  -Url "$ApiBase/api/auth/session"         -ExpectStatus 200
Test-Endpoint -Name "oidc providers"  -Method GET  -Url "$ApiBase/api/auth/oidc/providers"  -ExpectStatus 200
Test-Endpoint -Name "signin route"    -Method POST -Url "$ApiBase/api/auth/signin" `
  -Body '{"identifier":"smoke-test@placeupcareer.com","password":"definitely-wrong-password"}' `
  -ExpectStatus @(400, 401, 403, 422, 429)

if ($failures.Count -gt 0) {
  Write-Host ""
  Write-Host "AUTH SMOKE TEST FAILED:" -ForegroundColor Red
  $failures | ForEach-Object { Write-Host "  - $_" -ForegroundColor Red }
  Write-Host "Sign-in/sign-up is likely broken on this deploy. Check Cloud Run logs:" -ForegroundColor Yellow
  Write-Host "  gcloud run services logs read placeup-api --region us-east1 --limit 50"
  exit 1
}

Write-Host ""
Write-Host "All auth smoke checks passed - sign-in/sign-up surface is healthy." -ForegroundColor Green
exit 0

param(
    [Parameter(Mandatory = $true)][string]$ProjectId,
    [string]$ApiRegion = "us-east1",
    [string]$GpuRegion = "us-east4",
    [string]$DbInstance = "placeup-backend",
    [string]$BackendImage = "",
    [string]$ServiceTokenSecret = "ats-model-service-token",
    [string]$BaseModel = "mistralai/Mistral-7B-Instruct-v0.2",
    [string]$AdapterModel = "SlyGoblin/mistral_ATSscore_generation",
    [string]$ModelVersion = "mistral-ats-v1",
    [switch]$CreateSchedule
)

$ErrorActionPreference = "Stop"
$Service = "placeup-ats-model"
$WorkerJob = "placeup-master-ats-analysis"
$ModelImage = "$GpuRegion-docker.pkg.dev/$ProjectId/placeup/ats-model:latest"
if (-not $BackendImage) {
    $BackendImage = "$ApiRegion-docker.pkg.dev/$ProjectId/placeup/backend:latest"
}
$Root = Resolve-Path (Join-Path $PSScriptRoot "..\ats_model_service")
$ModelSa = "placeup-ats-model-sa@$ProjectId.iam.gserviceaccount.com"
$EtlSa = "placeup-etl-sa@$ProjectId.iam.gserviceaccount.com"

gcloud.cmd services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com secretmanager.googleapis.com --project $ProjectId

$RepoNames = @(gcloud.cmd artifacts repositories list --project $ProjectId --location $GpuRegion --format "value(name)")
if ($RepoNames -notcontains "placeup") {
    gcloud.cmd artifacts repositories create placeup --project $ProjectId --location $GpuRegion `
        --repository-format docker --description "PlaceUp private model images"
}

$ExistingModelSa = gcloud.cmd iam service-accounts list --project $ProjectId --filter "email=$ModelSa" --format "value(email)"
if (-not $ExistingModelSa) {
    gcloud.cmd iam service-accounts create placeup-ats-model-sa --project $ProjectId --display-name "PlaceUp private ATS GPU model"
}

$SecretNames = @(gcloud.cmd secrets list --project $ProjectId --format "value(name)")
if ($SecretNames -notcontains $ServiceTokenSecret) {
    gcloud.cmd secrets create $ServiceTokenSecret --project $ProjectId --replication-policy automatic | Out-Null
}
$ExistingVersion = gcloud.cmd secrets versions list $ServiceTokenSecret --project $ProjectId `
    --limit 1 --format "value(name)"
if (-not $ExistingVersion) {
    $bytes = New-Object byte[] 48
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try { $rng.GetBytes($bytes) } finally { $rng.Dispose() }
    $token = [Convert]::ToBase64String($bytes)
    $tokenFile = [IO.Path]::GetTempFileName()
    try {
        [IO.File]::WriteAllText($tokenFile, $token)
        gcloud.cmd secrets versions add $ServiceTokenSecret --project $ProjectId --data-file=$tokenFile | Out-Null
    } finally {
        Remove-Item -LiteralPath $tokenFile -Force -ErrorAction SilentlyContinue
    }
    $token = $null
}

foreach ($Member in @($ModelSa, $EtlSa)) {
    gcloud.cmd secrets add-iam-policy-binding $ServiceTokenSecret --project $ProjectId `
        --member "serviceAccount:$Member" --role roles/secretmanager.secretAccessor | Out-Null
}

gcloud.cmd builds submit $Root --tag $ModelImage --project $ProjectId --timeout 3600s --machine-type e2-highcpu-8
if ($LASTEXITCODE -ne 0) { throw "ATS model image build failed." }

# The service is internet-routable only so Cloud Run IAM identity tokens work
# across regions. It has no unauthenticated invoker and also requires the
# PlaceUp service token at the application layer.
gcloud.cmd run deploy $Service `
    --image $ModelImage `
    --project $ProjectId `
    --region $GpuRegion `
    --service-account $ModelSa `
    --no-allow-unauthenticated `
    --ingress all `
    --gpu 1 `
    --gpu-type nvidia-l4 `
    --no-gpu-zonal-redundancy `
    --cpu 8 `
    --memory 32Gi `
    --concurrency 1 `
    --min-instances 0 `
    --max-instances 1 `
    --timeout 900 `
    --set-env-vars "ATS_BASE_MODEL=$BaseModel,ATS_ADAPTER_MODEL=$AdapterModel,ATS_MODEL_VERSION=$ModelVersion,ATS_MAX_INPUT_CHARS=24000,ATS_LOAD_IN_4BIT=true" `
    --set-secrets "PLACEUP_SERVICE_TOKEN=$ServiceTokenSecret`:latest"
if ($LASTEXITCODE -ne 0) { throw "ATS model Cloud Run deployment failed." }

gcloud.cmd run services add-iam-policy-binding $Service --project $ProjectId --region $GpuRegion `
    --member "serviceAccount:$EtlSa" --role roles/run.invoker | Out-Null
$ModelUrl = gcloud.cmd run services describe $Service --project $ProjectId --region $GpuRegion --format "value(status.url)"
if (-not $ModelUrl) { throw "ATS model service has no ready URL." }

gcloud.cmd run jobs deploy $WorkerJob `
    --image $BackendImage `
    --project $ProjectId `
    --region $ApiRegion `
    --service-account $EtlSa `
    --command python `
    --args="-m,app.workers.master_ats_analysis,--batch-size,10,--max-jobs,0,--max-runtime-seconds,82800" `
    --set-cloudsql-instances "$ProjectId`:$ApiRegion`:$DbInstance" `
    --set-env-vars "APP_ENV=production,DATABASE_BACKEND=postgres,DB_POOL_SIZE=1,DB_MAX_OVERFLOW=0,DB_STATEMENT_TIMEOUT_MS=0,ATS_MODEL_URL=$ModelUrl,ATS_MODEL_VERSION=$ModelVersion,ATS_ANALYSIS_MIN_JD_CHARS=500" `
    --set-secrets "DATABASE_URL=DATABASE_URL:latest,ATS_MODEL_SERVICE_TOKEN=$ServiceTokenSecret`:latest" `
    --memory 1Gi `
    --cpu 1 `
    --max-retries 0 `
    --task-timeout 86400s
if ($LASTEXITCODE -ne 0) { throw "Master ATS analysis job deployment failed." }
gcloud.cmd run jobs add-iam-policy-binding $WorkerJob --project $ProjectId --region $ApiRegion `
    --member "serviceAccount:$EtlSa" --role roles/run.invoker | Out-Null

if ($CreateSchedule) {
    $Uri = "https://$ApiRegion-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/$ProjectId/jobs/$WorkerJob`:run"
    $Existing = gcloud.cmd scheduler jobs describe placeup-master-ats-analysis-daily --project $ProjectId --location $ApiRegion --format "value(name)" 2>$null
    if ($Existing) {
        gcloud.cmd scheduler jobs update http placeup-master-ats-analysis-daily --project $ProjectId --location $ApiRegion `
            --schedule "30 0 * * *" --time-zone "America/Chicago" --uri $Uri --http-method POST `
            --oauth-service-account-email $EtlSa
    } else {
        gcloud.cmd scheduler jobs create http placeup-master-ats-analysis-daily --project $ProjectId --location $ApiRegion `
            --schedule "30 0 * * *" --time-zone "America/Chicago" --uri $Uri --http-method POST `
            --oauth-service-account-email $EtlSa
    }
}

Write-Host "Private ATS GPU model deployed: $ModelUrl"
Write-Host "Resumable master analysis job deployed: $WorkerJob"

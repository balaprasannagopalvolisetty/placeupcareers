param(
    [Parameter(Mandatory = $true)][string]$ProjectId,
    [string]$Zone = "us-central1-a",
    [string]$ApiRegion = "us-east1",
    [string]$GpuRegion = "us-east4",
    [string]$DbInstance = "placeup-backend",
    [string]$InstanceName = "placeup-ats-batch",
    [string]$GpuType = "nvidia-tesla-p4",
    [string]$MachineType = "n1-standard-4",
    [ValidateSet("STANDARD", "SPOT")][string]$ProvisioningModel = "SPOT",
    [switch]$CreateSchedule
)

$ErrorActionPreference = "Stop"
$Network = "placeup-model"
$ComputeRegion = $Zone -replace '-[a-z]$', ''
$Subnet = "placeup-model-$ComputeRegion"
$SubnetCidr = if ($ComputeRegion -eq "us-central1") { "10.42.0.0/24" } else { "10.43.0.0/24" }
$ServiceAccount = "placeup-ats-model-sa@$ProjectId.iam.gserviceaccount.com"
$SchedulerRole = "placeupAtsVmRunner"
$BackendImage = "$ApiRegion-docker.pkg.dev/$ProjectId/placeup/backend:latest"
$ModelImage = "$GpuRegion-docker.pkg.dev/$ProjectId/placeup/ats-model:latest"
$StartupScript = Resolve-Path (Join-Path $PSScriptRoot "start_ats_batch_vm.sh")

gcloud.cmd services enable compute.googleapis.com secretmanager.googleapis.com artifactregistry.googleapis.com cloudscheduler.googleapis.com --project $ProjectId

$Networks = @(gcloud.cmd compute networks list --project $ProjectId --format "value(name)")
if ($Networks -notcontains $Network) {
    gcloud.cmd compute networks create $Network --project $ProjectId --subnet-mode custom
}
$Subnets = @(gcloud.cmd compute networks subnets list --project $ProjectId --regions $ComputeRegion --format "value(name)")
if ($Subnets -notcontains $Subnet) {
    gcloud.cmd compute networks subnets create $Subnet --project $ProjectId --network $Network `
        --region $ComputeRegion --range $SubnetCidr --enable-private-ip-google-access
}

foreach ($Role in @("roles/artifactregistry.reader", "roles/cloudsql.client", "roles/secretmanager.secretAccessor", "roles/logging.logWriter")) {
    gcloud.cmd projects add-iam-policy-binding $ProjectId --member "serviceAccount:$ServiceAccount" --role $Role | Out-Null
}

$ProjectRoles = @(gcloud.cmd iam roles list --project $ProjectId --format "value(name.basename())")
if ($ProjectRoles -notcontains $SchedulerRole) {
    gcloud.cmd iam roles create $SchedulerRole --project $ProjectId --title "PlaceUp ATS VM Runner" `
        --description "Start, stop, and inspect only the scheduled ATS batch VM workflow" `
        --permissions "compute.instances.get,compute.instances.start,compute.instances.stop"
} else {
    gcloud.cmd iam roles update $SchedulerRole --project $ProjectId `
        --permissions "compute.instances.get,compute.instances.start,compute.instances.stop"
}
gcloud.cmd projects add-iam-policy-binding $ProjectId --member "serviceAccount:$ServiceAccount" `
    --role "projects/$ProjectId/roles/$SchedulerRole" | Out-Null

$InstanceRows = @(gcloud.cmd compute instances list --project $ProjectId --format "csv[no-heading](name,zone.basename())")
$InstanceExists = $InstanceRows -contains "$InstanceName,$Zone"
if ($InstanceExists) {
    gcloud.cmd compute instances delete $InstanceName --project $ProjectId --zone $Zone --quiet
}

# This dedicated custom VPC intentionally has no ingress firewall rules. The VM
# receives an ephemeral egress address only for Hugging Face/Artifact Registry
# downloads; neither the model nor PostgreSQL proxy publishes a host port.
gcloud.cmd compute instances create $InstanceName `
    --project $ProjectId `
    --zone $Zone `
    --machine-type $MachineType `
    --accelerator type=$GpuType,count=1 `
    --maintenance-policy TERMINATE `
    --provisioning-model $ProvisioningModel `
    --image-family cos-121-lts `
    --image-project cos-cloud `
    --boot-disk-size 100GB `
    --boot-disk-type pd-balanced `
    --network $Network `
    --subnet $Subnet `
    --service-account $ServiceAccount `
    --scopes cloud-platform `
    --metadata-from-file "startup-script=$StartupScript" `
    --metadata "PROJECT_ID=$ProjectId,API_REGION=$ApiRegion,GPU_REGION=$GpuRegion,DB_INSTANCE=$DbInstance,MODEL_IMAGE=$ModelImage,BACKEND_IMAGE=$BackendImage"
if ($LASTEXITCODE -ne 0) { throw "ATS batch VM creation failed." }

if ($CreateSchedule) {
    $Uri = "https://compute.googleapis.com/compute/v1/projects/$ProjectId/zones/$Zone/instances/$InstanceName/start"
    $Jobs = @(gcloud.cmd scheduler jobs list --project $ProjectId --location us-central1 --format "value(name.basename())")
    if ($Jobs -contains "placeup-ats-batch-daily") {
        gcloud.cmd scheduler jobs update http placeup-ats-batch-daily --project $ProjectId --location us-central1 `
            --schedule "30 0 * * *" --time-zone "America/Chicago" --uri $Uri --http-method POST `
            --oauth-service-account-email $ServiceAccount --oauth-token-scope https://www.googleapis.com/auth/cloud-platform
    } else {
        gcloud.cmd scheduler jobs create http placeup-ats-batch-daily --project $ProjectId --location us-central1 `
            --schedule "30 0 * * *" --time-zone "America/Chicago" --uri $Uri --http-method POST `
            --oauth-service-account-email $ServiceAccount --oauth-token-scope https://www.googleapis.com/auth/cloud-platform
    }
}

Write-Host "ATS GPU batch VM created and started: $InstanceName ($Zone, $GpuType)"
Write-Host "It has no inbound firewall rule and will stop itself after the resumable analysis window."

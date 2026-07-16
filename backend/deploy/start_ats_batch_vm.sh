#!/bin/bash
set -euo pipefail

exec > >(tee /dev/console | logger -t placeup-ats-batch) 2>&1

meta() {
  curl -fsS -H 'Metadata-Flavor: Google' "http://metadata.google.internal/computeMetadata/v1/$1"
}

PROJECT_ID="$(meta instance/attributes/PROJECT_ID)"
API_REGION="$(meta instance/attributes/API_REGION)"
GPU_REGION="$(meta instance/attributes/GPU_REGION)"
DB_INSTANCE="$(meta instance/attributes/DB_INSTANCE)"
MODEL_IMAGE="$(meta instance/attributes/MODEL_IMAGE)"
BACKEND_IMAGE="$(meta instance/attributes/BACKEND_IMAGE)"
INSTANCE_NAME="$(meta instance/name)"
ZONE="$(meta instance/zone | awk -F/ '{print $NF}')"

stop_vm() {
  echo "Stopping the ATS batch VM"
  local token
  token="$(access_token 2>/dev/null || true)"
  if [ -n "$token" ]; then
    curl -fsS -X POST -H "Authorization: Bearer ${token}" \
      "https://compute.googleapis.com/compute/v1/projects/${PROJECT_ID}/zones/${ZONE}/instances/${INSTANCE_NAME}/stop" || true
  fi
  shutdown -h now 2>/dev/null || true
}

access_token() {
  meta instance/service-accounts/default/token | sed -n 's/.*"access_token":"\([^"]*\)".*/\1/p'
}

# Never leave a GPU VM billing after an image, driver, model, database, or
# worker failure. The worker commits each row, so stopping is always resumable.
trap stop_vm EXIT

secret() {
  local name="$1" token payload
  token="$(access_token)"
  payload="$(curl -fsS -H "Authorization: Bearer ${token}" \
    "https://secretmanager.googleapis.com/v1/projects/${PROJECT_ID}/secrets/${name}/versions/latest:access")"
  echo "$payload" | sed -n 's/.*"data": *"\([^"]*\)".*/\1/p' | tr '_-' '/+' | base64 -d
}

echo "Installing the signed COS NVIDIA driver"
cos-extensions install gpu -- -version=latest
mount --bind /var/lib/nvidia /var/lib/nvidia
mount -o remount,exec /var/lib/nvidia
/var/lib/nvidia/bin/nvidia-smi

TOKEN="$(access_token)"
for registry in "${GPU_REGION}-docker.pkg.dev" "${API_REGION}-docker.pkg.dev"; do
  echo "$TOKEN" | docker login -u oauth2accesstoken --password-stdin "https://${registry}"
done

docker pull "$MODEL_IMAGE"
docker pull "$BACKEND_IMAGE"
docker pull gcr.io/cloud-sql-connectors/cloud-sql-proxy:2.18.2

docker rm -f placeup-ats-worker placeup-ats-model placeup-cloudsql 2>/dev/null || true
docker network rm placeup-ats 2>/dev/null || true
docker network create placeup-ats

mkdir -p /var/lib/placeup-model-cache
chmod 0777 /var/lib/placeup-model-cache

SERVICE_TOKEN="$(secret ats-model-service-token)"
ORIGINAL_DATABASE_URL="$(secret DATABASE_URL)"
DATABASE_BASE="${ORIGINAL_DATABASE_URL%%\?host=*}"
DATABASE_URL="${DATABASE_BASE/@\//@placeup-cloudsql:5432/}"

docker run -d --name placeup-cloudsql --network placeup-ats \
  gcr.io/cloud-sql-connectors/cloud-sql-proxy:2.18.2 \
  --address 0.0.0.0 --port 5432 "${PROJECT_ID}:${API_REGION}:${DB_INSTANCE}"

docker run -d --name placeup-ats-model --network placeup-ats --shm-size 2g \
  --volume /var/lib/placeup-model-cache:/models \
  --volume /var/lib/nvidia/lib64:/usr/local/nvidia/lib64:ro \
  --volume /var/lib/nvidia/bin:/usr/local/nvidia/bin:ro \
  --device /dev/nvidia0:/dev/nvidia0 \
  --device /dev/nvidia-uvm:/dev/nvidia-uvm \
  --device /dev/nvidiactl:/dev/nvidiactl \
  --env LD_LIBRARY_PATH=/usr/local/nvidia/lib64 \
  --env PLACEUP_SERVICE_TOKEN="$SERVICE_TOKEN" \
  --env ATS_BASE_MODEL=mistralai/Mistral-7B-Instruct-v0.2 \
  --env ATS_ADAPTER_MODEL=SlyGoblin/mistral_ATSscore_generation \
  --env ATS_MODEL_VERSION=mistral-ats-v1 \
  --env ATS_LOAD_IN_4BIT=true \
  --env ATS_LOAD_IN_8BIT=false \
  "$MODEL_IMAGE"

echo "Waiting for the private model process"
MODEL_READY=0
for attempt in $(seq 1 120); do
  if docker exec placeup-ats-model python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/healthz', timeout=2)" 2>/dev/null; then
    MODEL_READY=1
    break
  fi
  sleep 2
done
if [ "$MODEL_READY" -ne 1 ]; then
  echo "Private model process did not become healthy"
  docker logs --tail 100 placeup-ats-model || true
  exit 1
fi

set +e
docker run --name placeup-ats-worker --network placeup-ats \
  --env APP_ENV=production \
  --env DATABASE_BACKEND=postgres \
  --env DATABASE_URL="$DATABASE_URL" \
  --env DB_POOL_SIZE=1 \
  --env DB_MAX_OVERFLOW=0 \
  --env DB_STATEMENT_TIMEOUT_MS=0 \
  --env ATS_MODEL_URL=http://placeup-ats-model:8080 \
  --env ATS_MODEL_SERVICE_TOKEN="$SERVICE_TOKEN" \
  --env ATS_MODEL_VERSION=mistral-ats-v1 \
  --env ATS_ANALYSIS_MIN_JD_CHARS=500 \
  "$BACKEND_IMAGE" \
  python -m app.workers.master_ats_analysis --batch-size 10 --max-jobs 0 --max-runtime-seconds 82800
WORKER_EXIT=$?
set -e

echo "ATS worker exited with code ${WORKER_EXIT}; stopping the GPU VM"
exit "$WORKER_EXIT"

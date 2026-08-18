#!/usr/bin/env bash
# =============================================================================
# PlaceUp — single-entrypoint local runtime controller (Linux / Ubuntu / WSL2)
#
# This is the implementation behind the Makefile. Everything the stack needs to
# come up — preflight checks, secret generation, image builds, migrations,
# seeding, health gating and smoke verification — happens here, so that
#
#     make up
#
# is genuinely the only command a developer has to run to get the complete
# PlaceUp application (frontend + backend + datastores) serving on this host.
#
# Design notes (see docs/freehire-analysis.md, "Operations & DX"):
#   * Fail loudly and early. A missing prerequisite is reported with the exact
#     command that fixes it, never as a stack trace 90 seconds into a build.
#   * Never leave the operator guessing. `up` does not return success until it
#     has proven, over HTTP, that the frontend can reach the backend.
#   * Idempotent. Re-running any subcommand on a healthy stack is a no-op.
#   * Data is precious. Only `reset` destroys volumes, and it demands
#     confirmation.
# =============================================================================

set -Eeuo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

ENV_FILE="$ROOT_DIR/.env.local"
ENV_EXAMPLE="$ROOT_DIR/.env.local.example"
COMPOSE_FILE="$ROOT_DIR/compose.yaml"
COMPOSE_LINUX_OVERLAY="$ROOT_DIR/compose.linux.yaml"

# Host ports published by compose.yaml. Kept here so preflight and the printed
# summary cannot drift from what is actually bound.
PORT_FRONTEND=3000
PORT_API=8000
PORT_POSTGRES=5432
PORT_FIRESTORE=8085
PORT_REDIS=6379
PORT_OLLAMA=11434
PORT_OPENCLAW=8090
PORT_ATS=8091

READY_TIMEOUT_SECONDS="${PLACEUP_READY_TIMEOUT:-900}"

# ----------------------------------------------------------------------------
# Output helpers
# ----------------------------------------------------------------------------
if [[ -t 1 && -z "${NO_COLOR:-}" ]]; then
  C_RESET=$'\033[0m'; C_RED=$'\033[31m'; C_GREEN=$'\033[32m'
  C_YELLOW=$'\033[33m'; C_BLUE=$'\033[36m'; C_BOLD=$'\033[1m'; C_DIM=$'\033[2m'
else
  C_RESET=''; C_RED=''; C_GREEN=''; C_YELLOW=''; C_BLUE=''; C_BOLD=''; C_DIM=''
fi

info()  { printf '%s==>%s %s\n' "$C_BLUE" "$C_RESET" "$*"; }
ok()    { printf '%s  ok%s   %s\n' "$C_GREEN" "$C_RESET" "$*"; }
warn()  { printf '%s  warn%s %s\n' "$C_YELLOW" "$C_RESET" "$*"; }
fail()  { printf '%s  FAIL%s %s\n' "$C_RED" "$C_RESET" "$*" >&2; }
step()  { printf '\n%s%s%s\n' "$C_BOLD" "$*" "$C_RESET"; }
dim()   { printf '%s%s%s\n' "$C_DIM" "$*" "$C_RESET"; }

die() { fail "$*"; exit 1; }

on_error() {
  local exit_code=$?
  local line=${1:-?}
  # 141 = SIGPIPE, e.g. `placeup.sh urls | head`. Not a failure worth reporting.
  (( exit_code == 141 )) && exit 0
  fail "aborted at ${BASH_SOURCE[0]}:${line} (exit ${exit_code})"
  printf '\nTroubleshooting:\n'
  printf '  make status      # per-service state and health probes\n'
  printf '  make logs        # follow every container log\n'
  printf '  make doctor      # re-run host prerequisite checks\n'
  exit "$exit_code"
}
trap 'on_error $LINENO' ERR

# ----------------------------------------------------------------------------
# Docker / Compose discovery
# ----------------------------------------------------------------------------
DOCKER_BIN=""
COMPOSE_CMD=()

detect_docker() {
  if command -v docker >/dev/null 2>&1; then
    DOCKER_BIN=docker
  elif command -v podman >/dev/null 2>&1; then
    DOCKER_BIN=podman
  else
    die "Neither 'docker' nor 'podman' is installed. See README.md → 'Install Docker Engine on Ubuntu'."
  fi

  if "$DOCKER_BIN" compose version >/dev/null 2>&1; then
    COMPOSE_CMD=("$DOCKER_BIN" compose)
  elif command -v docker-compose >/dev/null 2>&1; then
    COMPOSE_CMD=(docker-compose)
    warn "Using legacy docker-compose v1. Compose v2 (the 'docker compose' plugin) is strongly recommended."
  else
    die "Docker Compose v2 is missing. Install it with: sudo apt-get install -y docker-compose-plugin"
  fi
}

# Every compose invocation goes through this so the env file, the Linux overlay
# and the selected profiles are always applied consistently.
compose() {
  local args=("${COMPOSE_CMD[@]}" --env-file "$ENV_FILE" -f "$COMPOSE_FILE")
  [[ -f "$COMPOSE_LINUX_OVERLAY" ]] && args+=(-f "$COMPOSE_LINUX_OVERLAY")
  local p
  for p in "${ACTIVE_PROFILES[@]:-}"; do
    [[ -n "$p" ]] && args+=(--profile "$p")
  done
  "${args[@]}" "$@"
}

# Compose call that targets every profile — used by status/down so optional
# containers are never orphaned.
compose_all() {
  local args=("${COMPOSE_CMD[@]}" --env-file "$ENV_FILE" -f "$COMPOSE_FILE")
  [[ -f "$COMPOSE_LINUX_OVERLAY" ]] && args+=(-f "$COMPOSE_LINUX_OVERLAY")
  args+=(--profile workers --profile ai --profile ats)
  "${args[@]}" "$@"
}

# ----------------------------------------------------------------------------
# Profiles
# ----------------------------------------------------------------------------
ACTIVE_PROFILES=()
WITH_WORKERS=false
WITH_AI=false
WITH_ATS=false
NO_BUILD=false

parse_profile_flags() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --workers)   WITH_WORKERS=true ;;
      --ai)        WITH_AI=true ;;
      --ats)       WITH_ATS=true ;;
      --full)      WITH_WORKERS=true; WITH_AI=true; WITH_ATS=true ;;
      --no-build)  NO_BUILD=true ;;
      *)           die "unknown option: $1" ;;
    esac
    shift
  done

  # PROFILES=workers,ai is also honoured so `make up PROFILES=workers` works.
  if [[ -n "${PROFILES:-}" ]]; then
    local p
    IFS=',' read -ra _requested <<<"$PROFILES"
    for p in "${_requested[@]}"; do
      case "${p// /}" in
        workers) WITH_WORKERS=true ;;
        ai)      WITH_AI=true ;;
        ats)     WITH_ATS=true ;;
        full)    WITH_WORKERS=true; WITH_AI=true; WITH_ATS=true ;;
        "")      ;;
        *)       die "unknown profile in PROFILES: $p (choose from workers, ai, ats, full)" ;;
      esac
    done
  fi

  ACTIVE_PROFILES=()
  $WITH_WORKERS && ACTIVE_PROFILES+=(workers)
  $WITH_AI && ACTIVE_PROFILES+=(ai)
  $WITH_ATS && ACTIVE_PROFILES+=(ats)

  # compose.yaml reads these to decide whether the backend should call the local
  # tailoring model and whether the scheduler should run the batch ATS analysis.
  if $WITH_AI; then export LOCAL_AI_ENABLED=true; else export LOCAL_AI_ENABLED=false; fi
  if $WITH_ATS; then export LOCAL_ATS_ANALYSIS_ENABLED=true; else export LOCAL_ATS_ANALYSIS_ENABLED=false; fi
}

# ----------------------------------------------------------------------------
# Preflight ("doctor")
# ----------------------------------------------------------------------------
gen_secret() {
  if command -v openssl >/dev/null 2>&1; then
    openssl rand -hex 32
  else
    # Coreutils-only fallback; every Ubuntu install has od and tr.
    od -vN32 -An -tx1 /dev/urandom | tr -d ' \n'
  fi
}

port_in_use() {
  local port="$1"
  if command -v ss >/dev/null 2>&1; then
    ss -H -ltn "sport = :$port" 2>/dev/null | grep -q . && return 0
  elif command -v lsof >/dev/null 2>&1; then
    lsof -iTCP:"$port" -sTCP:LISTEN -n -P >/dev/null 2>&1 && return 0
  fi
  return 1
}

port_owned_by_stack() {
  # A port already bound by one of our own containers is fine — `up` is idempotent.
  local port="$1"
  "$DOCKER_BIN" ps --filter "label=com.docker.compose.project=placeup-local" \
    --format '{{.Ports}}' 2>/dev/null | grep -q ":${port}->" && return 0
  return 1
}

doctor() {
  local problems=0

  step "Host prerequisites"

  detect_docker
  ok "container engine: $("$DOCKER_BIN" --version 2>/dev/null | head -1)"

  if ! "$DOCKER_BIN" info >/dev/null 2>&1; then
    fail "the Docker daemon is not reachable by user '$(id -un)'."
    cat <<'EOS'

        Fix on Ubuntu:
          sudo systemctl enable --now docker
          sudo usermod -aG docker "$USER"
          newgrp docker        # or log out and back in

EOS
    problems=$((problems + 1))
  else
    ok "docker daemon reachable"
  fi

  ok "compose: $("${COMPOSE_CMD[@]}" version --short 2>/dev/null || echo unknown)"

  if command -v make >/dev/null 2>&1; then
    ok "make: $(make --version | head -1)"
  else
    fail "'make' is missing.  Fix: sudo apt-get install -y make"
    problems=$((problems + 1))
  fi

  for tool in curl git; do
    if command -v "$tool" >/dev/null 2>&1; then
      ok "$tool present"
    else
      fail "'$tool' is missing.  Fix: sudo apt-get install -y $tool"
      problems=$((problems + 1))
    fi
  done

  step "Capacity"

  local cores mem_gb disk_gb
  cores="$(nproc 2>/dev/null || echo 0)"
  mem_gb="$(awk '/MemTotal/ {printf "%d", $2/1024/1024}' /proc/meminfo 2>/dev/null || echo 0)"
  disk_gb="$(df -BG --output=avail "$ROOT_DIR" 2>/dev/null | tail -1 | tr -dc '0-9' || echo 0)"

  if (( cores >= 4 )); then ok "CPU cores: $cores"; else warn "CPU cores: $cores (4+ recommended)"; fi
  if (( mem_gb >= 8 )); then ok "RAM: ${mem_gb} GiB"
  elif (( mem_gb >= 6 )); then warn "RAM: ${mem_gb} GiB — enough for the core stack, too little for --ai/--ats"
  else fail "RAM: ${mem_gb} GiB — the core stack needs 6 GiB or more"; problems=$((problems + 1)); fi
  if (( disk_gb >= 30 )); then ok "free disk: ${disk_gb} GiB"
  elif (( disk_gb >= 15 )); then warn "free disk: ${disk_gb} GiB — core stack fits, local models will not"
  else fail "free disk: ${disk_gb} GiB — images alone need ~15 GiB"; problems=$((problems + 1)); fi

  step "Port availability (loopback only)"

  local -a checks=( "$PORT_FRONTEND frontend" "$PORT_API API" "$PORT_POSTGRES PostgreSQL" \
                    "$PORT_FIRESTORE Firestore-emulator" "$PORT_REDIS Redis" )
  $WITH_AI  && checks+=( "$PORT_OLLAMA Ollama" "$PORT_OPENCLAW OpenClaw" )
  $WITH_ATS && checks+=( "$PORT_ATS ATS-model" )

  local entry port label
  for entry in "${checks[@]}"; do
    port="${entry%% *}"; label="${entry#* }"
    if port_in_use "$port"; then
      if port_owned_by_stack "$port"; then
        ok "port $port ($label) held by the running PlaceUp stack"
      else
        fail "port $port ($label) is already in use by another process."
        dim "        Identify it with:  sudo ss -ltnp 'sport = :$port'"
        problems=$((problems + 1))
      fi
    else
      ok "port $port ($label) free"
    fi
  done

  step "Repository layout"
  for f in "$COMPOSE_FILE" "$ENV_EXAMPLE" backend/Dockerfile frontend/Dockerfile frontend/nginx.local.conf; do
    if [[ -e "$ROOT_DIR/$f" || -e "$f" ]]; then ok "$f"; else fail "missing: $f"; problems=$((problems + 1)); fi
  done

  echo
  if (( problems > 0 )); then
    die "$problems blocking problem(s) found. Fix the items marked FAIL and re-run 'make doctor'."
  fi
  ok "host is ready for 'make up'"
}

# ----------------------------------------------------------------------------
# Environment file
# ----------------------------------------------------------------------------
ensure_env_file() {
  if [[ -f "$ENV_FILE" ]]; then
    # Guard against a half-written file from an interrupted first run.
    if grep -q '__GENERATE__' "$ENV_FILE"; then
      info "filling in placeholder secrets left in .env.local"
      local key
      for key in JWT_SECRET INTERNAL_API_KEY SERVICE_TOKEN_SECRET OPENCLAW_TAILOR_TOKEN ATS_MODEL_SERVICE_TOKEN; do
        local secret; secret="$(gen_secret)"
        sed -i "s|^${key}=__GENERATE__$|${key}=${secret}|" "$ENV_FILE"
      done
    fi
    ok "using existing $ENV_FILE"
    return
  fi

  [[ -f "$ENV_EXAMPLE" ]] || die "missing $ENV_EXAMPLE — cannot generate local configuration"

  info "creating .env.local with freshly generated per-machine secrets"
  local tmp; tmp="$(mktemp)"
  cp "$ENV_EXAMPLE" "$tmp"
  local key secret
  for key in JWT_SECRET INTERNAL_API_KEY SERVICE_TOKEN_SECRET OPENCLAW_TAILOR_TOKEN ATS_MODEL_SERVICE_TOKEN; do
    secret="$(gen_secret)"
    sed -i "s|^${key}=__GENERATE__$|${key}=${secret}|" "$tmp"
  done
  mv "$tmp" "$ENV_FILE"
  chmod 600 "$ENV_FILE"
  ok "wrote $ENV_FILE (mode 600, git-ignored)"
}

# ----------------------------------------------------------------------------
# Readiness gating
# ----------------------------------------------------------------------------
http_status() {
  curl -s -o /dev/null -w '%{http_code}' --max-time "${2:-5}" "$1" 2>/dev/null || echo 000
}

wait_for_http() {
  local url="$1" label="$2" timeout="${3:-$READY_TIMEOUT_SECONDS}"
  local deadline=$(( SECONDS + timeout )) code
  printf '  %-22s' "$label"
  while (( SECONDS < deadline )); do
    code="$(http_status "$url" 4)"
    if [[ "$code" == "200" ]]; then
      printf '%sready%s (%s)\n' "$C_GREEN" "$C_RESET" "$url"
      return 0
    fi
    printf '.'
    sleep 3
  done
  printf '%s timed out%s (last HTTP %s)\n' "$C_RED" "$C_RESET" "$code"
  return 1
}

wait_for_oneshot() {
  # migrate / seed are run-once services: success is "exited 0", not "healthy".
  local service="$1" timeout="${2:-600}"
  local deadline=$(( SECONDS + timeout )) cid state code
  printf '  %-22s' "$service"
  while (( SECONDS < deadline )); do
    cid="$(compose ps -aq "$service" 2>/dev/null | head -1 || true)"
    if [[ -n "$cid" ]]; then
      state="$("$DOCKER_BIN" inspect -f '{{.State.Status}}' "$cid" 2>/dev/null || echo unknown)"
      if [[ "$state" == "exited" ]]; then
        code="$("$DOCKER_BIN" inspect -f '{{.State.ExitCode}}' "$cid")"
        if [[ "$code" == "0" ]]; then
          printf '%scompleted%s\n' "$C_GREEN" "$C_RESET"
          return 0
        fi
        printf '%s failed (exit %s)%s\n' "$C_RED" "$code" "$C_RESET"
        echo
        fail "'$service' failed. Last 40 log lines:"
        compose logs --tail 40 "$service" || true
        return 1
      fi
    fi
    printf '.'
    sleep 3
  done
  printf '%s timed out%s\n' "$C_RED" "$C_RESET"
  return 1
}

# ----------------------------------------------------------------------------
# Smoke verification — the proof that "it is actually running"
# ----------------------------------------------------------------------------
SMOKE_PASS=0
SMOKE_FAIL=0

check() {
  local label="$1"; shift
  printf '  %-46s' "$label"
  if "$@" >/dev/null 2>&1; then
    printf '%sPASS%s\n' "$C_GREEN" "$C_RESET"
    SMOKE_PASS=$((SMOKE_PASS + 1))
  else
    printf '%sFAIL%s\n' "$C_RED" "$C_RESET"
    SMOKE_FAIL=$((SMOKE_FAIL + 1))
  fi
}

expect_200() { [[ "$(http_status "$1" 10)" == "200" ]]; }
expect_contains() { curl -s --max-time 10 "$1" | grep -qF "$2"; }

# `alembic current` prints the active revision with a "(head)" marker once the
# schema is fully migrated; anything else means a migration did not land.
alembic_at_head() { compose exec -T api alembic current 2>/dev/null | grep -q '(head)'; }

smoke() {
  detect_docker
  step "Smoke verification"

  check "frontend  GET /healthz"                     expect_200 "http://localhost:${PORT_FRONTEND}/healthz"
  check "frontend  GET / serves the SPA shell"       expect_contains "http://localhost:${PORT_FRONTEND}/" "<div id=\"root\""
  check "backend   GET /api/health"                  expect_contains "http://localhost:${PORT_API}/api/health" '"status":"ok"'
  check "backend   GET /docs (OpenAPI UI)"           expect_200 "http://localhost:${PORT_API}/docs"
  check "backend   GET /openapi.json"                expect_contains "http://localhost:${PORT_API}/openapi.json" '"openapi"'
  check "wiring    frontend -> backend via /api/*"   expect_contains "http://localhost:${PORT_FRONTEND}/api/health" '"status":"ok"'
  check "postgres  accepting connections"            compose exec -T postgres pg_isready -U placeup -d placeup
  check "postgres  alembic schema at head"           alembic_at_head
  check "redis     PING"                             compose exec -T redis redis-cli ping
  check "firestore emulator TCP 8080"                compose exec -T firestore bash -c '</dev/tcp/127.0.0.1/8080'
  check "api       internal app-server reachable"    compose exec -T api python -c "import urllib.request,os;urllib.request.urlopen(os.environ['APP_SERVER_URL'].rstrip('/')+'/api/health',timeout=8)"

  if $WITH_AI; then
    check "openclaw  GET /healthz"                   expect_200 "http://localhost:${PORT_OPENCLAW}/healthz"
    check "ollama    GET /api/tags"                  expect_200 "http://localhost:${PORT_OLLAMA}/api/tags"
  fi
  if $WITH_ATS; then
    check "ats-model GET /healthz"                   expect_200 "http://localhost:${PORT_ATS}/healthz"
  fi

  echo
  if (( SMOKE_FAIL > 0 )); then
    fail "$SMOKE_FAIL check(s) failed, $SMOKE_PASS passed."
    dim "  Inspect with: make status   |   make logs-api   |   make logs-frontend"
    return 1
  fi
  ok "all $SMOKE_PASS checks passed"
}


# ----------------------------------------------------------------------------
# Subcommands
# ----------------------------------------------------------------------------
print_urls() {
  local header="${1:-PlaceUp local endpoints}"
  cat <<EOS

${C_BOLD}${header}${C_RESET}

  ${C_BOLD}Open the application${C_RESET}    ${C_GREEN}http://localhost:${PORT_FRONTEND}${C_RESET}
  API + interactive docs  http://localhost:${PORT_API}/docs
  API health              http://localhost:${PORT_API}/api/health
  ATS supply coverage     http://localhost:${PORT_API}/api/health/ats-coverage

  PostgreSQL              127.0.0.1:${PORT_POSTGRES}   (db placeup / user placeup)
  Firestore emulator      127.0.0.1:${PORT_FIRESTORE}
  Redis                   127.0.0.1:${PORT_REDIS}
EOS
  $WITH_AI  && printf '  Ollama                  127.0.0.1:%s\n  OpenClaw health         http://localhost:%s/healthz\n' "$PORT_OLLAMA" "$PORT_OPENCLAW"
  $WITH_ATS && printf '  ATS model health        http://localhost:%s/healthz\n' "$PORT_ATS"
  cat <<EOS

  Every port binds to 127.0.0.1 only — nothing is exposed to your LAN.

  ${C_DIM}Next:  make status   make logs   make jobs   make down${C_RESET}
EOS
  if ! $WITH_WORKERS; then
    echo
    dim "  The catalogue starts empty. Populate it with:  make job NAME=job-scraper-am"
    dim "  Or start the full stack including schedulers:  make up-full"
  fi
}

cmd_up() {
  parse_profile_flags "$@"
  doctor
  ensure_env_file

  step "Building and starting containers"
  local up_args=(up -d --remove-orphans)
  $NO_BUILD || up_args+=(--build)
  dim "  profiles: ${ACTIVE_PROFILES[*]:-core only}"
  dim "  first run pulls ~6 GiB of images and builds the Playwright-enabled backend; expect 5-15 minutes."
  if ! compose "${up_args[@]}"; then
    diagnose
    die "'docker compose up' failed — see the container logs printed above"
  fi

  step "Waiting for the stack to become ready"
  wait_for_oneshot migrate 900 || { diagnose; die "database migrations did not complete"; }
  wait_for_oneshot seed    600 || { diagnose; die "reference-data seeding did not complete"; }
  wait_for_http "http://localhost:${PORT_API}/api/health"   "backend API" 300 || { diagnose; die "the API never became healthy"; }
  wait_for_http "http://localhost:${PORT_FRONTEND}/healthz" "frontend"    180 || { diagnose; die "the frontend never became healthy"; }

  smoke || { diagnose; die "the stack started but smoke verification failed"; }
  print_urls "PlaceUp is running."
}

# Dump the evidence an operator needs when a start-up fails, so they do not have
# to know which container to look at first.
diagnose() {
  step "Diagnostics"
  compose ps -a || true
  local svc
  for svc in migrate seed api app-server frontend; do
    local cid; cid="$(compose ps -aq "$svc" 2>/dev/null | head -1 || true)"
    [[ -n "$cid" ]] || continue
    local state code
    state="$("$DOCKER_BIN" inspect -f '{{.State.Status}}' "$cid" 2>/dev/null || echo unknown)"
    code="$("$DOCKER_BIN" inspect -f '{{.State.ExitCode}}' "$cid" 2>/dev/null || echo ?)"
    if [[ "$state" != "running" && "$code" != "0" ]]; then
      fail "$svc is $state (exit $code) — last 40 log lines:"
      compose logs --tail 40 "$svc" 2>&1 | sed 's/^/      /' || true
    fi
  done
}

cmd_down() {
  detect_docker
  [[ -f "$ENV_FILE" ]] || ENV_FILE="$ENV_EXAMPLE"
  info "stopping PlaceUp (all data volumes are preserved)"
  compose_all down --remove-orphans
  ok "stopped. Start again with 'make up' — your database is intact."
}

cmd_reset() {
  detect_docker
  [[ -f "$ENV_FILE" ]] || ENV_FILE="$ENV_EXAMPLE"
  if [[ "${FORCE:-}" != "1" && -t 0 ]]; then
    printf '%sThis deletes the local PostgreSQL database, Firestore emulator data, Redis,\n' "$C_YELLOW"
    printf 'tailored documents and all downloaded model weights.%s\n' "$C_RESET"
    read -r -p "Type 'destroy' to confirm: " answer
    [[ "$answer" == "destroy" ]] || { info "cancelled — nothing was deleted"; return 0; }
  fi
  compose_all down --remove-orphans --volumes
  ok "all local PlaceUp volumes removed"
}

cmd_status() {
  detect_docker
  [[ -f "$ENV_FILE" ]] || ENV_FILE="$ENV_EXAMPLE"
  step "Containers"
  compose_all ps
  step "Health probes"
  local entry url label code
  for entry in \
    "http://localhost:${PORT_FRONTEND}/healthz|frontend" \
    "http://localhost:${PORT_API}/api/health|backend API" \
    "http://localhost:${PORT_FRONTEND}/api/health|frontend->backend proxy" \
    "http://localhost:${PORT_OPENCLAW}/healthz|openclaw (ai profile)" \
    "http://localhost:${PORT_ATS}/healthz|ats model (ats profile)"
  do
    url="${entry%%|*}"; label="${entry##*|}"
    code="$(http_status "$url" 4)"
    if [[ "$code" == "200" ]]; then
      printf '  %-28s %shealthy%s\n' "$label" "$C_GREEN" "$C_RESET"
    else
      printf '  %-28s %snot running / starting (HTTP %s)%s\n' "$label" "$C_YELLOW" "$code" "$C_RESET"
    fi
  done
  step "Disk used by PlaceUp volumes"
  "$DOCKER_BIN" system df -v 2>/dev/null | grep -E 'VOLUME NAME|placeup-local' || dim "  (no volumes yet)"
}

cmd_logs() {
  detect_docker
  [[ -f "$ENV_FILE" ]] || ENV_FILE="$ENV_EXAMPLE"
  if [[ $# -gt 0 ]]; then
    compose_all logs -f --tail 200 "$@"
  else
    compose_all logs -f --tail 100
  fi
}

cmd_job() {
  detect_docker
  local name="${1:-}"
  [[ -n "$name" ]] || die "usage: make job NAME=<job-name>   (see 'make jobs')"
  [[ -f "$ENV_FILE" ]] || die "run 'make up' first so .env.local exists"
  ACTIVE_PROFILES=(workers)
  export LOCAL_AI_ENABLED="${LOCAL_AI_ENABLED:-false}"
  export LOCAL_ATS_ANALYSIS_ENABLED="${LOCAL_ATS_ANALYSIS_ENABLED:-true}"
  info "running worker '$name' to completion"
  compose run --rm --no-deps scheduler python -m app.workers.local_scheduler --run "$name"
  ok "worker '$name' finished"
}

cmd_jobs() {
  detect_docker
  [[ -f "$ENV_FILE" ]] || die "run 'make up' first so .env.local exists"
  ACTIVE_PROFILES=(workers)
  compose run --rm --no-deps scheduler python -m app.workers.local_scheduler --list
}

cmd_test() {
  detect_docker
  [[ -f "$ENV_FILE" ]] || die "run 'make up' first so .env.local exists"
  info "running the backend test suite inside the api container"
  compose exec -T api python -m pytest -q "$@"
}

cmd_shell() {
  detect_docker
  [[ -f "$ENV_FILE" ]] || ENV_FILE="$ENV_EXAMPLE"
  compose exec "${1:-api}" bash
}

cmd_psql() {
  detect_docker
  [[ -f "$ENV_FILE" ]] || ENV_FILE="$ENV_EXAMPLE"
  compose exec postgres psql -U placeup -d placeup "$@"
}

usage() {
  cat <<'EOS'
placeup.sh — PlaceUp local runtime controller

  up [--workers] [--ai] [--ats] [--full] [--no-build]
                     Build, start, migrate, seed, health-gate and verify the stack
  down               Stop everything, keep all data
  reset              Stop everything and DELETE every local volume
  status             Container state + HTTP health probes + volume disk usage
  logs [service...]  Follow logs
  smoke              Re-run the verification suite against a running stack
  doctor             Host prerequisite checks only
  job NAME           Run one background worker to completion
  jobs               List the configured worker schedule
  test [args...]     Run the backend pytest suite inside the api container
  shell [service]    Interactive shell in a container (default: api)
  psql [args...]     psql inside the PostgreSQL container
  env                Create .env.local with fresh random secrets

Prefer the Makefile: `make help`.
EOS
}

main() {
  local cmd="${1:-up}"; shift || true
  case "$cmd" in
    up)      cmd_up "$@" ;;
    down)    cmd_down ;;
    reset)   cmd_reset ;;
    status)  cmd_status ;;
    logs)    cmd_logs "$@" ;;
    smoke)   detect_docker; parse_profile_flags "$@"; smoke ;;
    doctor)  parse_profile_flags "$@"; doctor ;;
    job)     cmd_job "$@" ;;
    jobs)    cmd_jobs ;;
    test)    cmd_test "$@" ;;
    shell)   cmd_shell "$@" ;;
    psql)    cmd_psql "$@" ;;
    env)     ensure_env_file ;;
    urls)    print_urls ;;
    -h|--help|help) usage ;;
    *)       usage; die "unknown command: $cmd" ;;
  esac
}

main "$@"

<div align="center">

# PlaceUp Career

### Every sponsored job, straight from the employer's own ATS — found, scored, tailored and applied to for you.

**A production job-search platform: a multi-country ATS crawler, an H-1B/visa-sponsorship
knowledge base, deterministic CV↔JD scoring, LLM résumé tailoring, and one-click
application submission — all runnable end to end on a single Ubuntu workstation.**

[Quick start](#quick-start) · [Verify it works](#verify-that-it-actually-works) ·
[Commands](#command-reference) · [Configuration](#configuration) ·
[Troubleshooting](#troubleshooting) · [Architecture](#architecture)

</div>

---

## Quick start

Three commands from a clean Ubuntu 22.04 / 24.04 machine to a running application:

```bash
git clone <your-remote> PlaceUp && cd PlaceUp
make doctor     # optional: confirms Docker, RAM, disk and free ports
make up         # <-- the only command you need
```

`make up` does all of this, in order, and refuses to report success until every
step has actually passed:

| # | Step | What it proves |
|---|------|----------------|
| 1 | Host preflight | Docker daemon reachable, ≥6 GiB RAM, ≥15 GiB disk, ports 3000/8000/5432/6379/8085 free |
| 2 | Secret generation | `.env.local` created with five independent 256-bit random secrets, mode `600` |
| 3 | Image build | Backend (Python 3.12 + Playwright/Chromium) and frontend (Vite build → Nginx) images built |
| 4 | Datastores | PostgreSQL 16, the Firestore emulator and Redis 7 all report healthy |
| 5 | Migrations | `alembic upgrade head` exits 0 |
| 6 | Seeding | H-1B / visa sponsor reference data loaded |
| 7 | Services | Public API, private app-server and the Nginx frontend all report healthy |
| 8 | Smoke suite | 11 checks including **frontend → backend proxy over HTTP** and **schema at head** |

When it finishes you get:

```
PlaceUp is running.

  Open the application   http://localhost:3000
  API + interactive docs  http://localhost:8000/docs
  API health              http://localhost:8000/api/health
  ATS supply coverage     http://localhost:8000/api/health/ats-coverage
  ...
```

> **First run takes 5–15 minutes.** It pulls roughly 6 GiB of base images and
> builds a Playwright/Chromium-enabled Python image. Every run after that starts
> in well under a minute — use `make up-fast` to skip the rebuild entirely.

**No `make` on the box?** `bash scripts/placeup.sh up` is the identical command.
(Everything is invoked through `bash`, so a missing executable bit after a
checkout from Windows never matters.)

---

## Table of contents

- [Prerequisites](#prerequisites)
- [Installing Docker on Ubuntu](#installing-docker-on-ubuntu)
- [Running the application](#running-the-application)
- [Verify that it actually works](#verify-that-it-actually-works)
- [Command reference](#command-reference)
- [Background workers and fresh job data](#background-workers-and-fresh-job-data)
- [Local AI: résumé tailoring and ATS scoring](#local-ai-résumé-tailoring-and-ats-scoring)
- [Configuration](#configuration)
- [Ports and URLs](#ports-and-urls)
- [Day-2 operations](#day-2-operations)
- [Testing](#testing)
- [Troubleshooting](#troubleshooting)
- [Architecture](#architecture)
- [Repository layout](#repository-layout)
- [Production vs local](#production-vs-local)
- [Appendix: running without Docker](#appendix-running-without-docker)
- [Documentation index](#documentation-index)
- [Credits and prior art](#credits-and-prior-art)

---

## Prerequisites

| | Minimum | Recommended | Needed for |
|---|---|---|---|
| **OS** | Ubuntu 22.04 LTS | Ubuntu 24.04 LTS | Also works on Debian 12, Fedora 40+, and Ubuntu under WSL 2 |
| **CPU** | 2 cores | 4+ cores | Image builds and the scraper are the CPU-heavy parts |
| **RAM** | 6 GiB | 16 GiB | 6 GiB runs the app; `--ai` needs 12 GiB+; `--ats` needs 24 GiB+ or a GPU |
| **Disk** | 15 GiB free | 60 GiB free | Base images ~6 GiB, built images ~5 GiB, model weights 5–20 GiB |
| **Network** | Outbound HTTPS | — | Pulling images, and the scraper reaching employer career pages |

Host packages: **Docker Engine + Compose v2**, `make`, `git`, `curl`. That is the
complete list. PostgreSQL, Redis, Java (for the Firestore emulator), Node, Python,
Playwright, Ollama and OpenClaw all run **inside containers** — nothing is
installed onto your host.

Verify what you have:

```bash
docker --version              # Docker version 24.x or newer
docker compose version        # Docker Compose version v2.20 or newer
make --version | head -1      # GNU Make 4.x
git --version
curl --version | head -1
```

### Installing Docker on Ubuntu

Use Docker's own apt repository. The `docker.io` package in Ubuntu's default
archive ships an old engine and, on some releases, no Compose v2 plugin.

```bash
# 1. Remove any conflicting distro packages
for pkg in docker.io docker-doc docker-compose docker-compose-v2 podman-docker containerd runc; do
  sudo apt-get remove -y "$pkg" 2>/dev/null || true
done

# 2. Add Docker's official GPG key
sudo apt-get update
sudo apt-get install -y ca-certificates curl gnupg make git
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc

# 3. Add the repository for your Ubuntu release
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] \
  https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "${UBUNTU_CODENAME:-$VERSION_CODENAME}") stable" \
  | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# 4. Install the engine, the CLI and the Compose v2 plugin
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io \
                        docker-buildx-plugin docker-compose-plugin

# 5. Start it and allow your user to talk to it without sudo
sudo systemctl enable --now docker
sudo usermod -aG docker "$USER"
newgrp docker            # or log out and back in

# 6. Confirm
docker run --rm hello-world
docker compose version
```

`make doctor` re-checks all of this and prints the exact fix for anything missing.

---

## Running the application

### The one command

```bash
make up
```

That is the whole thing: frontend server, backend API, the private internal
app-server, PostgreSQL, the Firestore emulator and Redis, migrated, seeded,
health-gated and verified. Open <http://localhost:3000>.

### Optional profiles

The core stack is the application. Three optional profiles add the pieces that
cost real CPU, RAM and disk, so you switch them on deliberately:

```bash
make up            # core: frontend + backend + datastores
make up-workers    # core + the background scheduler (scraping, digests, retention)
make up-ai         # core + local Ollama/OpenClaw résumé tailoring (qwen2.5:7b)
make up-ats        # core + the heavyweight local ATS scoring model
make up-full       # all of the above
```

Profiles compose freely and can also be set with a variable:

```bash
make up PROFILES=workers,ai
```

### Stopping, restarting and resetting

```bash
make down      # stop everything — every data volume is preserved
make restart   # stop and start again without rebuilding images
make up-fast   # start without rebuilding (after your first successful `make up`)
make reset     # DESTRUCTIVE: stop and delete the database, emulator data,
               # tailored documents and every downloaded model weight
```

`make reset` prompts for the literal word `destroy` before doing anything. In a
script, set `FORCE=1 make reset`.

---

## Verify that it actually works

`make up` already runs all of this for you and fails loudly if any check does not
pass. Run it again at any time against a live stack:

```bash
make health
```

```
Smoke verification
  frontend  GET /healthz                          PASS
  frontend  GET / serves the SPA shell            PASS
  backend   GET /api/health                       PASS
  backend   GET /docs (OpenAPI UI)                PASS
  backend   GET /openapi.json                     PASS
  wiring    frontend -> backend via /api/*        PASS
  postgres  accepting connections                 PASS
  postgres  alembic schema at head                PASS
  redis     PING                                  PASS
  firestore emulator TCP 8080                     PASS
  api       internal app-server reachable         PASS

  ok   all 11 checks passed
```

### Checking each layer by hand

Every one of these is a real command with a real expected output.

**1 — The frontend is serving.**

```bash
curl -i http://localhost:3000/healthz
```
```
HTTP/1.1 200 OK
Content-Type: text/plain
...
ok
```

**2 — The frontend is serving the actual application, not a placeholder.**

```bash
curl -s http://localhost:3000/ | grep -o '<div id="root">'
```
```
<div id="root">
```

**3 — The backend API is alive.**

```bash
curl -s http://localhost:8000/api/health | python3 -m json.tool
```
```json
{
    "status": "ok",
    "timestamp": "2026-08-18T09:14:22.104913+00:00"
}
```

**4 — The frontend can reach the backend.** This is the check that catches a
broken Nginx proxy, the single most common "the page loads but nothing works"
failure. It goes through port 3000, not 8000:

```bash
curl -s http://localhost:3000/api/health | python3 -m json.tool
```
```json
{
    "status": "ok",
    "timestamp": "2026-08-18T09:14:25.882110+00:00"
}
```

**5 — The interactive API documentation.** Open <http://localhost:8000/docs> in a
browser, or:

```bash
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8000/docs        # 200
curl -s http://localhost:8000/openapi.json | python3 -c \
  'import json,sys; d=json.load(sys.stdin); print(len(d["paths"]), "endpoints")'
```

**6 — The database schema is fully migrated.**

```bash
docker compose --env-file .env.local exec -T api alembic current
```
```
<revision-hash> (head)
```

**7 — PostgreSQL is reachable and holds the seeded reference data.**

```bash
make psql ARGS="-c '\dt'"                                   # list tables
make psql ARGS="-c 'select count(*) from job_postings;'"    # 0 until you scrape
make psql ARGS="-c 'select count(*) from h1b_sponsors;'"    # non-zero after seeding
```

**8 — Redis and the Firestore emulator.**

```bash
docker compose --env-file .env.local exec -T redis redis-cli ping       # PONG
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8085/         # 200
```

**9 — The scraper supply mix.** Once you have run a scrape, this endpoint tells
you whether jobs are coming from first-party ATS boards or from aggregators —
the health signal that matters most for one-click apply:

```bash
curl -s 'http://localhost:8000/api/health/ats-coverage?hours=168' | python3 -m json.tool
```

**10 — Full container and volume state.**

```bash
make status
```

---

## Command reference

```bash
make help      # this table, always current
```

### Lifecycle

| Command | Description |
|---|---|
| `make up` | **Run the complete application** — build, migrate, seed, health-gate, verify |
| `make up-full` | Everything, including schedulers and both local AI profiles |
| `make up-workers` | Core plus the background worker scheduler |
| `make up-ai` | Core plus local Ollama + OpenClaw résumé tailoring |
| `make up-ats` | Core plus the local Mistral-based ATS scoring service |
| `make up-fast` | Start without rebuilding images |
| `make down` | Stop everything; all data preserved |
| `make restart` | Stop and start again, no rebuild |
| `make reset` | **Destructive** — delete every local volume |

### Inspection

| Command | Description |
|---|---|
| `make status` | Container state, HTTP health probes, volume disk usage |
| `make health` | Re-run the 11-check smoke suite |
| `make doctor` | Host prerequisite checks only — safe to run any time |
| `make urls` | Print every local URL and port |
| `make size` | How much disk PlaceUp's images and volumes are using |

### Logs

| Command | Description |
|---|---|
| `make logs` | Follow every container |
| `make logs-api` | Backend API only |
| `make logs-frontend` | Nginx frontend only |
| `make logs-scheduler` | Background workers only |

### Data and workers

| Command | Description |
|---|---|
| `make jobs` | List every background job and its schedule |
| `make job NAME=job-scraper-am` | Run one job to completion, right now |
| `make psql` | `psql` against the local database |
| `make psql ARGS="-c 'select 1'"` | Run one statement |
| `make redis` | `redis-cli` against local Redis |

### Development

| Command | Description |
|---|---|
| `make test` | Backend pytest suite inside the running API container |
| `make test ARGS="-k apply -v"` | Pass arguments through to pytest |
| `make build` | Rebuild images without starting anything |
| `make shell` | Interactive shell in the backend container |
| `make shell-frontend` | Interactive shell in the frontend container |
| `make env` | Recreate `.env.local` with fresh random secrets |
| `make clean-images` | Prune dangling images and build cache |

---

## Background workers and fresh job data

The local database starts with sponsor reference data but **no job postings and
no user records**. Production data is deliberately never copied down: it contains
private user information, and moving it is an explicit migration decision, not a
side effect of starting a dev environment.

Populate the catalogue by running the scraper once:

```bash
make job NAME=job-scraper-am
```

This crawls the same 32-country × role taxonomy the cloud deployment uses, but
collapsed into one bounded process that respects `SCRAPE_MAX_CONCURRENCY` and
`SCRAPER_RUN_BUDGET_SECONDS` so it cannot saturate your workstation.

### Every available job

```bash
make jobs
```

| Job | Module | Default schedule | What it does |
|---|---|---|---|
| `job-scraper-am` | `app.etl.jobs_scraper_6h` | 11:00 | Full multi-country ATS crawl |
| `job-scraper-pm` | `app.etl.jobs_scraper_6h` | 20:00 | Second daily crawl |
| `daily-match-digest` | `app.etl.daily_match_digest` | 09:00 | Per-user match email digest |
| `jd-repair` | `app.workers.job_description_repair` | every 2h | Refetch truncated/broken descriptions |
| `company-link-resolver` | `app.workers.company_link_resolver` | every 2h | Resolve official company career URLs |
| `board-discovery` | `app.workers.board_discovery_sweep` | every 6h | Discover new ATS boards |
| `job-liveness` | `app.workers.job_liveness_checker` | every 6h | Mark dead postings closed |
| `stale-jobs` | `app.workers.stale_jobs_sweeper` | 03:30 | Sweep postings past retention |
| `job-retention` | `app.workers.job_retention` | 04:15 | 60-day + non-taxonomy purge |
| `ats-worker` | `app.workers.ats_worker` | 02:30 | Per-user ATS scoring pass |
| `taxonomy-report` | `app.workers.taxonomy_evolution` | Sun 05:00 | Weekly taxonomy drift report |
| `master-ats-analysis` | `app.workers.master_ats_analysis` | 01:00 | Batch JD analysis (needs `--ats`) |

Run any of them immediately:

```bash
make job NAME=jd-repair
make job NAME=job-retention
make job NAME=job-liveness
```

Or start `make up-workers` and let the local scheduler (an APScheduler process
replacing Cloud Scheduler) run them on the schedule above. Watch it with
`make logs-scheduler`.

Disable specific jobs without editing code:

```bash
# in .env.local
LOCAL_SCHEDULER_DISABLED_JOBS=board-discovery,master-ats-analysis
```

---

## Local AI: résumé tailoring and ATS scoring

Both AI profiles are **off by default** and the application is fully functional
without them — the backend keeps its deterministic tailoring and scoring
fallbacks. Turn them on when you want to exercise the model-backed paths.

### `make up-ai` — résumé tailoring

Starts Ollama, pulls `qwen2.5:7b` (~4.7 GiB) and runs the OpenClaw tailoring
service. Résumé and job-description text never leave the Compose network; only a
loopback health port is published.

```bash
make up-ai
curl -s http://localhost:8090/healthz            # OpenClaw
curl -s http://localhost:11434/api/tags | python3 -m json.tool   # model present
```

Pick a smaller model on a constrained machine:

```bash
# in .env.local
OLLAMA_MODEL=qwen2.5:3b
```

### `make up-ats` — batch ATS scoring

Runs `SlyGoblin/mistral_ATSscore_generation`. Its Mistral 7B base is
substantially heavier than the tailoring model.

**NVIDIA GPU (strongly recommended).** Install the container toolkit, then set
the device:

```bash
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey \
  | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list \
  | sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' \
  | sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
sudo apt-get update && sudo apt-get install -y nvidia-container-toolkit
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker
docker run --rm --gpus all nvidia/cuda:12.4.0-base-ubuntu22.04 nvidia-smi
```

```bash
# in .env.local
ATS_DEVICE=cuda
ATS_LOAD_IN_4BIT=true
```

**CPU only.** Supported but slow, and it wants a lot of RAM:

```bash
# in .env.local
ATS_DEVICE=cpu
ATS_LOAD_IN_4BIT=false
```

The ordinary in-app match and ATS calculations do not need this service at all.

---

## Configuration

`make up` creates `.env.local` from `.env.local.example` on first run, generating
five independent 256-bit secrets and writing the file with mode `600`. It is
git-ignored. **Never commit it, and never reuse these values in a deployed
environment.**

| Key | Default | Purpose |
|---|---|---|
| `LOCAL_POSTGRES_PASSWORD` | `placeup_local_dev` | Local database password |
| `JWT_SECRET` | generated | Session token signing |
| `INTERNAL_API_KEY` | generated | API → app-server calls |
| `SERVICE_TOKEN_SECRET` | generated | Service-to-service tokens |
| `OPENCLAW_TAILOR_TOKEN` | generated | Auth for the tailoring service |
| `ATS_MODEL_SERVICE_TOKEN` | generated | Auth for the ATS model service |
| `ADMIN_EMAILS` | `operations@placeupcareer.com` | Accounts granted the admin UI |
| `LOCAL_TIMEZONE` | `America/Chicago` | Timezone for the worker schedule |
| `LOCAL_WORKER_CONCURRENCY` | `2` | Parallel scheduled jobs |
| `LOCAL_SCHEDULER_DISABLED_JOBS` | — | Comma-separated jobs to skip |
| `OLLAMA_MODEL` | `qwen2.5:7b` | Local tailoring model |
| `SCRAPE_MAX_CONCURRENCY` | `8` | Simultaneous board fetches |
| `SCRAPER_RUN_BUDGET_SECONDS` | `10800` | Hard stop for one crawl |
| `ATS_DEVICE` / `ATS_LOAD_IN_4BIT` | `auto` / `true` | ATS model placement |
| `USAJOBS_*`, `ADZUNA_*`, `HUNTER_API_KEY`, `GREENHOUSE_BOARD_TOKENS` | empty | Optional providers — empty simply disables them |

Linux host tuning lives in `compose.linux.yaml` and is also overridable from
`.env.local`:

| Key | Default | Purpose |
|---|---|---|
| `PLACEUP_PG_SHARED_BUFFERS` | `512MB` | PostgreSQL page cache |
| `PLACEUP_PG_WORK_MEM` | `16MB` | Per-sort working memory |
| `PLACEUP_PG_MAX_CONNECTIONS` | `200` | Connection ceiling |
| `PLACEUP_SCRAPER_SHM_SIZE` | `1gb` | `/dev/shm` for Playwright/Chromium |
| `PLACEUP_READY_TIMEOUT` | `900` | Seconds `make up` waits for readiness |

### What local mode deliberately turns off

Signup email verification, OTP MFA, billing gates, live ATS submission,
Cloudflare origin checks and hosted email are all **off**, and email uses the
console provider (messages are printed to `make logs-api`). Local mode also
substitutes every Google Cloud dependency:

| Production | Local replacement |
|---|---|
| Cloud SQL | PostgreSQL 16 container, persistent named volume |
| Firestore | Official Firestore emulator, persistent data directory |
| Cloud Storage | Private volume served through the ownership-checked API |
| Cloud Tasks | In-process, idempotent application queue |
| Cloud Scheduler / Run Jobs | `app.workers.local_scheduler` container |
| Cloud Run API | FastAPI container on `127.0.0.1:8000` |
| Private app server | Internal-only FastAPI container, not published |
| Cloud Run frontend | Nginx container on `127.0.0.1:3000` |
| Hosted tailoring model | OpenClaw + Ollama |
| GPU ATS batch VM | Optional local Hugging Face ATS container |
| Memorystore | Redis 7 container with append-only persistence |

Scraping still needs ordinary outbound internet access to employer career pages.

---

## Ports and URLs

| Service | URL / address | Profile |
|---|---|---|
| **Web application** | <http://localhost:3000> | core |
| API + Swagger UI | <http://localhost:8000/docs> | core |
| API health | <http://localhost:8000/api/health> | core |
| ATS supply coverage | <http://localhost:8000/api/health/ats-coverage> | core |
| ReDoc | <http://localhost:8000/redoc> | core |
| PostgreSQL | `127.0.0.1:5432` (db `placeup`, user `placeup`) | core |
| Firestore emulator | `127.0.0.1:8085` | core |
| Redis | `127.0.0.1:6379` | core |
| Ollama | `127.0.0.1:11434` | `--ai` |
| OpenClaw health | <http://localhost:8090/healthz> | `--ai` |
| ATS model health | <http://localhost:8091/healthz> | `--ats` |

**Every published port binds to `127.0.0.1` only.** Nothing is reachable from
your LAN or the internet. If you ever need remote access, put an authenticated
reverse proxy in front — do not change the bind address.

---

## Day-2 operations

### Logs

Logs are JSON-file, rotated at 20 MB × 5 files per service (50 MB × 5 for
workers), so a runaway crawl cannot fill your disk.

```bash
make logs                                   # everything
make logs-api                               # backend only
docker compose --env-file .env.local logs --since 15m api
docker compose --env-file .env.local logs api | grep -i error
```

### Database

```bash
make psql                                                   # interactive
make psql ARGS="-c '\dt'"                                   # list tables
make psql ARGS="-c 'select source, count(*) from job_postings group by 1 order by 2 desc;'"

# Back up
docker compose --env-file .env.local exec -T postgres \
  pg_dump -U placeup -d placeup --format=custom > placeup-$(date +%F).dump

# Restore
docker compose --env-file .env.local exec -T postgres \
  pg_restore -U placeup -d placeup --clean --if-exists < placeup-2026-08-18.dump
```

### Applying new migrations after a `git pull`

```bash
git pull
make up            # rebuilds and re-runs `alembic upgrade head` automatically
```

### Reclaiming disk

```bash
make size          # what PlaceUp is using
make clean-images  # dangling images and build cache
make reset         # nuclear: every PlaceUp volume, including the database
```

---

## Testing

```bash
make up            # the suite runs inside the live API container
make test
make test ARGS="-k apply -v"
make test ARGS="tests/test_visa.py"
```

A handful of tests (`test_free_boards.py`, `test_official_portals.py`) reach out
to real job boards. They fail in network-restricted sandboxes and behind
corporate proxies; that is expected and is not a regression. Everything else runs
offline.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `permission denied while trying to connect to the Docker daemon socket` | Your user is not in the `docker` group | `sudo usermod -aG docker "$USER" && newgrp docker` |
| `Cannot connect to the Docker daemon` | Daemon not running | `sudo systemctl enable --now docker` |
| `docker: 'compose' is not a docker command` | Compose v2 plugin missing | `sudo apt-get install -y docker-compose-plugin` |
| `make doctor` reports **port 3000 in use** | Another dev server has it | `sudo ss -ltnp 'sport = :3000'`, stop that process |
| `make doctor` reports **port 5432 in use** | A host PostgreSQL is running | `sudo systemctl stop postgresql` (PlaceUp's DB is in a container) |
| Build fails on `playwright install` | Transient network, or too little disk | `make clean-images`, confirm ≥15 GiB free, re-run `make up` |
| `migrate` exits non-zero | Schema conflict from an older volume | `make reset` then `make up` — **this deletes local data** |
| `seed` exits non-zero | Reference workbook missing or unreadable | `make logs` and check `backend/H1b_US_DataLIst.xlsx` is present |
| Page loads but every request 404s | Frontend cannot reach the backend | `curl http://localhost:3000/api/health` — if that fails, `make logs-frontend` |
| API healthy, frontend never becomes healthy | Vite build failed inside the image | `docker compose --env-file .env.local logs frontend` |
| Everything times out during `make up` | Slow disk or network on the first build | Raise the budget: `PLACEUP_READY_TIMEOUT=1800 make up` |
| Scraper container crashes with Chromium errors | `/dev/shm` too small | Raise `PLACEUP_SCRAPER_SHM_SIZE=2gb` in `.env.local` |
| Ollama pull hangs | Large model on a slow link | `make logs ollama-pull`; try `OLLAMA_MODEL=qwen2.5:3b` |
| ATS model OOM-kills the host | Mistral 7B on CPU | Set `ATS_DEVICE=cuda`, or simply don't use `--ats` |
| WSL 2: `localhost:3000` refused from Windows | WSL networking not mirrored | Use `http://127.0.0.1:3000`, or set `networkingMode=mirrored` in `.wslconfig` |

Still stuck? These three, in order, answer almost everything:

```bash
make doctor      # is the host itself the problem?
make status      # which container is unhealthy?
make logs        # what did it say before it died?
```

---

## Architecture

### Local topology

```
                        ┌──────────────────────────────────────┐
   browser ──▶ :3000    │  frontend (nginx + built Vite SPA)   │
                        │  /            → static SPA           │
                        │  /api/*       → proxy to api:8080    │
                        │  /healthz     → 200 ok               │
                        └──────────────┬───────────────────────┘
                                       │ same-origin, keeps auth cookies valid
                        ┌──────────────▼───────────────────────┐
   curl    ──▶ :8000    │  api  (FastAPI, SERVER_ROLE=web)     │
                        │  public surface, CORS, rate limits,  │
                        │  security headers, audit log         │
                        └──────┬───────────────────┬───────────┘
                               │ internal only     │
                    ┌──────────▼─────────┐         │
                    │  app-server        │         │
                    │  SERVER_ROLE=app   │         │
                    │  not published     │         │
                    └──────────┬─────────┘         │
                               │                   │
      ┌────────────────┬───────┴──────┬────────────┴───────┬──────────────┐
      ▼                ▼              ▼                    ▼              ▼
 PostgreSQL 16    Firestore em.    Redis 7          tailored_documents   scheduler
 job catalogue    user store       queue/cache      private volume       (--workers)
 :5432            :8085            :6379                                 APScheduler
                                                                              │
                                                          ┌───────────────────┴────────┐
                                                          ▼                            ▼
                                                   openclaw + ollama            ats-model
                                                   (--ai)                       (--ats)
```

Two properties are worth calling out because they are what make this
production-shaped rather than a dev shim:

**The public API is not the whole backend.** `api` (`SERVER_ROLE=web`) is the only
service with a published port. `app-server` (`SERVER_ROLE=app`) holds the
privileged paths and is reachable *only* over the Compose network — the same
split the Cloud Run deployment uses, so a local run exercises the real trust
boundary rather than a collapsed one.

**The frontend and the API are same-origin.** Nginx proxies `/api/*` to the
backend rather than the browser calling port 8000 directly. This is required by
the production Content-Security-Policy and is what makes session cookies behave
identically locally and in production.

### Request lifecycle

1. Browser hits `http://localhost:3000/...` → Nginx serves the built SPA.
2. The SPA calls `/api/...` **same-origin** → Nginx proxies to `api:8080`.
3. FastAPI middleware runs: request ID, security headers, CORS, rate limit,
   request size limit, route access control, audit log.
4. Handlers read the job catalogue from PostgreSQL, user records from Firestore,
   and queue/cache state from Redis.
5. Privileged operations are forwarded to the private `app-server`.
6. Long-running work (scraping, JD repair, retention, digests, ATS scoring) never
   runs in the request path — it belongs to the `scheduler` profile, exactly as
   it belongs to Cloud Run Jobs in production.

---

## Repository layout

```
.
├── Makefile                    the one-command interface — start here
├── scripts/placeup.sh          everything `make` calls: preflight, secrets,
│                               health gating, smoke suite, diagnostics
├── compose.yaml                service definitions (shared with Windows)
├── compose.linux.yaml          Linux overlay: log rotation, init, shm, PG tuning
├── .env.local.example          configuration template (copied to .env.local)
│
├── backend/
│   ├── app/
│   │   ├── main.py             FastAPI entry point and middleware stack
│   │   ├── api/                HTTP routers (jobs, apply, match, visa, auth, …)
│   │   ├── services/           domain logic
│   │   ├── etl/                scrapers, loaders, normalizers, local seeding
│   │   ├── workers/            background jobs + the local scheduler
│   │   ├── db/                 PostgreSQL and Firestore clients
│   │   ├── middleware/         security headers, rate limits, audit logging
│   │   └── job_taxonomy*.py    the curated role/country taxonomy
│   ├── migrations/             Alembic migrations (source of truth for schema)
│   ├── openclaw_service/       résumé tailoring service (Node)
│   ├── ats_model_service/      Hugging Face ATS scoring service
│   ├── tests/                  pytest suite
│   └── deploy/                 Cloud Run deployment scripts
│
├── frontend/
│   ├── src/                    React 18 + Vite + Tailwind + Radix SPA
│   ├── nginx.conf              production Nginx (HSTS, strict CSP)
│   ├── nginx.local.conf        local Nginx (same CSP minus HTTPS upgrades)
│   └── vite.config.ts          build chunking + dev proxy to :8000
│
└── docs/
    └── freehire-analysis.md    external architecture review and adoption plan
```

---

## Production vs local

This local runtime is intentionally shaped like production, but it is **not** a
production deployment. Before anything is exposed beyond `127.0.0.1`:

- **Secrets.** `.env.local` values are per-machine development secrets. Real
  deployments load `JWT_SECRET`, `INTERNAL_API_KEY` and `SERVICE_TOKEN_SECRET`
  from Secret Manager, never from a file in the repository.
- **Auth surfaces.** Email verification, OTP MFA, billing gates and Cloudflare
  origin verification are disabled locally and **must** be on in production.
- **TLS.** Local runs plain HTTP so cookies work on `localhost`. Production
  terminates TLS at the edge and `nginx.conf` (not `nginx.local.conf`) applies
  HSTS and `upgrade-insecure-requests`.
- **OpenAPI docs.** `/docs`, `/redoc` and `/openapi.json` are served locally and
  automatically disabled when `APP_ENV=production`.
- **Live submission.** `APPLY_LIVE_SUBMIT_ENABLED=false` locally. Nothing is ever
  submitted to a real employer from a local run.
- **Data.** The local database never receives production job or user records.

Cloud Run deployment lives in `backend/deploy/`, `frontend/deploy_frontend.ps1`
and `deploy_separate_cloud_run.ps1`; the ordered release procedure is in
`MASTER_DOCUMENTATION.md`.

---

## Appendix: running without Docker

Docker is the supported path — it is what makes one command work and what keeps
local behaviour honest against production. If you must run natively, you own the
datastores yourself and several cloud-substituting services will be unavailable.

```bash
# Host dependencies
sudo apt-get install -y python3.12 python3.12-venv python3-pip \
                        postgresql-16 redis-server nodejs npm
sudo systemctl enable --now postgresql redis-server

sudo -u postgres psql -c "CREATE USER placeup WITH PASSWORD 'placeup_local_dev';"
sudo -u postgres psql -c "CREATE DATABASE placeup OWNER placeup;"

# Backend
cd backend
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m playwright install --with-deps chromium
export DATABASE_URL='postgresql+psycopg://placeup:placeup_local_dev@localhost:5432/placeup'
export APP_ENV=development DATABASE_BACKEND=postgres REDIS_URL=redis://localhost:6379/0
alembic upgrade head
python -m app.etl.local_seed
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload      # terminal 1

# Frontend
cd ../frontend
npm ci
npx vite --port 3000                                            # terminal 2
```

Caveats you are accepting: `package.json` has no `dev` script (hence `npx vite`);
the Vite dev server proxies `/api` to `http://localhost:8000` via
`VITE_PROXY_TARGET`, which is *not* the same Nginx path production uses; there is
no Firestore emulator, so user-store paths need `USER_DATABASE_BACKEND` pointed
at a real emulator you start yourself; and the `web`/`app` server split does not
exist, so the internal trust boundary is not exercised. `make up` has none of
these gaps.

---

## Documentation index

| Document | Contents |
|---|---|
| **README.md** (this file) | Running PlaceUp locally on Ubuntu, verification, operations |
| `MASTER_DOCUMENTATION.md` | Product rules, infrastructure, trust model, scraper topology, taxonomy, deployment, release log |
| `LOCAL_RUN.md` | The Windows / PowerShell local runtime |
| `docs/freehire-analysis.md` | External architecture review (strelov1/freehire) and the adoption plan for PlaceUp |
| `.github/workflows/README.md` | CI workflows |

---

## Credits and prior art

The local developer experience in this repository — the self-documenting
`make help` surface, a single `make up` that builds, migrates, seeds and *proves*
the stack is healthy before returning, run-once workers invoked identically by
the scheduler and by hand, and a source-coverage health endpoint that reports
supply mix rather than a bare `200 OK` — was shaped by a study of
**[strelov1/freehire](https://github.com/strelov1/freehire)** (MIT), an
open-source job aggregator that crawls employer ATS platforms directly.

The full review, including which of its ideas apply to PlaceUp's Python/React
stack and which deliberately do not, is in
**[docs/freehire-analysis.md](docs/freehire-analysis.md)**.

No freehire source code is used in PlaceUp. freehire is Go and SvelteKit;
PlaceUp is Python and React. What was adopted is architectural and operational
practice, which the analysis document attributes in detail.

---

<div align="center">
<sub>PlaceUp Career · proprietary · see <code>MASTER_DOCUMENTATION.md</code> for product and deployment policy</sub>
</div>

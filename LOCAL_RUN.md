# PlaceUp — complete local runtime (Windows / PowerShell)

> **On Linux, macOS or WSL 2?** Use [`README.md`](README.md) instead. There the
> whole application is a single command — `make up` — which builds, migrates,
> seeds, health-gates and smoke-verifies the stack before reporting success.
> This file documents the equivalent Windows PowerShell scripts; both drive the
> same `compose.yaml`, so the two runtimes stay in step.

This runtime replaces Google Cloud services with processes and persistent
volumes on one workstation. The existing GCP deployment scripts remain intact,
but nothing in `compose.yaml` needs a GCP project, service account, Cloud SQL,
Cloud Run, Cloud Tasks, Cloud Storage, Secret Manager, or Cloud Scheduler.

## Local architecture

| Production dependency | Local replacement |
| --- | --- |
| Cloud SQL | PostgreSQL 16 container with a persistent named volume |
| Firestore | Official Firestore emulator with a persistent data directory |
| Cloud Storage | Private filesystem volume served through the ownership-checked API |
| Cloud Tasks | In-process, idempotent application queue |
| Cloud Scheduler / Cloud Run Jobs | `app.workers.local_scheduler` container |
| Cloud Run API | Local FastAPI container on `127.0.0.1:8000` |
| Private application server | Internal-only FastAPI container on the Compose network |
| Cloud Run frontend | Local Nginx/Vite container on `127.0.0.1:3000` |
| Hosted tailoring model | OpenClaw + Ollama using `qwen2.5:7b` locally |
| GPU ATS batch VM | Optional local Hugging Face ATS-model container |
| Redis service | Local Redis 7 container with append-only persistence |

Scraping still needs normal outbound internet access to company ATS career
pages. Optional providers such as USAJobs, Adzuna, Hunter, SMTP, or Stripe are
disabled unless you intentionally add their credentials to `.env.local`.

## Prerequisite

Install and start Docker Desktop for Windows with the WSL 2 engine. Docker is
the only host-level prerequisite; PostgreSQL, Java/Firestore, Redis, Node,
Python, Playwright, Ollama, and OpenClaw run inside containers.

## Start

Core application (database, local user store, Redis, backend tiers, frontend):

```powershell
.\start_local.ps1
```

Everything, including scheduled workers, local Ollama/OpenClaw, and the large
Hugging Face ATS model:

```powershell
.\start_local.ps1 -Full
```

Profiles can also be selected independently:

```powershell
.\start_local.ps1 -WithWorkers
.\start_local.ps1 -WithAI
.\start_local.ps1 -WithWorkers -WithAI
.\start_local.ps1 -WithAtsModel
```

The first run builds the application images, migrates PostgreSQL, imports the
bundled sponsor reference data, and—when AI is enabled—downloads the Ollama
model. These downloads can take time. The website becomes available at
<http://localhost:3000>; API documentation is at
<http://localhost:8000/docs>.

The startup script creates `.env.local` with independent random local secrets.
That file is ignored by Git. Signup verification, MFA, billing gates, live ATS
submission, Cloudflare origin checks, and hosted email are deliberately off in
local mode. Email messages use the console provider.

## Workers and fresh jobs

`-WithWorkers` replaces Cloud Scheduler. It keeps the scraper, JD repair,
official-company link resolver, board discovery, liveness checker, retention,
digest, ATS scoring, and taxonomy report on local cron schedules. The cloud
32×117 fan-out is collapsed into the existing bounded global scraper process;
it uses the same 32-country and role taxonomy but respects workstation resource
limits.

Run any task immediately:

```powershell
.\run_local_job.ps1 -Name job-scraper-am
.\run_local_job.ps1 -Name jd-repair
.\run_local_job.ps1 -Name job-retention
```

The local database starts with sponsor reference data but no copied production
job or user records. Run `job-scraper-am` to populate fresh jobs. Production
data is intentionally not downloaded automatically because it contains private
user information and copying it requires an explicit migration decision.

## Local AI

`-WithAI` starts Ollama and OpenClaw, pulls `qwen2.5:7b`, and keeps the tailoring
service private except for the loopback health port `8090`. Resume and JD text
stay inside the Compose network. The backend retains its deterministic tailoring
fallback if the model is still loading or unavailable.

`-WithAtsModel` starts the separate `SlyGoblin/mistral_ATSscore_generation`
service on loopback port `8091`. Its Mistral 7B base is substantially larger:

- NVIDIA GPU: recommended; install NVIDIA Container Toolkit and add a Compose
  GPU device override, then set `ATS_DEVICE=cuda`.
- CPU: supported by the service changes, but expect a large RAM requirement and
  slow batch analysis. Set `ATS_DEVICE=cpu` and `ATS_LOAD_IN_4BIT=false`.

The normal in-app match/ATS calculations work without this optional batch model.

## Operations

```powershell
.\local_status.ps1                 # containers and health endpoints
docker compose logs -f api         # API logs
docker compose logs -f scheduler   # worker logs
.\stop_local.ps1                   # stop; preserve all data
.\stop_local.ps1 -DeleteData       # destructive reset of every local volume
```

Persistent named volumes hold PostgreSQL, Firestore emulator data, Redis,
tailored documents, Ollama weights, and Hugging Face weights. `stop_local.ps1`
preserves them unless `-DeleteData` is explicitly supplied.

## Local URLs and ports

- Website: `http://localhost:3000`
- Direct API and docs: `http://localhost:8000`, `/docs`
- PostgreSQL: `127.0.0.1:5432`
- Firestore emulator: `127.0.0.1:8085`
- Redis: `127.0.0.1:6379`
- Ollama: `127.0.0.1:11434` (AI profile)
- OpenClaw health: `http://localhost:8090/healthz` (AI profile)
- ATS model health: `http://localhost:8091/healthz` (ATS profile)

Every published port binds only to `127.0.0.1`; the stack is not exposed to the
LAN or public internet. Use a separate, authenticated reverse proxy if remote
access is ever required.

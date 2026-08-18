# =============================================================================
# PlaceUp — one command to run the whole application locally on Ubuntu.
#
#     make up            frontend + backend + datastores, built, migrated,
#                        seeded, health-gated and smoke-verified
#     make up-full       everything above plus schedulers and the local models
#     make help          every target with a one-line description
#
# All logic lives in scripts/placeup.sh; this file is the friendly surface.
# Requires: GNU make, Docker Engine + Compose v2. `make doctor` checks the rest.
# =============================================================================

SHELL := /usr/bin/env bash
.SHELLFLAGS := -eu -o pipefail -c
.DEFAULT_GOAL := help

# Invoked through `bash` on purpose: the executable bit does not survive a
# checkout from a Windows working tree, and this makes that irrelevant.
PLACEUP := bash ./scripts/placeup.sh

# `make up PROFILES=workers,ai` is equivalent to `make up-workers up-ai`.
PROFILES ?=
export PROFILES

# `make job NAME=job-scraper-am`
NAME ?=

# Extra args forwarded to `make test` / `make psql`, e.g. `make test ARGS="-k apply"`
ARGS ?=

.PHONY: help up up-full up-workers up-ai up-ats up-fast down stop restart reset \
        status ps health logs logs-api logs-frontend logs-scheduler smoke doctor \
        jobs job test lint build pull shell shell-frontend psql redis urls \
        env clean-images size

# -----------------------------------------------------------------------------
# Help
# -----------------------------------------------------------------------------
help: ## Show every available command
	@printf '\n\033[1mPlaceUp — local runtime\033[0m\n\n'
	@printf '  \033[36m%-18s\033[0m %s\n' "make up" "START HERE — run the complete application (frontend + backend)"
	@printf '\n\033[1mAll targets\033[0m\n'
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'
	@printf '\n\033[2m  App: http://localhost:3000   API docs: http://localhost:8000/docs\033[0m\n\n'

# -----------------------------------------------------------------------------
# Lifecycle
# -----------------------------------------------------------------------------
up: ## Run the complete application locally (the only command you need)
	@$(PLACEUP) up

up-full: ## Run everything: app + schedulers + local Ollama/OpenClaw + ATS model
	@$(PLACEUP) up --full

up-workers: ## App + the background worker scheduler (fresh jobs, digests, retention)
	@$(PLACEUP) up --workers

up-ai: ## App + local Ollama/OpenClaw resume-tailoring model
	@$(PLACEUP) up --ai

up-ats: ## App + the heavyweight local ATS scoring model (needs a GPU or lots of RAM)
	@$(PLACEUP) up --ats

up-fast: ## Start without rebuilding images (use after the first successful `make up`)
	@$(PLACEUP) up --no-build

down: ## Stop every container; all data volumes are preserved
	@$(PLACEUP) down

stop: down ## Alias for `make down`

restart: ## Restart the stack without rebuilding
	@$(PLACEUP) down
	@$(PLACEUP) up --no-build

reset: ## DESTRUCTIVE — stop and delete every local volume (database, models, files)
	@$(PLACEUP) reset

# -----------------------------------------------------------------------------
# Inspection
# -----------------------------------------------------------------------------
status: ## Container state, HTTP health probes and volume disk usage
	@$(PLACEUP) status

ps: status ## Alias for `make status`

health: ## Re-run the smoke verification suite against a running stack
	@$(PLACEUP) smoke

smoke: health ## Alias for `make health`

doctor: ## Check host prerequisites (Docker, RAM, disk, free ports) and stop
	@$(PLACEUP) doctor

urls: ## Print every local URL and port
	@$(PLACEUP) urls

size: ## Show how much disk the PlaceUp images and volumes are using
	@docker system df -v | grep -E 'TYPE|VOLUME NAME|placeup' || true

# -----------------------------------------------------------------------------
# Logs
# -----------------------------------------------------------------------------
logs: ## Follow logs from every container
	@$(PLACEUP) logs

logs-api: ## Follow backend API logs only
	@$(PLACEUP) logs api

logs-frontend: ## Follow frontend (nginx) logs only
	@$(PLACEUP) logs frontend

logs-scheduler: ## Follow background worker logs only
	@$(PLACEUP) logs scheduler

# -----------------------------------------------------------------------------
# Background workers
# -----------------------------------------------------------------------------
jobs: ## List every background job and its local cron schedule
	@$(PLACEUP) jobs

job: ## Run one background job now, e.g. `make job NAME=job-scraper-am`
	@test -n "$(NAME)" || { echo "usage: make job NAME=<job>   (see 'make jobs')" >&2; exit 2; }
	@$(PLACEUP) job $(NAME)

# -----------------------------------------------------------------------------
# Development
# -----------------------------------------------------------------------------
test: ## Run the backend test suite inside the running api container
	@$(PLACEUP) test $(ARGS)

build: ## Rebuild the backend and frontend images without starting anything
	@$(PLACEUP) doctor
	@docker compose --env-file .env.local -f compose.yaml -f compose.linux.yaml build api frontend

pull: ## Pull the third-party base images ahead of the first build
	@docker compose --env-file .env.local.example -f compose.yaml pull postgres firestore redis || true

shell: ## Open a shell inside the backend API container
	@$(PLACEUP) shell api

shell-frontend: ## Open a shell inside the frontend container
	@$(PLACEUP) shell frontend

psql: ## Open psql against the local PostgreSQL database
	@$(PLACEUP) psql $(ARGS)

redis: ## Open redis-cli against the local Redis
	@docker compose --env-file .env.local -f compose.yaml exec redis redis-cli

env: ## Create .env.local from .env.local.example with fresh random secrets
	@$(PLACEUP) env

clean-images: ## Remove dangling Docker images and build cache to reclaim disk
	@docker image prune -f
	@docker builder prune -f

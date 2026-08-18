# freehire → PlaceUp: architecture review and adoption plan

**Subject:** [`strelov1/freehire`](https://github.com/strelov1/freehire) — MIT-licensed,
open-source job aggregator (Go + SvelteKit).
**Reviewed:** 18 August 2026, against the repository's default branch.
**For:** PlaceUp Career (Python/FastAPI + React/Vite, private).

This document exists so that PlaceUp can borrow freehire's *engineering
decisions* without borrowing its stack. No freehire source code is present in
PlaceUp, and none should be: the two systems share a problem domain and share
almost nothing else technically. What transfers is the reasoning.

---

## Contents

- [1. Executive summary](#1-executive-summary)
- [2. What freehire actually is](#2-what-freehire-actually-is)
- [3. Side-by-side](#3-side-by-side)
- [4. Where PlaceUp is already ahead](#4-where-placeup-is-already-ahead)
- [5. Adopted in this change](#5-adopted-in-this-change)
- [6. Recommended next — ranked](#6-recommended-next--ranked)
- [7. Deliberately not adopted](#7-deliberately-not-adopted)
- [8. Licensing and attribution](#8-licensing-and-attribution)
- [9. Reading list](#9-reading-list)

---

## 1. Executive summary

freehire solves the same first half of the problem PlaceUp solves — get every
real job posting out of employers' applicant-tracking systems, normalize it, and
make it searchable — and has done so at a scale worth learning from: it reports
roughly **3.3M open postings from 294,000 companies across 225 live sources, 92
of them multi-tenant ATS platforms**.

Its architecture is unusual in one specific, transferable way: **the HTTP server
does nothing but serve HTTP.** Every crawl, every LLM call that is not
request-time, every index rebuild is a *run-once-and-exit* process started by
cron. There is no queue daemon and no long-lived background runtime, so all
coordination happens in PostgreSQL — which is why the write paths are built
around **transactional outboxes**: a row queued in the same transaction as the
write that caused it, drained later by whichever worker owns that queue.

PlaceUp already shares the shape of this (Cloud Run Jobs, `app/workers/*`,
`local_scheduler`). The five ideas genuinely worth importing are, in order:

1. **Sources as data, not code** — one YAML file per ATS provider, validated
   against the adapter registry *before any network request*.
2. **Transactional outboxes** — replace `SELECT … LIMIT n` table scans in the
   workers with queues written at upsert time.
3. **The cheap re-crawl path** — an unchanged posting must not re-trigger
   enrichment, re-indexing or re-scoring. This is freehire's single biggest
   scaling lesson and it is measured, not theoretical.
4. **One wire shape per entity** — a single serializer used by the list
   endpoint, the detail endpoint and any index, so those surfaces cannot drift.
5. **Generated frontend contracts** — a new enum value in the backend that the
   SPA does not handle should be a type error, not a blank cell that ships green.

The developer-experience and operations patterns (a self-documenting `make`
surface, one command that builds *and proves health*, graceful degradation for
every optional dependency) were adopted immediately and are live in this
repository — see [§5](#5-adopted-in-this-change).

---

## 2. What freehire actually is

### Stack

| Layer | freehire |
|---|---|
| HTTP server | Go + [Fiber v2](https://gofiber.io/), single binary (`cmd/server`) |
| Database | PostgreSQL + [pgvector](https://github.com/pgvector/pgvector) |
| DB access | [sqlc](https://sqlc.dev/) — type-safe Go generated from hand-written SQL, **no ORM** |
| Search | [Meilisearch](https://www.meilisearch.com/) — one `jobs` index, keyword + facets |
| LLM | [langchaingo](https://github.com/tmc/langchaingo) over any OpenAI-compatible endpoint; no vendor baked in |
| Frontend | SvelteKit 2 (Svelte 5 runes) + Tailwind 4, `adapter-node`, server-rendered |
| Cache / limits | Redis · S3-compatible object storage (MinIO locally) |
| Local dev | Docker Compose + a `make` surface |
| Licence | MIT |

### Process model

Roughly **60 entry points under `cmd/`**. Exactly two are daemons — `cmd/server`
and `cmd/mail-ingest`. Everything else takes `DATABASE_URL`, does one pass, exits
non-zero on failure, and is scheduled by systemd timers with `Type=oneshot`
(which is also what prevents a worker stacking on itself — there is no lock
file).

The pipeline: `cmd/ingest <board-file>` → `pipeline.Runner` (fetch → normalize →
dedup → upsert) → outbox rows → `cmd/enrich`, `cmd/search-drain`, `cmd/embed`,
`cmd/capture-apply-form` drain them → Meilisearch and pgvector.

### The decisions worth writing down

- **Dedup is a database constraint,** `jobs UNIQUE (source, external_id)`, so
  re-running a crawl is free rather than merely idempotent-by-convention.
- **Failing boards back off on a recorded cooldown** instead of being retried at
  full rate every run.
- **An unchanged re-crawl takes a cheap path** that only refreshes a "last seen"
  timestamp. Nothing downstream fires. Without this the entire catalogue is
  re-enriched and re-indexed every few hours.
- **Search writes are batched through an outbox** for a measured reason:
  Meilisearch re-merges its inverted index across the *whole* live index on every
  push regardless of batch size — 90–180 seconds per push on a ~2.7M-document
  index. ~169 independent per-board processes each pushing directly saturated
  host disk IO; the outbox collapses many small pushes into few fat ones.
- **`cmd/reindex` rebuilds and swaps atomically,** so live reads are never
  affected by a rebuild.
- **The search index stores the complete public wire shape of a job,** not a
  pointer to one, so a search response needs no database round trip to render.
- **`internal/jobview` owns the single JSON representation** used by the list
  endpoint, the detail endpoint and the index alike.
- **Response envelope is uniform:** `{"data": …}`, `{"data": …, "meta": {…}}`,
  `{"error": msg}`. The catalogue read API is public and keyless.
- **`sources/` is data.** One YAML file per provider, one line per company.
  Retiring a board *moves* the line to `sources/retired/` — never deletes it —
  because ingest takes one file by path, so retirement is expressed by location
  and a mistake is undone by moving the line back.
- **`cmd/gen-contracts` generates the SPA's TypeScript types** from the Go wire
  structs and the closed vocabularies (source names, application stages,
  enrichment facets).
- **Facet dictionaries are curated and never guess.** `internal/location`,
  `internal/classify`, `internal/skilltag` emit nothing rather than emit a guess.
- **Every optional dependency degrades gracefully.** Unset `LLM_*`, `S3_*`,
  `MEILI_MASTER_KEY`, `PII_FILTER_URL` or an OAuth provider's credentials and the
  feature it gates simply turns off — no crash, no half-broken surface.
- **A separate PII-span-detection service** (`services/pii-filter`, Python) sits
  in front of résumé structuring and import.
- **Docs are split into map and territory:** `docs/architecture.md` is the map;
  per-package `AGENTS.md` files carry the invariants and the traps.
- **The design system is a separate package** with design tokens, Storybook, and
  *ratchet* scripts (`check-adoption.mjs`, `check-token-coverage.mjs`,
  `ratchet.mjs` + committed baselines) that fail CI when hardcoded values
  increase.
- **Outgoing emails are rendered to committed static previews** (`make
  mail-preview`) and a test asserts the previews still match the templates.

---

## 3. Side-by-side

| Dimension | freehire | PlaceUp |
|---|---|---|
| Language | Go | Python 3.12 |
| HTTP | Fiber v2, one binary | FastAPI, split `web` + private `app` server |
| DB access | sqlc, no ORM | SQLAlchemy Core / psycopg + Alembic |
| Catalogue store | PostgreSQL (+pgvector) | PostgreSQL (Cloud SQL) |
| User store | PostgreSQL | Firestore |
| Search | Meilisearch, faceted | SQL filters over PostgreSQL |
| Frontend | SvelteKit 2, SSR | React 18 + Vite SPA behind Nginx |
| Background work | ~60 run-once `cmd/` binaries, systemd timers | 13 `app/workers` modules, Cloud Run Jobs / APScheduler |
| Queueing | Transactional outbox tables | In-process app queue + Cloud Tasks |
| Source registry | YAML per provider, `retired/` convention | Python constants + adapter modules |
| Sponsorship data | — | H-1B / visa sponsor knowledge base |
| Résumé tailoring | CV builder, ATS-safe PDF, deterministic scoring | OpenClaw + Ollama, deterministic fallback |
| Application submission | Form capture + browser extension fill | One-click submission (Elite gate) |
| Business model | Open source, hosted free | Commercial SaaS, tiered |
| Licence | MIT | Proprietary |

---

## 4. Where PlaceUp is already ahead

Worth stating plainly, because a review that only lists gaps is misleading.

- **A real trust boundary.** PlaceUp splits the public `web` server from a
  private `app` server that is unreachable from outside the network, and the
  local Compose stack reproduces that split rather than collapsing it. freehire
  is a single binary.
- **Supply observability.** `GET /api/health/ats-coverage` reports the first-party
  ATS vs aggregator mix over a rolling window with a configurable minimum share,
  and returns `degraded` when direct-ATS supply thins out. That is a better
  health signal than a `200 OK`, and freehire has no equivalent.
- **Sponsorship as a first-class dimension.** The H-1B/visa sponsor knowledge base
  and `visa_label_backfill` are the product differentiator; freehire does not
  model sponsorship at all.
- **Submission, not just discovery.** One-click apply with a gated live-submit
  flag, an apply queue and per-user document storage.
- **Retention discipline.** A dedicated 60-day retention worker plus a
  non-taxonomy purge, with the visibility window derived from the same constant
  (`VISIBLE_RETENTION_DAYS`).
- **Layered request middleware.** Request ID, structured JSON access logging,
  security headers, rate limiting, request-size limits, route access control and
  audit logging, with OpenAPI docs automatically disabled in production.

---

## 5. Adopted in this change

Everything in this section is live in the repository now.

| Borrowed | freehire origin | PlaceUp implementation |
|---|---|---|
| Self-documenting `make help` | `Makefile` `grep`/`awk` help target | `Makefile` — every target carries a `##` description |
| Container-engine fallback | `DOCKER ?= docker \|\| podman` | `detect_docker()` in `scripts/placeup.sh` |
| One command brings up everything | `make up` | `make up` — build, migrate, seed, health-gate, verify |
| Optional heavy dependencies are opt-in | Compose profiles / unset env disables a feature | `--workers`, `--ai`, `--ats` profiles; every optional provider key empty by default |
| Run-once workers invoked identically by cron and by hand | `go run ./cmd/<worker>` | `make job NAME=<job>` runs exactly what the scheduler runs |
| A documented port override for conflicts | `HIRE_HOST_PORT=8090 make up` | `make doctor` names the conflicting port and prints the `ss -ltnp` command to find its owner |
| Docs split into map and territory | `docs/architecture.md` + per-package `AGENTS.md` | `README.md` (the map) + `MASTER_DOCUMENTATION.md` (the territory) |
| Graceful degradation as the default | unset `LLM_*`/`S3_*`/`MEILI_*` disables cleanly | AI profiles off by default; deterministic tailoring and scoring fallbacks stay in the request path |

Two things were added that freehire does *not* do, because a
build-and-hope `up` is the most common way a "working" stack lies to you:

- **`make up` will not report success until it has proved health over HTTP** —
  including a request through the frontend's `/api/*` proxy to the backend, which
  is what catches the "page loads, nothing works" class of failure.
- **`make doctor`** runs the host preflight (daemon reachable, RAM, disk, port
  ownership) *before* a 15-minute image build, and prints the exact fix command
  for anything it finds.

Supporting files: `Makefile`, `scripts/placeup.sh`, `compose.linux.yaml`,
`README.md`.

---

## 6. Recommended next — ranked

Effort is engineer-days. Nothing here is required for the local runtime to work.

### P1 — high value, contained

**1. Move the board registry into YAML data.** *(3–5 d)*
Today a company or board lives in Python (`app/scrape_constants.py` and the
adapter modules). Move it to `backend/sources/<provider>.yml`, one entry per
company, with a `backend/sources/retired/` directory and the **move-don't-delete**
rule. Validate every entry against the adapter registry at process start, before
any HTTP request goes out.
*Why:* adding a company becomes a reviewable one-line data diff instead of a code
change; a typo fails in under a second instead of mid-crawl; and the retirement
history stays in the tree.

**2. Transactional outboxes for post-upsert work.** *(5–8 d)*
`jd-repair`, `company-link-resolver`, `ats-worker` and `job-liveness` currently
scan with `LIMIT`. Add `job_enrichment_outbox` and `job_scoring_outbox` rows
written *in the same transaction* as the posting upsert, and have each worker
claim-and-drain its own queue.
*Why:* bounded, restartable, exactly-once-ish work; no repeated full-table scans;
a worker that dies mid-batch resumes instead of re-deriving where it was.

**3. The cheap re-crawl path.** *(2–3 d, highest ratio on this list)*
Store a content hash over the normalized title + description + location +
salary. On re-crawl, if the hash is unchanged, update `last_seen_at` **only** and
queue nothing.
*Why:* freehire's most expensive lesson. Without it, every downstream consumer —
enrichment, scoring, indexing — re-does the whole catalogue on every crawl cycle.

**4. One wire shape per entity.** *(3–4 d)*
A single Pydantic response model for a job posting, used by the list endpoint,
the detail endpoint, the dashboard feed and any export. freehire's
`internal/jobview` exists precisely so those surfaces cannot drift.
*Why:* the July 2026 overhaul had to reconcile exactly this kind of drift between
the dashboard and the jobs page. A shared model makes that class of bug
unrepresentable.

**5. Generated TypeScript contracts.** *(1–2 d)*
FastAPI already emits `/openapi.json`. Run `openapi-typescript` in CI, commit
`frontend/src/lib/generated/api.ts`, and export closed vocabularies (source
names, apply stages, visa labels, role taxonomy keys) as TS unions. Fail CI when
the committed file differs from a fresh generation.
*Why:* a backend enum the SPA does not handle becomes a compile error instead of
a blank cell in production.

**6. Uniform response envelope.** *(2–3 d, coordinate with the SPA)*
`{"data": …}` / `{"data": …, "meta": {…}}` / `{"error": …}` across every route.
*Why:* one error-handling path in the client instead of per-endpoint shapes;
pagination metadata stops being reinvented per route.

### P2 — worthwhile, larger

**7. Surface the posting-reality signal to users.** *(3–5 d)*
`job_liveness_checker` already knows which postings are probably dead. freehire
turns the same signal into a user-visible "is this job real?" indicator rather
than using it only to purge.
*Why:* it is the highest-trust feature in a job product, and PlaceUp already
computes the input.

**8. A PII filter in front of every model call.** *(5–8 d)*
freehire runs `services/pii-filter` — a separate span-detection service, disabled
cleanly when unconfigured — ahead of résumé structuring. PlaceUp sends résumé and
JD text to OpenClaw/Ollama.
*Why:* directly relevant to `PlaceUp_Legal_Compliance_Checklist.docx`, and the
degrade-when-unset pattern means it can ship dark and be enabled per environment.

**9. Rendered email previews under test.** *(2–3 d)*
Render every outgoing template (digest, password reset, verification, alerts) to
committed static HTML via a `make mail-preview` target, and assert in a test that
the previews still match.
*Why:* email is the one surface nobody looks at until a customer does.

**10. Design-token ratchet in CI.** *(2–3 d)*
PlaceUp ships `default_shadcn_theme.css` with Radix/shadcn components. Add a
script that counts hardcoded colour/spacing literals in `frontend/src`, commit a
baseline, and fail CI when the count rises.
*Why:* cheap, mechanical, and it stops design drift without a redesign project.

**11. Faceted search.** *(10–20 d — do not start without a decision)*
freehire uses Meilisearch and stores the complete wire shape in the index.
PlaceUp filters in SQL. Before adopting anything, note freehire's *other* lesson:
they **removed** their semantic index once its only two consumers stopped needing
a live one. PostgreSQL full-text + `pg_trgm` is very likely the correct next step
for PlaceUp, not a second datastore.

### P3 — evaluate, do not assume

**12. Per-directory `AGENTS.md` invariants.** *(ongoing)*
PlaceUp has `.agents/` and `.claude/`. freehire's convention is one file per
substantial package stating what is *always true* about it, indexed from a root
`AGENTS.md`. Cheap to start, compounds.

---

## 7. Deliberately not adopted

| freehire practice | Why not for PlaceUp |
|---|---|
| Go + Fiber + sqlc | A rewrite with no product benefit. PlaceUp's scraping, PDF and ML ecosystem is Python-native (jobspy, scrapegraphai, Playwright, transformers). |
| Public keyless catalogue API | PlaceUp's catalogue *is* the product. A keyless read API contradicts the tiered commercial model. |
| Open-sourcing the pipeline | Same reason. The source registry could be opened later without opening the platform. |
| pgvector semantic search | freehire built it and then removed the live index. Do not add it without a named consumer. |
| Meilisearch as a hard dependency | Adds a second stateful service to operate and back up. Exhaust PostgreSQL FTS + `pg_trgm` first. |
| Telegram channel ingestion | Wrong supply channel for US-sponsorship-focused demand. |
| Browser extension | Real value, but it is a product decision with its own review and store-listing cost — not an architecture borrow. |
| Storybook + a separate design-system package | The token ratchet (P2 #10) captures most of the benefit at a fraction of the cost. |

---

## 8. Licensing and attribution

freehire is **MIT licensed**. MIT permits reuse of source with attribution and
the licence text retained.

**PlaceUp copies no freehire source code.** What this document transfers is
architectural and operational practice — ideas, which are not copyrightable — and
it attributes them explicitly. The `README.md` carries a
[Credits and prior art](../README.md#credits-and-prior-art) section naming the
project and linking to it.

If freehire source is ever adapted into PlaceUp — an adapter, a dictionary, a
script — then at that moment:

1. Add `THIRD_PARTY_NOTICES.md` at the repository root containing freehire's full
   MIT licence text and copyright line.
2. Note the origin, the commit SHA, and the modifications in the header of every
   adapted file.
3. Record it in `MASTER_DOCUMENTATION.md` under a third-party dependencies
   section.

Nothing in the current change requires step 1.

---

## 9. Reading list

The files worth reading in `strelov1/freehire`, in the order that makes them make
sense:

| Path | Why |
|---|---|
| `README.md` | Scope, stack, source breakdown, the quick-start surface |
| `docs/architecture.md` | The crawl-to-search topology and the three main flows |
| `Makefile` | The DX surface adopted in §5 |
| `docker-compose.yml` | Optional-dependency wiring and the `minio-init` completed-successfully pattern |
| `.env.example` | How to document configuration so unset means "cleanly off" |
| `internal/pipeline/AGENTS.md` | fetch → normalize → dedup → upsert, and the cooldown rule |
| `internal/sources/AGENTS.md` | The adapter registry and how a source's kind is a property of its type |
| `internal/searchdrain/AGENTS.md` | The outbox batching rationale, with the measured numbers |
| `internal/jobview/AGENTS.md` | One wire shape, and why |
| `sources/*.yml` + `sources/retired/` | Sources as data, and the move-don't-delete rule |
| `services/pii-filter/` | A degradeable sidecar service, done small |
| `design-system/scripts/ratchet.mjs` | The baseline-ratchet idea behind P2 #10 |
| `CONTRIBUTING.md` | The checks CI runs |

---

<sub>Reviewed for PlaceUp Career, 18 August 2026. freehire facts in §2 are as stated by
that repository's own documentation at review time; catalogue counts change
continuously.</sub>

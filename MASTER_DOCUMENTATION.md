# PlaceUp Career Master Documentation

> Local-only deployment is now supported. See `LOCAL_RUN.md` and
> `compose.yaml` for the cloud-free PostgreSQL + Firestore emulator + local
> workers + Ollama/OpenClaw topology. Existing GCP deployment instructions are
> retained only for teams that deliberately choose the hosted topology.

Last updated: 2026-07-14

This is the single source of truth for PlaceUp Career. Keep this file current
and avoid adding scattered markdown files unless the team explicitly decides to
split documentation again.

## Product

PlaceUp Career is a dark-mode-first career platform for global candidates who
need accurate job matching, ATS resume scoring, visa sponsorship signals, and
clean job descriptions from first-party or official sources.

Core user flows:

- Visitor lands on `placeupcareer.com`.
- Signup collects account credentials, legal acceptance, target roles/country,
  visa/work-authorization status, common ATS application questions, plan choice,
  email verification, and a required resume upload.
- Verified users sign in and use the dashboard.
- Users upload resumes, set target roles/countries/visa needs, and browse jobs.
- Jobs are labeled by country, visa route, sponsor signal, English friendliness,
  role taxonomy, description quality, and ATS/resume match.
- Application support uses the saved profile to prepare tailored resumes, cover
  letters, application packets, and status tracking. Submission automation must
  stay behind explicit user authorization and platform-compliance controls.
- The Automated Application System (see that section) prepares and — after a
  mandatory human review — submits applications through legitimate ATS APIs
  where they exist and server-side headless-browser automation only where they
  don't. Every application passes a non-optional review-before-submit gate, and
  the system never solves CAPTCHAs or bypasses security controls; it hands off
  to the user instead.

## Infrastructure

Production stays on Google Cloud and Firebase.

- Client server: Firebase Hosting / frontend Cloud Run as applicable.
- User server/data: Firebase Auth-style app session layer plus Firestore user
  store in project `placeup-firebase-641222668282`.
- Web server: Cloud Run service `placeup-api` in project `steel-shine-492401-u6`.
- Application server: internal Cloud Run service `placeup-app`.
- Jobs database: Cloud SQL PostgreSQL instance `placeup-backend`.
- Secrets: Google Secret Manager.
- Scheduled work: Cloud Run Jobs plus Cloud Scheduler.
- Static frontend domain: `https://placeupcareer.com`.
- Apply submission queue: Cloud Tasks, one queue per ATS (`apply-{ats_type}`),
  paced per-platform (Workday throttled far slower than Greenhouse).
- Browser automation: Playwright on Cloud Run Jobs (batch) / a Cloud Run
  service (interactive handoff), with a managed-browser fallback (Steel.dev /
  Browserbase) once concurrency exceeds what Cloud Run handles.
- Dedicated inbox: AWS SES inbound (MX on `mail.placeupcareer.com`) → S3 →
  Lambda → FastAPI webhook. This is the one intentional cross-cloud dependency;
  it is chosen over Gmail restricted-scope OAuth (see the Automated Application
  System section for the rationale).

Do not use Supabase for production infrastructure.

## Trust Model

The public web server and internal application server are separate.

Request path:

1. Client/UI calls the web server.
2. Web server verifies the user JWT/session and route permissions.
3. Web server calls the application server only through
   `app.services.internal_client`.
4. The internal client sends:
   - a Google-signed ID token for Cloud Run IAM, and
   - a short-lived `X-Service-Token` minted by `zero_trust.create_service_token`.
5. The app server runs with `SERVER_ROLE=app`; `ServiceOnlyGateMiddleware`
   refuses every non-health request without a valid service token.

Important files:

- `backend/app/zero_trust.py`
- `backend/app/middleware/security.py`
- `backend/app/services/internal_client.py`
- `backend/deploy/deploy_app_server.ps1`

Required app-server secrets:

- `DATABASE_URL`
- `JWT_SECRET`
- `SERVICE_TOKEN_SECRET`

If a secret is pasted in chat, terminal logs, screenshots, or documentation,
rotate it immediately.

## Country Scraper Topology

The platform targets 32 destination countries:

`US, CA, GB, IE, DE, NL, AU, NZ, SG, AE, JP, PT, FR, ES, SE, DK, NO, CH, FI, BE, AT, PL, EE, QA, SA, IT, LU, KR, TW, HK, CZ, IN`

Country rules live in:

- `backend/app/services/global_visa_rules.py`

The global scraper can run all countries, or one isolated country:

- all countries: omit `SCRAPER_TARGET_COUNTRIES`
- one country: `SCRAPER_TARGET_COUNTRIES=DE`
- several countries: `SCRAPER_TARGET_COUNTRIES=DE,NL,GB`

Deploy per-country scraper jobs:

```powershell
.\backend\deploy\deploy_country_scrapers.ps1 `
  -ProjectId steel-shine-492401-u6 `
  -Region us-east1 `
  -DbInstance placeup-backend `
  -CreateSchedulers
```

Each country job uses the same backend image but scopes its run to one country.
Jobs are named like `placeup-country-scraper-us`. Every country job contains
117 Cloud Run tasks (`--tasks 117`). Those tasks shard every unique taxonomy
title across 117 role pipelines, producing a deterministic 32 x 117 = 3,744
country/role coverage matrix on every scheduled cycle. If the taxonomy grows
beyond 117 titles, a pipeline owns two or more titles; no title is dropped.

The collection request path is deliberately separated:

1. Client and web application request the newest positions from `placeup-api`.
2. The application server reads only active, complete-JD records posted or
   first discovered during the rolling last 24 hours.
3. Thirty-two isolated country jobs run the 117 role-pipeline matrix against
   the source connectors.
4. Normalization, completeness quarantine, deduplication, and the locked master
   publisher prepare the serving inventory.
5. The Jobs page requests 40 results per page and renders numbered pagination
   at the bottom until the matching 24-hour inventory is exhausted.

## Job Collection Rules

Allowed collection sources:

- official company ATS boards
- official country job portals
- free public JSON/RSS job feeds
- first-party career pages and structured job detail pages

Avoid:

- fake jobs
- placeholder records
- job search/category pages masquerading as postings
- duplicate aggregator rows when a first-party job is available
- roles with explicit no-sponsorship, citizenship-only, or clearance-only text
  in visa-friendly feeds

Primary ATS/career systems currently supported:

- Greenhouse
- Workday
- Lever
- Ashby
- Rippling
- iCIMS
- BambooHR
- Workable
- JazzHR
- Jobvite
- BreezyHR
- Oracle Recruiting / Oracle Cloud HCM / Taleo
- Paylocity
- SmartRecruiters
- UltiPro / UKG
- Zoho Recruit
- ADP
- Dover
- Gem
- SAP SuccessFactors
- Recruitee
- Pinpoint
- Personio
- Teamtailor
- Polymer
- Phenom
- Dayforce
- JOIN
- Hireology
- Eightfold discovery through career page ingestion
- Similar official employer career pages through the career-site feed and
  first-party page discovery

As of 2026-07-10 every platform above has a direct scraper in
`backend/app/services/careers_ats.py` (29 providers in `ATS_DISPATCH`).
Coverage works in three layers that all feed the same normalize → stage →
load pipeline and the 32-target-country prefilter:

1. Curated seed catalog — `h1b_sponsor_boards.H1B_SPONSOR_BOARDS` maps known
   sponsor companies to their board tokens. Token formats per platform are
   documented at the top of `careers_ats.py` (Workday uses `(tenant, site)`,
   Oracle Recruiting uses `(host, siteNumber)` or `"host|CX_1"`, UKG uses the
   board path, ADP/Paylocity use GUIDs, SuccessFactors/Phenom use the careers
   domain, everything else uses the company slug).
2. Slug probing — `company_career_resolver.PROBE_ATS` guesses boards for every
   sponsor company in `visa_sponsors`/`h1b_sponsors` (22 slug-guessable
   platforms probed; run by `board_discovery_sweep`).
3. Careers-page ingest — detects embedded/unknown ATS from the company's own
   careers URL.

Scoring validation (2026-07-10): match and ATS scores now validate inputs
(empty/short resume or JD returns flagged low scores instead of noise), clamp
every component to 0-100, calibrate TF-IDF similarity, and cross-check that
80+ scores are backed by real skill evidence. See
`backend/app/services/match_engine.py` and `backend/app/services/ats_scorer.py`.

Resume Tailor (2026-07-10): unlocked by default. `TAILOR_FEATURE_ENABLED=false`
in the service env re-locks it without a deploy.

Feed ranking (2026-07-10): first-party ATS/career-page sources
(`app/scrape_constants.FIRST_PARTY_ATS_SOURCES`) rank ahead of aggregator
copies (LinkedIn/Indeed/Dice) inside every relevance tier + date bucket, and
the DB pool query tops up with the freshest first-party rows so aggregator
volume can never push direct postings out of the 2500-row pool
(`app/db/postgres.py get_jobs`). "Recent" sort is day-bucketed with
first-party priority within the day.

Job dates render in the user's targeted-country convention (country filter
first, else first saved target location) — `COUNTRY_LOCALES` in
`frontend/src/app/components/dashboard/JobsPage.tsx`.

Sign-in resilience (2026-07-10): Firestore user lookups retry transient
errors (RESOURCE_EXHAUSTED "Rate exceeded.", unavailable, deadline) with
backoff, and the frontend API client maps raw 429/5xx upstream bodies to
friendly messages instead of leaking them.

Direct-source policy (2026-07-10 pm): the Jobs feed serves ATS/company-page
postings only; aggregator copies (`scrape_constants.AGGREGATOR_SOURCES`:
LinkedIn/Indeed/Dice/...) backfill only when the direct pool can't fill a
page. `JOBS_FEED_INCLUDE_AGGREGATORS=true` restores blending. Ranking is
relevance-first (Jobright-style): target-role tier, then match score +
freshness bonus + first-party bonus (`_projection_sort_key`).

Scraper schedule + alerting (2026-07-11): the job scraper runs twice daily
at 11:00 and 20:00 America/New_York (`deploy/schedule_jobs.ps1` —
placeup-job-scraper-am/-pm; retire the old placeup-job-scraper-6h trigger).
Failures and partial runs email SCRAPER_ALERT_EMAIL (default
operations@placeupcareer.com) via `_alert_ops` in
`app/etl/jobs_scraper_6h.py`. Requires SMTP settings on the Cloud Run job.

ATS coverage additions (2026-07-11): Freshteam, Jobylon, Comeet, Homerun,
CATS (catsone), and an Eightfold alias (same /api/apply/v2/jobs pattern as
Phenom) — 36 dispatch keys in careers_ats.ATS_DISPATCH, wired into
first-party sources, slug probes, and tier1 providers.

Direct-ATS collection guarantee (2026-07-14): the 6h scraper's
`DIRECT_ATS_CONNECTOR_SOURCES` now includes the free, no-auth first-party ATS
APIs (`greenhouse`, `lever`, `ashby`, `smartrecruiters`) alongside
`career_site_feed`/`remoteok`/`remotive`/`jobicy`. Every scheduled run now pulls
real ATS-portal jobs directly from the H-1B sponsor board registry — no longer
dependent on `APIFY_TOKEN` or the separate `placeup-board-discovery-sweep` job —
so the direct-ATS inventory that feeds One-Click Apply refreshes even when the
separate board sweep is delayed. Override with
`API_CONNECTOR_SOURCES`. The per-country matrix jobs now also run this direct-ATS
pass — once per country, on the first role shard (`CLOUD_RUN_TASK_INDEX=0`) — so
all 32 countries get real ATS-portal coverage without fetching every board on all
117 shards. Whole-board results are filtered before persistence, so one country
task cannot load another country's rows. Toggle with
`SCRAPER_MATRIX_DIRECT_ATS_ENABLED` (default true).

ATS coverage health check (2026-07-14): `GET /api/health/ats-coverage?hours=24`
reports the live supply mix — first-party ATS boards vs aggregators
(LinkedIn/Indeed/Dice) — with per-source complete-JD counts, percentages,
`first_party_share`, and a `direct_ats_healthy` flag. Health requires a non-zero
direct count and `ATS_COVERAGE_MIN_FIRST_PARTY_SHARE` (default 5%). Use it to confirm the scraper is actually
landing ATS-portal jobs and to watch One-Click Apply supply. Backed by
`PostgresClient.source_coverage_sync` (honest posting window, never last_seen_at).

Apply tailoring completion (2026-07-14): (1) the duplicate cover-letter
implementation is consolidated into one Groq path with true-facts-only numeric
grounding checks; ungrounded output is rejected. (2) `tailoring_pipeline._score` calls the real
async scorers (`match_engine.compute_match_score`,
`ats_scorer.score_resume_against_job`) and records before/after scores. (3) when
Groq is absent or fails, a deterministic parser still produces a truthful,
renderable resume and cover-letter fallback. Broken or old document caches are
regenerated under tailoring pipeline v2.
`deploy_backend.ps1` binds `GROQ_API_KEY` from Secret Manager when that secret
exists; without it, production uses the deterministic renderable fallback.

Job Detail scores (2026-07-11): the top card's Match % rates ROLE fit; the
"Resume readiness" card (formerly "ATS score breakdown") rates how well the
resume document presents that fit (bullets/metrics/formatting). Labeled +
explained in UI so the two numbers don't read as a contradiction. Jobs
filters are minimal by default — the Refine row collapses behind a
"Filters" toggle with an active-count badge.

Keyword extraction (2026-07-10 pm): `text_processing.BUSINESS_SKILLS` adds a
cross-domain lexicon (HR/finance/ops/health/sales/design); `ats_analysis`
now blacklists application-process noise (cv/apply/click), drops
company-internal acronyms defined in-document ("... Centre (OSC)"), and
mines "experience in X, Y, Z" requirement phrases so non-tech JDs extract
their real asks. Resume experience entries carry title/company/dates plus a
computed `duration_label` ("1 yr 7 mos"), with Title↔Company order fixed.

Important files:

- `backend/app/etl/jobs_scraper_6h.py`
- `backend/app/etl/api_sources/runner.py`
- `backend/app/services/careers_ats.py`
- `backend/app/services/careers_page_ingest.py`
- `backend/app/services/company_career_resolver.py`
- `backend/app/services/h1b_sponsor_boards.py`
- `backend/app/utils/job_quality.py`

The scraper must collect full job descriptions when available. Thin descriptions
are marked and repaired by background/detail hydration jobs instead of being
presented as complete matches.

Serving boundary (2026-07-13): the Jobs API defaults to 40 positions per page.
For explicit freshness filters, PostgreSQL applies the honest posting window
before pagination: use `posted_at` when the ATS supplies it and fall back to
`first_seen_at` only when `posted_at` is missing. `last_seen_at` is never treated
as a new posting date. The locked complete-JD boundary accepts the canonical
`jd_complete=true` flag and conservatively recognizes substantial legacy JDs so
older rows cannot blank the feed solely because they predate that metadata flag.

## Labels

Every job should be normalized with:

- country code and country name
- visa program codes and names
- sponsor verified status and source
- English-friendly status
- taxonomy category and role
- no-sponsorship or clearance restrictions when present
- description quality
- baseline ATS score
- resume-based score when a user has an active resume and requests scoring

Important files:

- `backend/app/etl/normalizers/jobs.py`
- `backend/app/etl/visa_label_backfill.py`
- `backend/app/services/global_visa_rules.py`
- `backend/app/api/jobs.py`

## User Profile

User data stays in Firestore. Profiles and preferences support:

- target roles
- target locations
- visa status
- sponsorship required
- English-friendly-only preference
- max years required
- target keywords
- avoid-title signals
- current country and target country
- LinkedIn URL, phone, current company, and experience level
- common ATS application answers such as work authorization, sponsorship need,
  relocation openness, gender, race/ethnicity, disability, and veteran status

The Career Copilot local files (`candidate_profile.json`, `discover.py`,
`jobs_data.js`, and the system prompt) are patterns for production behavior,
not production data dependencies. Bring the ideas forward this way:

- store each user's target roles, countries, keywords, visa status, seniority,
  and avoid-title signals in Firestore preferences
- score jobs 0-100 with sponsorship as a hard gate when the user requires it
- cap or reject roles with explicit no-sponsorship, citizenship-only, or
  clearance-only language from visa-friendly views
- never hardcode one candidate's profile as the platform default
- never auto-submit applications; prepare, score, tailor, and queue for user
  review

Important files:

- `backend/app/models/user.py`
- `backend/app/db/firestore_user_store.py`
- `backend/app/api/user.py`
- `frontend/src/app/components/dashboard/SettingsPage.tsx`

The Career Copilot local files are useful patterns only. Production should not
depend on `jobs_data.js` or local `.careercopilot` state.

## Automated Application System

PlaceUp prepares and — after a mandatory human review — submits applications on
the user's behalf. The engine is hybrid: submit through legitimate candidate
ATS APIs where they exist, and fall back to server-side headless-browser
automation only for platforms that are web-form-only. A non-optional
review-before-submit gate sits on every application. The system prefers APIs,
throttles hard, never defeats CAPTCHAs, and hands off to the user instead.

This is legally contested territory: Workday, LinkedIn and most ATS Terms of
Service prohibit automated submission. The review-before-submit + per-application
human approval model reduces but does not eliminate account/IP-blocking risk.
Users must give explicit, specific, informed consent before we submit for them,
and they — not the LLM — are responsible for the truthfulness of their answers.

### Intake tiers (the core routing decision)

Every ATS falls into one tier; the tier drives the whole flow.

- Tier A — candidate-facing submission API: Greenhouse, Ashby, SmartRecruiters,
  Workable, Recruitee, plus Teamtailor, JazzHR, Phenom (partner-auth). IMPORTANT
  (verified 2026-07-12): "Tier A" means a candidate-apply API *exists* and we can
  map to it — it does NOT mean submission is open. Reading postings is public,
  but **submitting** an application is credential-gated on almost every one:
    - Recruitee — genuinely open: no-auth candidate POST. The one true
      submit-without-a-key case.
    - Greenhouse — `POST` submit needs HTTP Basic Auth with that company's
      Job Board API Key (per-employer). Reading the board is no-auth.
    - Ashby — `applicationForm.submit` needs the org's `candidatesWrite` key;
      no general public apply API.
    - SmartRecruiters — `POST /postings/:uuid/candidates` needs an API key or
      OAuth; they run a partner "Post an Application" program.
    - Workable — creating a candidate needs a Bearer token; a **partner token**
      exists for building across many accounts.
  So Greenhouse/Ashby/SmartRecruiters/Workable are submittable only once PlaceUp
  holds a partner token (or a specific employer's key). See "Submit credentials
  & partner programs" below. This corrects the original architecture PDF, which
  labeled Tier A "no employer key needed" — true for reading, not for posting.
- Tier B — API exists but requires the employer's OAuth/API key (Workday,
  iCIMS, Oracle/Taleo, SuccessFactors, UKG, ADP, Zoho Recruit, Dover, Gem,
  Pinpoint). We never hold employer credentials, so these are treated as
  web-form-only.
- Tier C — web-form-only, headless browser required (Lever, Workday candidate
  side, Rippling, BambooHR, Jobvite, BreezyHR, Paylocity, Dayforce, Join,
  Hireology, Polymer, plus every Tier B platform).

Routing lives in `backend/app/services/apply/tiers.py`. `infer_ats_type(job)`
resolves the real platform from metadata / canonical URL (never the scraper
fan-out worker name); `resolve_tier` returns the tier (unknown ⇒ Tier C, the
always-available path); `is_api_submittable` is the static Phase-0 allowlist
(`API_SUBMITTABLE_ATS`) that never depends on adapter import order.

### Security-control boundary (non-negotiable)

PlaceUp never solves, bypasses, or automates past a CAPTCHA, OTP challenge, or
bot-detection check. These exist specifically to stop automated submission;
defeating them would violate ATS Terms of Service (Workday/iCIMS/LinkedIn
explicitly prohibit it), get the *user's* email/IP flagged or banned, cause
applications to be silently discarded, and expose PlaceUp to account termination
and legal (circumvention) exposure. When a site presents one of these, the
browser worker sets `NEEDS_YOU` and hands the single challenge to the user — it
does not fill the whole form invisibly and it does not use CAPTCHA-solving
services. This is a product principle, not a temporary limitation, and requests
to remove it are declined.

### Submit credentials & partner programs

There is no single API to buy. Submit access to each ATS comes one of two ways:

1. Partner program (the scalable path) — apply to each vendor as an integration
   partner and receive a partner token that lets you submit across their
   customers' boards. SmartRecruiters, Workable, JazzHR, Phenom and Teamtailor
   all issue partner tokens. Applying is generally free but approval is a
   business/contract relationship; some involve review, revenue-share, or fees,
   and terms change — confirm with each vendor's partnerships team. Prices are
   not publicly fixed.
2. Per-employer key — only works for companies PlaceUp has a direct relationship
   with (not useful for a candidate-side aggregator).

Recruitee needs neither — its candidate POST is open today.

`APPLY_CREDENTIALED_ATS` (config, default `recruitee`) is the comma-separated
set of ats_types PlaceUp currently holds a submit credential for. It's the
single switch that turns a platform from "prepare + review only" into true
one-click submit. Add an ats_type here the moment its partner token/key is
configured in Secret Manager, and every matching job becomes one-click with no
code change. `tiers.parse_credentialed` + `tiers.is_one_click_ready` gate this.

### One-Click Apply tab

A dedicated dashboard tab (`/dashboard/one-click-apply`,
`frontend/src/app/components/dashboard/OneClickApplyPage.tsx`) lists the user's
target-role matches from recently verified direct ATS boards, with full-JD
links, real posting dates, resume match score, and numbered pagination. Each card is flagged `one_click_ready`
when its ATS is in `APPLY_CREDENTIALED_ATS` (submittable via the official API
right now, after the review gate — no CAPTCHA, no browser). Jobs whose ATS isn't
credentialed yet show as "Tailor & Prepare" (they still tailor + review, but can't
auto-submit until the credential lands). The ready set expands automatically as
partner programs are approved. Backed by `GET /api/apply/one-click`
(`page`, `page_size`, `ready_only`). Only the ready subset is constrained by
partner credentials; non-ready direct ATS roles remain available for preparation.

### Components

- Apply Orchestration (`app/services/apply/orchestrator.py`) — resolves tier,
  runs tailoring, builds the Tier A payload or fills the Tier C form up to (not
  including) submit, and lands the application in `NEEDS_REVIEW`. On approval it
  enqueues the submission; nothing is ever submitted without `confirm=true`.
- Tier A adapters (`app/services/apply/adapters_tier_a.py`) — one per platform.
  `build_payload` is a pure, unit-tested mapping; `submit` is the only method
  that touches the network and only runs after approval. Adapters validate
  required fields client-side (Greenhouse's Job Board API does not validate them
  server-side); SmartRecruiters renders EEO fields last and records consent.
  **Recruitee `submit()` is fully implemented** (the one open, no-credential
  API): it POSTs to the public `/offers/{slug}/candidates` endpoint, reading the
  private GCS resume server-side and sending it as a multipart `candidate[cv]`
  upload; 201 → APPLIED (candidate id
  saved as the confirmation ref), 422 → FAILED with the validation message. The
  other Tier A adapters' `submit()` stay as integration points pending partner
  credentials. Real submission is gated by `APPLY_LIVE_SUBMIT_ENABLED` (default
  false = dry-run: validate + prepare, no POST) so deploys can't fire real
  applications by accident.
- Browser worker (`app/services/apply/browser_worker.py`) — graceful-handoff
  state machine with an injectable Playwright-driver seam. The generic Tier-C
  driver/live-view bridge is not enabled yet; those roles safely return
  `NEEDS_YOU` for manual completion. It never solves or bypasses a control, and
  `browser.close()` always runs in a finally block.
- Tailoring pipeline (`app/services/apply/tailoring_pipeline.py`) — JD-signal
  extraction → tailor resume with only true facts from the base resume (reuses
  `resume_tailor_llm` + `ats_analysis`) → per-position cover letter
  (`resume_tailor_llm.generate_cover_letter`, true facts only) → render to
  ATS-safe DOCX/PDF → before/after score → cache per (user, company, position).
  A deterministic true-facts-only fallback remains renderable when Groq is down. Keep the LLM router
  model-agnostic. Runs for every application (apply + One-Click).
- Resume renderer (`app/services/apply/resume_renderer.py`) — server-side,
  ATS-safe renderer that turns the tailored resume spec into DOCX (python-docx)
  and PDF (reportlab): single column, standard fonts, real headings, no tables /
  text boxes / images. Also renders the cover letter. Original PlaceUp
  templates — no third-party code or branding. `render_all(resume, cover)`
  returns a name→bytes map.
- Doc storage (`app/services/apply/doc_storage.py`) — uploads rendered docs to
  GCS (`APPLY_DOCS_BUCKET`, `gs://…` refs). Production is strictly GCS-only;
  `APPLY_DOCS_LOCAL_DIR` is available only in development/tests.
  `render_and_store_tailored`
  in the apply store now renders + stores and returns resume/cover-letter URLs
  (previously a stub).
- Resume Studio (`frontend/.../ResumeStudioPage.tsx`, `/dashboard/resume-studio`)
  — optional in-app editor for manual tweaks: edit the structured resume spec,
  live-preview the server-rendered PDF, download PDF/DOCX + cover letter. Backed
  by `POST /api/apply/render` (stateless base64 render). Per-position
  auto-render still happens in the pipeline; the Studio is for hand-edits.

### GCP deployment (apply subsystem)

Production-ready on Google Cloud — no local dependencies required:

- Rendered docs live in a **private** Cloud Storage bucket (`APPLY_DOCS_BUCKET`,
  default `placeup-tailored-docs`). `deploy_backend.ps1` creates the bucket
  idempotently (uniform access, private) and grants `placeup-api-sa` the
  `roles/storage.objectAdmin` role. `store_document` writes `gs://…` refs; the
  bucket is never public. The UI fetches docs through the ownership-checked
  `GET /api/apply/{id}/document/{kind}` endpoint, which streams the bytes
  server-side via `doc_storage.read_document`.
- Deps `google-cloud-storage` and `google-cloud-tasks` are in
  `backend/requirements.txt`; the render deps `python-docx` + `reportlab` were
  already present.
- `deploy_backend.ps1` sets the apply env on `placeup-api`:
  `APPLY_FEATURE_ENABLED=true`, `APPLY_DOCS_BUCKET`, `APPLY_CREDENTIALED_ATS`,
  `APPLY_QUEUE_BACKEND`, `APPLY_QUEUE_REGION`, `INBOX_DOMAIN`, `GCP_PROJECT_ID`.
  It uses `--update-env-vars` (merge), so out-of-band auth/email settings are
  preserved.
- Per-ATS Cloud Tasks queues are provisioned on every production deploy. The
  script enables the API, creates/updates dedicated Tier-A queues plus a slow
  shared browser queue, grants `placeup-api-sa` `roles/cloudtasks.enqueuer`, and
  sets `APPLY_QUEUE_BACKEND=cloudtasks` + `APPLY_WORKER_URL`. The historical
  `-CreateApplyQueues` switch remains accepted but is no longer required.
- Submission push handler `POST /api/apply/internal-submit` runs a queued
  submission (`orchestrator._run_submit`) for one application. Internal-key
  protected — the Cloud Tasks enqueuer (`apply_queue._enqueue_cloud_tasks`) adds
  the standard `X-API-Key` header. The zero-trust middleware accepts that
  verified internal credential for direct Cloud Run service traffic. The local
  queue is a development/test fallback and is never selected by production deploys.
- **Going live on Recruitee** (the one ready-now ATS): keep
  `APPLY_CREDENTIALED_ATS` including `recruitee` and deploy with
  `-EnableLiveApply`. The script explicitly sets
  `APPLY_LIVE_SUBMIT_ENABLED=true`. After that, a user's
  approve on a Recruitee job actually submits via the official API (resume +
  cover letter attached), with the human review gate still required. Leave it
  false to demo the whole flow as a dry-run first.
- Before trusting the Recruitee field names against a live offer, run the probe
  `backend/scripts/recruitee_submit_probe.py` (dry-run by default; `--live`
  actually submits). It prints the exact request the adapter sends so you can
  confirm the documented multipart `candidate[cv]` contract.
- The local-dir fallback (`APPLY_DOCS_LOCAL_DIR`) is only for dev/tests. In
  production a missing bucket or failed upload returns no document instead of
  writing an ephemeral `file://` reference.
- Deploy: `.\backend\deploy\deploy_backend.ps1 -ProjectId steel-shine-492401-u6
  -Region us-east1 -DbInstance placeup-backend -ApplyDocsBucket
  placeup-tailored-docs -EnableLiveApply` (bucket, queues, IAM, env, and the
  explicit real-submit safety switch handled automatically).
- Dedicated inbox (`app/services/apply/inbox_ingest.py`) — parses the SES→Lambda
  webhook, extracts OTP/verification codes, classifies the message, and links it
  to an application. Codes are surfaced in the review UI; the user still enters
  them.
- Per-ATS queue (`app/services/apply/apply_queue.py`) — Cloud Tasks abstraction
  with a local asyncio fallback; per-ATS rate limits; idempotent on app id.
- Store (`app/db/firestore_apply_store.py`) — Firestore CRUD for `applications`,
  `application_profiles`, `tailored_docs`, `inbox_messages`, `ats_adapters`.
- API (`app/api/apply.py`) — `POST/GET /api/apply`, `GET /api/apply/{id}`,
  `POST /api/apply/{id}/approve|cancel`, `PATCH /api/apply/{id}/status`,
  `GET/PUT /api/apply/profile`, `GET /api/apply/inbox`,
  `GET /api/apply/one-click` (One-Click Apply feed),
  `POST /api/apply/render` (Resume Studio DOCX/PDF render),
  `GET /api/apply/{id}/document/{kind}` (ownership-checked stream of a stored
  tailored resume/cover-letter from private Cloud Storage), and the
  service-authenticated `POST /api/apply/inbox/webhook` +
  `POST /api/apply/internal-submit` (Cloud Tasks submission push target). Gated
  by `APPLY_FEATURE_ENABLED` (503 when off, no redeploy needed).
- Frontend — the existing `ApplicationsPage.tsx` kanban tracker, the new
  `ReviewBeforeSubmit.tsx` gate, and the new `OneClickApplyPage.tsx` tab
  (`/dashboard/one-click-apply`, in `Dashboard.tsx` NAV_ITEMS); apply client
  functions in `lib/api.ts` (`startApplication`, `approveApplication`,
  `setApplicationStatus`, `getOneClickJobs`, …).

### Why the dedicated inbox, not Gmail OAuth

Each user gets `first.last@mail.placeupcareer.com` via an SES catch-all receipt
rule — no per-user provisioning. Gmail restricted scope is rejected because it
forces an annual CASA Tier 2 security assessment (recurring cost) and a
**lifetime 100-user cap that cannot be reset until the app is verified** — a
non-starter for a consumer product targeting thousands of students. Record this
rejection in the design doc, not just here.

### Data minimization & compliance

- Prefer per-application data entry over storing ATS logins; minimize stored
  credentials. Voluntary EEO/identity answers are **not persisted** in Phase 0
  (`_assert_profile_minimized` in `app/api/apply.py` rejects them) until Cloud
  KMS envelope encryption is wired; users enter them at review time.
- Encrypt sensitive fields with Cloud KMS; scope Firestore rules to owner +
  service account; audit-log every submission with a screenshot/receipt.
- GDPR/CCPA: explicit consent for automated submission, data export + deletion,
  retention limits on `inbox_messages`, DPAs with SES/Cloudflare.

### Change-course thresholds

- If block/failure rate on an ATS exceeds ~5–10%, slow that queue or disable
  browser automation for it and route to manual.
- If an ATS requires handoff on >50% of attempts, deprioritize automating it.
- Stay on Cloud Run until interactive browser concurrency regularly exceeds
  ~25–50 simultaneous sessions; then move to a managed browser or GKE pool.

### Phased roadmap

- Phase 0 (done in this pass): tier framework + Tier A adapters (Greenhouse,
  Ashby, SmartRecruiters, Workable, Recruitee) + application data model +
  tracker + review gate. No browser automation yet.
- Phase 1 (backend complete): tailoring pipeline with diff data + review gate;
  dedicated-inbox SES capture + OTP extraction. Rich field-level diff display
  can continue to improve in the frontend.
- Phase 2: Playwright browser worker on Cloud Run Jobs for Tier C (start with
  Greenhouse-form + Lever, then Workday); Cloud Tasks per-ATS queues.
- Phase 3: real-time handoff (screencast + input relay); full kanban statuses;
  CSV import/export.
- Phase 4: scale-out (managed browser / GKE), remaining Tier C adapters by
  demand, block-rate dashboards, compliance hardening.

### Caveats to verify before launch

Verify each Tier A adapter against live ATS docs. Greenhouse Harvest v1/v2 are
deprecated after 2026-08-31 (migrate to v3). Gem/Polymer/Join write-capability
were unconfirmed in public docs. LLM prices move (Gemini 2.0 Flash deprecated
2026-06-01) — keep the router model-agnostic.

Important files:

- `backend/app/models/application.py`
- `backend/app/services/apply/` (tiers, base, adapters_tier_a, orchestrator,
  browser_worker, tailoring_pipeline, inbox_ingest, apply_queue)
- `backend/app/db/firestore_apply_store.py`
- `backend/app/api/apply.py`
- `backend/tests/test_apply_system.py`
- `frontend/src/app/components/dashboard/ReviewBeforeSubmit.tsx`
- `frontend/src/app/components/dashboard/OneClickApplyPage.tsx`
- `frontend/src/app/components/dashboard/ResumeStudioPage.tsx`
- `backend/app/services/apply/resume_renderer.py`,
  `backend/app/services/apply/doc_storage.py`
- Config: `APPLY_FEATURE_ENABLED`, `APPLY_LIVE_SUBMIT_ENABLED`,
  `APPLY_CREDENTIALED_ATS`, `APPLY_QUEUE_BACKEND`, `APPLY_WORKER_URL`,
  `INBOX_DOMAIN`, `APPLY_DOCS_BUCKET`, `APPLY_DOCS_LOCAL_DIR` in
  `backend/app/config.py`

## Frontend Rules

The frontend uses React, Vite, Tailwind CSS, Motion, and lucide-react.

### Theming (dark + light, 2026-07-10)

The whole app supports dark and light modes. How it works:

- Every color in inline styles resolves to a CSS variable
  (`var(--pu-...)`) defined in `frontend/src/styles/theme-tokens.css`,
  which holds the full dark palette (the original brand colors) and a
  tuned light palette, switched by `data-theme` on `<html>`.
- `Layout.tsx` owns the ThemeProvider: explicit user choice persists in
  localStorage (`placeup-theme`); otherwise the OS preference is followed
  live. `index.html` applies the same logic pre-paint (no flash). The
  `.dark` class is kept in sync for the shadcn/Tailwind components, and
  `ThemeToggle` (exported from `Layout.tsx`) renders the sun/moon switch
  used in the public navbar and the dashboard topbar.
- `BrandLogo` auto-swaps wordmark variants with the theme; toasts
  (`ui/sonner.tsx`) follow the same provider.
- NEW CODE RULE: never hardcode a color in a component. Use an existing
  `--pu-*` token (or add the token to BOTH palettes in theme-tokens.css).
  The only exceptions are the static "paper" resume document in
  UserProfilePage and unused canvas components.

Non-negotiable coding rules:

- import router APIs from `react-router`, not `react-router-dom`
- import animation from `motion/react`, not `framer-motion`
- page components use default exports
- use `ImageWithFallback` for new images
- do not modify `frontend/src/app/components/figma/ImageWithFallback.tsx`
- do not modify lockfiles unless dependency changes require it
- keep typography sizing/weight/line-height inline where the current design
  system does so
- keep dashboard UI dense, professional, and scannable
- do not dump raw job descriptions; render structured sections, highlights,
  risks, requirements, and readable paragraphs

Important frontend files:

- `frontend/src/app/routes.ts`
- `frontend/src/app/components/Layout.tsx`
- `frontend/src/app/components/dashboard/JobsPage.tsx`
- `frontend/src/app/components/dashboard/JobDetailPage.tsx`
- `frontend/src/styles/theme.css`

## Deployment

Backend:

```powershell
.\backend\deploy\deploy_backend.ps1 `
  -ProjectId steel-shine-492401-u6 `
  -Region us-east1 `
  -DbInstance placeup-backend `
  -UserDatabaseBackend firestore `
  -UserFirestoreProjectId placeup-firebase-641222668282 `
  -UserFirestoreDatabase "(default)" `
  -FrontendUrl https://placeupcareer.com
```

Internal application server:

```powershell
.\backend\deploy\deploy_app_server.ps1 `
  -ProjectId steel-shine-492401-u6 `
  -Region us-east1 `
  -DbInstance placeup-backend
```

Cloud Run frontend:

```powershell
cd frontend
.\deploy_frontend.ps1 `
  -ProjectId placeup-firebase-641222668282 `
  -Region us-east1 `
  -ApiBase "" `
  -BackendOrigin "https://placeup-api-rui2a74muq-ue.a.run.app"
```

Health check:

```powershell
Invoke-WebRequest -UseBasicParsing https://placeupcareer.com/api/health
```

## Private master-job ATS analysis

PlaceUp self-hosts `SlyGoblin/mistral_ATSscore_generation` over
`mistralai/Mistral-7B-Instruct-v0.2`; no third-party inference API receives job
descriptions. The private model produces normalized skills, keywords,
responsibilities, experience, seniority, education, certifications, and work
authorization data. `app.workers.master_ats_analysis` writes the versioned
result to `master_jobs.extra_metadata.ats_model_analysis` for every active job
with a complete description. Description hashes make the backfill resumable and
automatically re-analyze changed JDs.

Preferred Cloud Run GPU deployment (requires one L4 quota):

```powershell
.\backend\deploy\deploy_ats_model.ps1 `
  -ProjectId steel-shine-492401-u6 `
  -ApiRegion us-east1 `
  -GpuRegion us-east4 `
  -DbInstance placeup-backend `
  -CreateSchedule
```

Quota-efficient Compute Engine deployment (one P4, 4-bit NF4, resumable Spot
VM, private Docker network, no ingress firewall rule, and automatic shutdown on
success or failure):

```powershell
.\backend\deploy\deploy_ats_batch_vm.ps1 `
  -ProjectId steel-shine-492401-u6 `
  -Zone us-central1-a `
  -GpuType nvidia-tesla-p4 `
  -MachineType n1-standard-4 `
  -ProvisioningModel SPOT `
  -CreateSchedule
```

The project must have both a regional GPU allowance and a non-zero
`GPUS_ALL_REGIONS` quota before either GPU runtime can start. Images, service
accounts, Secret Manager tokens, database access, and the worker can be
provisioned before that quota is granted.

## Testing

Run focused backend tests after scraper/security changes:

```powershell
python -m pytest backend\tests\test_zero_trust.py backend\tests\test_global_visa_rules.py backend\tests\test_board_discovery_sweep.py backend\tests\test_api_sources.py
python -m pytest backend\tests\test_master_ats_analysis.py
```

Run the apply-subsystem tests after any change to `app/services/apply/*`,
`app/api/apply.py`, or the application models:

```powershell
python -m pytest backend\tests\test_apply_system.py
```

Run frontend build after UI changes:

```powershell
cd frontend
npm run build
```

## Operations

Useful commands:

```powershell
gcloud.cmd run services describe placeup-api --region us-east1 --project steel-shine-492401-u6 --format="value(status.latestReadyRevisionName,status.traffic[0].percent)"
gcloud.cmd run jobs execute placeup-job-scraper-6h --region us-east1 --project steel-shine-492401-u6 --async
gcloud.cmd run jobs execute placeup-visa-label-backfill --region us-east1 --project steel-shine-492401-u6 --async
gcloud.cmd run jobs execute placeup-board-discovery-sweep --region us-east1 --project steel-shine-492401-u6 --async
```

Manual label repair:

```powershell
gcloud.cmd run jobs execute placeup-visa-label-backfill --region us-east1 --project steel-shine-492401-u6 --args="--all" --async
```

## July 18, 2026 Release — Dashboard/Jobs/Tailor Overhaul

Summary of changes in this release:

- Analytics page removed entirely (`/dashboard/analytics` redirects to Jobs;
  backend `/api/analytics/dashboard` deleted; `/api/analytics/market` kept for
  the Overview market widget).
- Applications page minimized to title + posted date + applied date; counts
  and rows include ONLY `status == "applied"` records. `posted_at` is now
  stored on user applications.
- Jobs page: default view is ALL currently-open positions (new "All open"
  time option; the visibility boundary equals the 60-day retention window in
  `api/jobs.py: VISIBLE_RETENTION_DAYS`). Role/category filters now push
  taxonomy title terms into the indexed SQL query, fixing empty results when
  selecting a role. The Experience filter is re-applied against the FULL job
  description after hydration.
- One-click apply: automated submission (`POST /api/apply/{id}/approve`) is
  Elite-only (402 otherwise). Everyone still sees every position and can
  tailor + prepare. The one-click feed returns `one_click_allowed`.
- Retention: `SCRAPER_RETENTION_DAYS` now defaults to 60 (2 months) and the
  new `app/workers/job_retention.py` job purges expired AND non-taxonomy
  positions daily.
- Scraper: coverage audit now feeds a targeted gap backfill
  (`SCRAPER_GAP_BACKFILL_*` envs) so thin role-country cells are re-scraped in
  the same run.
- ATS score: the SlyGoblin/mistral_ATSscore_generation analysis stored in
  `extra_metadata.ats_model_analysis` is blended into visible match scores
  (70% deterministic + 30% model requirement coverage).
- Tailoring: the OpenClaw service runs the LOCAL openclaw CLI only
  (`openclaw agent --model glm-5.2:cloud`); no direct HTTP API path. Each
  instance runs a bounded pool of 16 child processes with retry/backoff, and
  Cloud Run scales to 32 instances (≈512 concurrent requests). The Tailor
  page uses this service first, then Groq, then deterministic. Prompt now
  also emits a specific 3-paragraph cover letter.

Deploy steps (PowerShell, in order):

```powershell
# 0) SECURITY: rotate the Ollama Cloud API key (it was shared in chat), then:
gcloud.cmd secrets create OLLAMA_API_KEY --project steel-shine-492401-u6 --replication-policy automatic
echo <NEW_KEY> | gcloud.cmd secrets versions add OLLAMA_API_KEY --project steel-shine-492401-u6 --data-file=-

# 1) OpenClaw tailoring service (local openclaw CLI, --model glm-5.2:cloud)
#    The script builds the image, mounts OLLAMA_API_KEY + service token from
#    Secret Manager, and sets concurrency 16 x max-instances 32.
backend\deploy\deploy_openclaw_tailor.ps1 -ProjectId steel-shine-492401-u6 -EnableApiIntegration

# 2) API + app server (jobs/apply/user/analytics changes)
backend\deploy\deploy_backend.ps1 -ProjectId steel-shine-492401-u6
backend\deploy\deploy_app_server.ps1 -ProjectId steel-shine-492401-u6

# 3) Scraper image (retention default + gap backfill)
backend\deploy\deploy_country_scrapers.ps1 -ProjectId steel-shine-492401-u6

# 4) Retention job (daily 60-day + non-taxonomy purge)
gcloud.cmd run jobs create placeup-job-retention --region us-east1 --project steel-shine-492401-u6 `
  --image us-east1-docker.pkg.dev/steel-shine-492401-u6/placeup/backend:latest `
  --command python --args="-m,app.workers.job_retention" `
  --set-secrets DATABASE_URL=DATABASE_URL:latest --max-retries 1 --task-timeout 3600
gcloud.cmd scheduler jobs create http placeup-job-retention-daily --project steel-shine-492401-u6 `
  --location us-east1 --schedule "0 9 * * *" `
  --uri "https://run.googleapis.com/v2/projects/steel-shine-492401-u6/locations/us-east1/jobs/placeup-job-retention:run" `
  --oauth-service-account-email placeup-api-sa@steel-shine-492401-u6.iam.gserviceaccount.com

# 5) Frontend
cd frontend
npm run build
.\deploy_frontend.ps1
```

Follow-up fixes (same release, second deploy):

- Jobs feed starvation: personalized feeds now keep role title-terms in the
  indexed SQL query (the newest-4k pool only spanned hours of the 60-day
  window, showing 1 result while the market widget counted 2k+). Exact
  resume scoring is capped at 1200 pool rows; the visible page is always
  exact-scored.
- Taxonomy direction reversed per product decision: unknown-role positions
  are KEPT (non-taxonomy purge is now opt-in via --include-non-taxonomy).
  New `app/workers/taxonomy_evolution.py` reports high-volume unknown titles
  as add candidates and zero-inventory roles as remove candidates (emails
  operations@).
- One-click flow: preparation-time NEEDS_YOU no longer dead-ends the modal —
  apps stay in NEEDS_REVIEW so Step 2 (approve & auto-apply) always exists.
  Unknown ATS questions are auto-answered by the LLM from JD+resume+cover+
  profile (`services/apply/question_answerer.py`); EEO/sensitive questions
  are never auto-answered; anything unanswered holds the application pending
  in the modal until the user fills it, saves, and approves.
- Review modal shows editable profile answers for browser submissions too.
- Notification bell refreshes every 60s and on window focus.
- Resume quality score (e.g. 75) is computed deterministically at upload
  time by `score_resume_quality`; the GPU model scores JOBS against the
  resume (match/ATS scores), not this number. It changes when a new resume
  version is uploaded.

Run ALL master job descriptions through the private mistral ATS model (after
GPU deploy; see "Private master-job ATS analysis" section):

```powershell
.\backend\deploy\deploy_ats_model.ps1 -ProjectId steel-shine-492401-u6 -ApiRegion us-east1 -GpuRegion us-east4 -DbInstance placeup-backend -CreateSchedule
# or the Spot-VM variant (deploy_ats_batch_vm.ps1); either runs
# app.workers.master_ats_analysis until every active JD is analyzed.
```

Required env/secrets after deploy: `OPENCLAW_TAILOR_ENABLED=true`,
`OPENCLAW_TAILOR_URL=<service url>`, `OPENCLAW_TAILOR_TOKEN` (existing
secret), `OLLAMA_API_KEY` (rotated). Optional: `SCRAPER_RETENTION_DAYS`
(default 60), `SCRAPER_GAP_BACKFILL_ENABLED` (default true),
`TAILOR_MAX_CONCURRENCY` (default 16 per instance; total = × max-instances).

## August 24, 2026 — Dependency Audit and Version Policy

No product behaviour changed in this pass. It closes the gap between what
`requirements.txt` / `package.json` *said* and what was actually being
installed, and removes every dependency advisory that upstream allows us to
remove.

### The underlying problem

`backend/requirements.txt` declared only `>=` floors and no ceilings, and the
floors had not moved since the file was written. Because pip always picks the
newest version that satisfies a floor, every image build silently adopted the
newest MAJOR of every dependency. The local venv had already drifted to
pandas 2.3.3, scikit-learn 1.8, reportlab 5.0, stripe 15.1, bcrypt 5.0,
redis 8.0, pytest 9.0 and firebase-admin 7.4 — none of it recorded anywhere.
pandas 3.x is now published, so the next unpinned build would have taken it.

The policy now written at the top of `requirements.txt`:

* lower bounds are the versions the stack is known to run on;
* upper bounds cap the next MAJOR;
* a ceiling is raised deliberately, after running the suite — never deleted.

### Security fixes (backend)

Audited against the PyPI advisory database on 2026-08-24. 18 installed
packages carried advisories; after this change, 1 does.

Direct dependencies whose floor allowed a vulnerable build:

| Package | Old floor | New floor | Issue |
|---|---|---|---|
| `python-multipart` | 0.0.17 | 0.0.31 | urlencoded body mis-parsing; negative `Content-Length` |
| `PyJWT` | 2.9.0 | 2.13.0 | algorithm confusion when HMAC + asymmetric are both accepted |
| `pydantic-settings` | 2.6.0 | 2.14.2 | `NestedSecretsSettingsSource` directory traversal |

`PyPDF2` was replaced by `pypdf`. PyPDF2 is end-of-life — the name was
retired in favour of `pypdf`, and its final release (3.0.1) carries an
unpatched infinite-loop DoS in `__parse_content_stream` (PYSEC-2026-1835)
that will never be fixed under the old name. `app/services/resume_parser.py`
imports `pypdf` first and falls back to `PyPDF2` only so that a container
image that has not been rebuilt yet keeps parsing resumes. The `PdfReader`
API is identical; nothing else changed.

A new **transitive security floors** block at the end of `requirements.txt`
pins twelve packages PlaceUp never imports directly — `starlette`, `aiohttp`,
`cryptography`, `urllib3`, `idna`, `h2`, `httplib2`, `msgpack`, `pyasn1`,
`soupsieve`, `langchain`, `langsmith`. They arrive underneath FastAPI, httpx,
google-auth, firebase-admin and scrapegraphai. pip has no override mechanism,
so naming them directly is the only way to stop the resolver picking a version
with a published advisory. The most serious were request smuggling on
WebSocket upgrade (`aiohttp`) and Host-header spoofing of `request.url`
(`starlette`). Each line carries the reason; delete a line once the parent
package's own floor has caught up.

`markdownify` remains the single unresolved advisory, exactly as documented
before. Re-verified against python-jobspy 1.1.82: the hard pin is still
`markdownify>=0.13.1,<0.14.0`, so the patched 0.14.1 cannot be installed
without dropping the main scraper. The containment argument is unchanged —
it is reachable only inside python-jobspy's HTML-to-text conversion, in the
isolated background Cloud Run job, under a job timeout.

### Security fixes (frontend)

`npm audit` reported five HIGH advisories; it now reports zero.

* `react-router` `^7.17.0` → `^7.18.2`. The declared range admitted five HIGH
  advisories, including an open redirect via backslash in `<Link>` and
  `useNavigate`, an XSS through `RSCErrorHandler`, and arbitrary constructor
  injection in `deserializeErrors()` during SSR hydration. 7.18.2 is the
  patched release on the 7.x line; **react-router 8.x is a separate migration
  and was deliberately not taken.**
* `brace-expansion`, `nanoid`, `postcss` and `tar` were transitive and fixed
  by regenerating `package-lock.json`. The frontend image builds with
  `npm ci`, so the lockfile is what production actually installs — it must be
  committed alongside `package.json`.

Thirty-five same-major upgrades were applied at the same time (the Radix UI
set, `react-hook-form`, `sonner`, `tailwind-merge`, `tailwindcss` and
`@tailwindcss/vite` 4.1.12 → 4.3.3, `eslint`, `input-otp`, `tw-animate-css`,
`react-responsive-masonry`).

### Deliberately NOT upgraded

These are real migrations, not version bumps, and each needs its own pass:

| Package | Current | Latest | Why it was left |
|---|---|---|---|
| `react` / `react-dom` | 18.3.1 | 19.2.8 | gates almost everything below it |
| `@mui/material`, `@mui/icons-material` | 7.3.5 | 9.3.1 | two majors |
| `recharts` | 2.15.2 | 3.10.1 | v3 migration guide; 2.x is deprecated upstream |
| `react-router` | 7.18.2 | 8.3.0 | major |
| `vite` + `@vitejs/plugin-react` | 6.4.3 / 4.7.0 | 8.2.2 / 6.1.0 | two majors |
| `@sentry/react` | ^8.55.2 | 10.71.0 | two majors |
| `react-day-picker` | 8.10.1 | 10.0.1 | two majors |
| `react-resizable-panels` | 2.1.7 | 4.12.3 | two majors |
| `date-fns`, `lucide-react`, `motion` | — | 4.x / 1.x / 13.x | major each |
| `pandas` | 2.3.3 | 3.0.5 | copy-on-write and string-dtype changes |

`recharts@2.x` prints a deprecation warning on install; that is expected until
the v3 migration happens.

### Known follow-ups

* `frontend/package.json` still carries `pnpm.overrides.vite = 6.4.2`, but the
  frontend Dockerfile uses `npm ci`. That override is dead configuration and
  npm resolves vite to 6.4.3 regardless.
* `app/models/job.py` uses a class-based `Config`, deprecated in Pydantic 2
  and removed in 3. The `<3.0` ceiling holds it for now; migrate to
  `ConfigDict` before raising it.
* Several modules call `datetime.utcnow()`, deprecated in Python 3.12 and
  scheduled for removal. `python:3.12-slim` is still the base image.

### Verification performed

* Backend resolved cleanly on python 3.12 (179 packages) and the full suite
  ran: **172 passed, 1 failed**, the failure being a fixture file excluded
  from the verification copy, not a regression.
* Re-audit of the resolved set: 18 vulnerable packages → 1 (`markdownify`).
* Frontend: `npm ci` + `npm run build` succeeded, 2892 modules transformed;
  `npm audit` reports 0 vulnerabilities.
* Local runtime unchanged and re-verified statically: `bash -n` and
  `shellcheck -S warning` clean on `scripts/placeup.sh` and
  `scripts/bootstrap-ubuntu.sh`; all 34 Makefile targets pass `make -n`;
  `docker compose -f compose.yaml -f compose.linux.yaml config` validates for
  core and for the `workers`, `ai` and `ats` profiles. A live boot still has
  not been performed — no Docker daemon is reachable from the assistant
  sandbox.

### Deploy

No migration and no config change. Rebuild and redeploy the images so the new
pins take effect:

```powershell
backend\deploy\deploy_backend.ps1     -ProjectId steel-shine-492401-u6
backend\deploy\deploy_app_server.ps1  -ProjectId steel-shine-492401-u6
backend\deploy\deploy_country_scrapers.ps1 -ProjectId steel-shine-492401-u6
cd frontend
npm ci          # NOT npm install — the lockfile is the audited artefact
npm run build
.\deploy_frontend.ps1
```

## Documentation Policy

Keep documentation in this file. When architecture, deployment, scraper
sources, security, or UI rules change, update `MASTER_DOCUMENTATION.md` in the
same commit.

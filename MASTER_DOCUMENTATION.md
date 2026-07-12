# PlaceUp Career Master Documentation

Last updated: 2026-07-10

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
Jobs are named like `placeup-country-scraper-us`.

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

## Testing

Run focused backend tests after scraper/security changes:

```powershell
python -m pytest backend\tests\test_zero_trust.py backend\tests\test_global_visa_rules.py backend\tests\test_board_discovery_sweep.py backend\tests\test_api_sources.py
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

## Documentation Policy

Keep documentation in this file. When architecture, deployment, scraper
sources, security, or UI rules change, update `MASTER_DOCUMENTATION.md` in the
same commit.

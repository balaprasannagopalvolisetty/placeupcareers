# PlaceUp Career — Agent Context (read this first)

> **Purpose of this file**: a single document any developer or AI agent
> can read to understand the *current* state of PlaceUp, what works,
> what's broken, what's planned, and exactly how to start work without
> re-discovering the whole codebase.
>
> **Last updated**: 2026-05-31 (matches the code in this repo, not an
> aspirational roadmap).

---

## 1. What this product is

PlaceUp Career is a **global career platform for English-speaking
international students and visa-seeking talent**. The product direction is
worldwide coverage: collect positions country-by-country only when the company
is a verified visa sponsor in that role's country, or the posting is clearly
labeled as sponsorship-indicated for countries without a public sponsor
registry. The user uploads a resume once, and the platform:

1. Scrapes jobs on a free/open-source-first basis from official job APIs,
   government portals, and public company ATS endpoints. The scheduled
   production path does not use paid LinkedIn providers or blocked anonymous
   aggregator scraping.
2. Verifies employers against country-specific visa sponsor registries where
   those registries exist (USCIS/DOL for US, UK licensed sponsors, IND
   Netherlands, LMIA/Job Bank Canada, etc.).
3. Filters and labels jobs by destination country, sponsor source,
   English-friendliness, and eligible visa programs for that country.
4. Tags each job into the current 12-category × 100-role taxonomy, using 533
   scrape terms so all current role families are covered.
5. Scores every job against the user's active resume (keyword overlap,
   per-request, fast — no LLM in the hot path).
6. Surfaces visa sponsorship signal from H1B/USCIS data today and the
   generalized `visa_sponsors` model as global sponsor importers are added.
7. Discovers up to 3 recruiter contacts per job via the bulk
   enrichment pipeline (FinalScout / Apollo / Hunter / DOL LCA / team
   pages / GitHub).

The end-state user flow:

> "I sign up. I upload a resume. The dashboard shows me fresh
> English-friendly roles across target countries, with my ATS score for each,
> the country's visa/sponsor proof for that employer, and 3 recruiter emails I
> can draft outreach to. Filters work. No mock data. No stale results."

---

## 2. Architecture in one diagram

```
┌─────────────────────────────────────────┐                ┌───────────────────────────────────────┐
│ Frontend — React 18 + Vite + Tailwind   │ HTTP/JSON      │ Backend — FastAPI (uvicorn) :8000     │
│ /src/app/...                            │ ─────────────► │   /api/auth, /api/user, /api/jobs,    │
│ Bearer token in localStorage            │ ◄───────────── │   /api/visa, /api/alerts, /api/...    │
│ Vite dev proxy: /api/* → :8000          │                │                                       │
└─────────────────────────────────────────┘                └───────────────────────────────────────┘
                                                                     │
                                                                     ▼
                                                  ┌──────────────────────────────────────┐
                                                  │ SQLite — backend/data/placeup.db     │
                                                  │   users, user_alerts, user_resumes,  │
                                                  │   user_preferences, jobs,            │
                                                  │   h1b_sponsors (23K rows),           │
                                                  │   contacts                            │
                                                  └──────────────────────────────────────┘
                                                                     ▲
                                                                     │
                                                       APScheduler (every 8h)
                                                                     │
                                                  ┌──────────────────────────────────────┐
                                                  │ Scraper — multi-source              │
                                                  │   JobSpy → Indeed/LinkedIn/Glassdoor │
                                                  │   USAJobs / Dice / Greenhouse boards │
                                                  │   H1B sponsor pipeline               │
                                                  │ → geo-filter US+CA                   │
                                                  │ → tag years_min/max + entry_level    │
                                                  │ → dedupe by content_hash             │
                                                  │ → enrich each job with ≤3 contacts   │
                                                  │ → deactivate jobs >12 days old       │
                                                  └──────────────────────────────────────┘
```

Current production note: the diagram above is historical in a few labels. The
live Cloud Run ETL now uses Cloud SQL/Postgres for job data, runs the
`placeup-job-scraper-6h` Cloud Run Job, and the scheduled scrape path is
free/open only: `usajobs`, `dice`, `h1b_sponsor`, and `tier1_ats`. LinkedIn
repair is a one-off/legacy cleanup worker for existing rows; it is not part of
the default scheduled global ingestion policy.

---

## 3. Tech stack (versions, not aspirations)

### Backend (`backend/`)
- Python 3.12 (Windows venv at `backend/.venv`)
- FastAPI + uvicorn
- SQLite 3 (file at `backend/data/placeup.db`)
- `python-jobspy` remains installed, but scheduled production scraping defaults
  to free/open official sources and public ATS endpoints.
- `bcrypt` 4.x (called directly, not via passlib — passlib 1.7 is broken on bcrypt 4)
- `PyJWT` for HS256 access tokens
- `apscheduler` for the 8h scrape loop
- `openpyxl` to read the bundled H1B Excel

### Frontend (`frontend/`)
- React 18.3 + Vite 6
- react-router 7 (Data mode, `createBrowserRouter`) — **never use `react-router-dom`**
- Tailwind CSS v4 (config in `src/styles/theme.css` via `@theme inline`)
- Motion (the successor to Framer Motion) — `import { motion } from "motion/react"`
- lucide-react icons
- recharts (charts)
- shadcn/ui primitives in `src/app/components/ui/`

---

## 4. File structure (what each directory does)

```
backend/
├── app/
│   ├── main.py                    # FastAPI entry point + lifespan + scheduler
│   ├── config.py                  # Settings loaded from .env (Pydantic Settings)
│   ├── security.py                # bcrypt + JWT + current_user_id dependency
│   ├── job_taxonomy.py            # 12 categories × 100 roles × 533 scrape terms
│   ├── scrape_constants.py        # Re-exports taxonomy synonyms as scrape queries
│   ├── api/                       # FastAPI routers (one per resource)
│   │   ├── auth.py                # /signin /signup /demo (auto-seed)
│   │   ├── user.py                # /profile /preferences /password /resumes /notifications
│   │   ├── jobs.py                # /jobs /jobs/taxonomy /jobs/{id} /jobs/detail/{id}
│   │   ├── visa.py                # /dashboard /sponsors /h1b/{employer} /search /classify
│   │   ├── alerts.py              # /alerts /alerts/settings (per-user)
│   │   ├── analytics.py           # /analytics/dashboard (REAL DATA ONLY — no mocks)
│   │   ├── contacts.py            # /contacts /import-csv /enrich-emails /debug/finalscout
│   │   ├── resume.py              # /resume/parse /score /upload /list /keywords
│   │   ├── match.py               # /match/score /match/batch
│   │   └── health.py              # /api/health
│   ├── db/
│   │   ├── local_db.py            # SQLiteClient — schema + jobs + h1b + contacts
│   │   ├── user_store.py          # User-scoped helpers: create_user, list_alerts, etc.
│   │   └── firebase.py            # Firestore alternative (not active by default)
│   ├── models/                    # Pydantic models per resource
│   ├── services/
│   │   ├── job_scraper.py         # Multi-source orchestrator (free/open defaults)
│   │   ├── job_filters.py         # country scope, parse_years(), is_entry_level()
│   │   ├── job_exporter.py        # Single rolling placeup_jobs.csv + xlsx
│   │   ├── h1b_excel_importer.py  # Loads H1b_US_DataLIst.xlsx → h1b_sponsors
│   │   ├── ats_scorer.py          # Resume quality scoring + LLM-based ATS
│   │   ├── resume_parser.py       # PDF/DOCX → text
│   │   ├── match_engine.py        # Hybrid match (TF-IDF + keywords + LLM)
│   │   ├── visa_classifier.py     # Title/JD → visa-friendliness signal
│   │   ├── contact_finder.py      # Multi-source recruiter discovery (free + BYOK)
│   │   ├── contact_csv_importer.py # CSV → contacts table; FinalScout/Hunter enrichment
│   │   ├── finalscout_enrichment.py # api.finalscout.com/v1/find/linkedin/single
│   │   ├── apollo_enrichment.py   # Apollo.io
│   │   ├── hunter_enrichment.py   # Hunter.io email-finder + verifier
│   │   ├── google_xray.py         # Google CSE LinkedIn site: search
│   │   ├── team_page_crawler.py   # Public company team page scraping
│   │   ├── github_miner.py        # GitHub commit metadata for engineering hires
│   │   ├── dol_lca_importer.py    # DOL LCA petitions for visa-sponsoring employers
│   │   └── h1b_sponsor_pipeline.py # Curated H1B sponsor → ATS board pipeline
│   └── utils/                     # text_processing, deduplication, terminal_table
├── data/
│   ├── placeup.db                 # SQLite database (~130 MB once H1B + contacts loaded)
│   ├── exports/                   # placeup_jobs.csv (single rolling file)
│   ├── resumes/<user_id>/         # uploaded resume blobs, used by ATS scorer
│   └── h1b/                       # legacy CSV exports
├── H1b_US_DataLIst.xlsx           # 24,363-row USCIS H1B petition data (bundled)
├── sample user.csv                # Recruiter import sample (LinkedIn URLs)
├── requirements.txt
└── .env                           # API keys (see §10)

frontend/
├── src/
│   └── app/
│       ├── App.tsx                # Root, wraps RouterProvider in dark mode
│       ├── routes.ts              # createBrowserRouter — Layout > Dashboard > pages
│       ├── lib/api.ts             # Single typed fetch client; bearer in localStorage
│       ├── context/AuthContext.tsx # signIn/signUp/signOut + getProfile on mount
│       ├── pages/
│       │   ├── Home.tsx           # Marketing landing (scrollytelling)
│       │   ├── SignIn.tsx         # Login + "Use demo account" button
│       │   ├── SignUp.tsx         # Account creation (NEEDS expansion — see §8)
│       │   └── Dashboard.tsx      # Sidebar + topbar + outlet for sub-pages
│       └── components/
│           ├── Layout.tsx         # ThemeContext, page transitions
│           ├── dashboard/
│           │   ├── ResumePage.tsx          # Upload + version mgmt + Quick Wins
│           │   ├── JobsPage.tsx            # Taxonomy sidebar + cards (real data)
│           │   ├── JobDetailPage.tsx       # Per-job view + ATS + contacts
│           │   ├── JobRoutes.tsx           # URL params → page props adapter
│           │   ├── VisaTrackerPage.tsx     # H1B search/table (23K rows)
│           │   ├── AlertsPage.tsx          # Per-user alert feed
│           │   ├── AnalyticsPage.tsx       # Recharts of resume score history
│           │   ├── SettingsPage.tsx        # Profile + preferences + password
│           │   └── UserProfilePage.tsx     # Profile view (skills are static — see §8)
│           └── ui/                # shadcn/ui primitives

PlaceUp/  (this folder — top-level docs)
├── INTEGRATION.md                 # Original wire-up guide (still mostly accurate)
├── GAP_REPORT.md                  # Original gap analysis (older)
├── SCRAPING_ROADMAP.md            # LinkedIn / FinalScout reality check
└── AGENT_CONTEXT.md               # ◄ THIS FILE — read first
```

---

## 5. Endpoints catalog

All endpoints are mounted under `/api/*`. JWTs go in
`Authorization: Bearer <token>`. Endpoints marked **🔒** require auth.

### Auth — `app/api/auth.py`
| Method | Path | Notes |
|---|---|---|
| POST | `/api/auth/signup` | Body: `{first_name, last_name, email, password, visa_status?, experience_level?, targets?}` |
| POST | `/api/auth/signin` | Self-heals demo account on demo creds |
| GET  | `/api/auth/demo` | Returns + ensures demo creds (dev only). Disabled in prod. |

### User — `app/api/user.py`
| Method | Path | Notes |
|---|---|---|
| 🔒 GET  | `/api/user/profile` | |
| 🔒 PUT  | `/api/user/profile` | Partial update; `id`/`email` ignored |
| 🔒 GET  | `/api/user/preferences` | |
| 🔒 PUT  | `/api/user/preferences` | |
| 🔒 PUT  | `/api/user/password` | `{current_password, new_password}` |
| 🔒 GET  | `/api/user/notifications` | Synthesized from latest alerts |
| 🔒 GET  | `/api/user/resumes` | |
| 🔒 POST | `/api/user/resumes/upload` | Multipart `file`; persists to `data/resumes/<uid>/` |
| 🔒 POST | `/api/user/resumes/{id}/activate` | |
| 🔒 DELETE | `/api/user/resumes/{id}` | |

### Jobs — `app/api/jobs.py`
| Method | Path | Notes |
|---|---|---|
| GET  | `/api/jobs/taxonomy` | 12 categories × 88 roles for filter UI |
| GET  | `/api/jobs` | Query: `search, location, source, visa_only, page, page_size, role, category, entry_level=true`. With JWT, each job carries a per-active-resume `match_score`. Returns plain dict (NOT `JobListResponse`) so `taxonomy_category` and `role` survive. |
| GET  | `/api/jobs/stats` | |
| POST | `/api/jobs/scrape` | Manual scrape trigger |
| GET  | `/api/jobs/export` | Writes `data/exports/placeup_jobs.csv` (atomic rewrite) |
| GET  | `/api/jobs/{id}` | Raw row |
| GET  | `/api/jobs/detail/{id}` | Decorated: taxonomy + ATS score + ≤3 contacts |

### Visa — `app/api/visa.py`
| Method | Path | Notes |
|---|---|---|
| GET  | `/api/visa/dashboard` | Top-25 sponsors + headline stats (uses real H1B data) |
| GET  | `/api/visa/sponsors` | Searchable, paginated. Query: `company, state, page, page_size` |
| GET  | `/api/visa/h1b/{employer}` | Per-employer record set |
| GET  | `/api/visa/search` | Live h1bdata.info salary + sponsor search |
| POST | `/api/visa/classify` | Body `{title, company, description}` → visa flags |
| GET  | `/api/visa/salary` | Aggregated H1B LCA salary stats |

### Alerts — `app/api/alerts.py`
All require auth. Backed by `user_alerts` and `user_alert_settings`.

| Method | Path |
|---|---|
| GET / POST / DELETE | `/api/alerts(...)` + per-id |
| PATCH | `/api/alerts/{id}/read` |
| POST | `/api/alerts/read-all` |
| GET / PUT | `/api/alerts/settings` |

### Analytics — `app/api/analytics.py`
| Method | Path | Notes |
|---|---|---|
| GET | `/api/analytics/dashboard` | **REAL DATA ONLY**. Per-user app count + resume score history. Returns empty arrays when the user has no data. |

### Contacts — `app/api/contacts.py`
| Method | Path | Notes |
|---|---|---|
| GET  | `/api/contacts` | Filter `company, job_id, source, limit` |
| GET  | `/api/contacts/stats` | Aggregates by source/confidence/company |
| POST | `/api/contacts/enrich` | Per-job recruiter discovery (free-first, BYOK) |
| POST | `/api/contacts/bulk-enrich` | Batch over many jobs |
| POST | `/api/contacts/contribute` | Crowdsourced submission |
| POST | `/api/contacts/draft-email` | Personalized outreach DRAFT (never sends) |
| POST | `/api/contacts/import-csv` | Ingest `sample user.csv` style sheet |
| POST | `/api/contacts/enrich-emails` | Fill missing emails via FinalScout → Hunter |
| GET  | `/api/contacts/debug/finalscout` | Probe FinalScout endpoint (diagnostic) |
| GET  | `/api/contacts/debug/finalscout-account` | Probe FinalScout account info |

### Resume / Match — `app/api/resume.py` and `app/api/match.py`
| Method | Path | Notes |
|---|---|---|
| POST | `/api/resume/parse` | PDF/DOCX → structured fields (LLM) |
| POST | `/api/resume/score` | Resume + JD → ATS score + keyword analysis |
| POST | `/api/resume/keywords` | Lighter keyword diff |
| POST | `/api/match/score` | Hybrid match (TF-IDF + keywords + LLM) |
| POST | `/api/match/batch` | Up to 20 jobs per call |

---

## 6. Data flows (the important ones)

### Sign-in flow
1. `POST /api/auth/signin` returns `{access_token, user_id, email, ...}`.
2. Frontend stores `access_token` in `localStorage["placeup_token"]`.
3. Every subsequent fetch sets `Authorization: Bearer <token>`.
4. Backend's `current_user_id` dependency decodes the JWT, injects
   `user_id` into the route handler.
5. `_seed_demo_user()` runs on startup; `/api/auth/demo` returns
   `demo@placeup.dev / Password123!` (dev only).

### Scrape cycle (Cloud Run every 6h)
1. Cloud Scheduler triggers the `placeup-job-scraper-6h` Cloud Run Job,
   which runs `app.etl.jobs_scraper_6h`.
2. The 6h job covers the current full taxonomy: 12 categories, 100 roles,
   and 533 scrape terms.
3. Scheduled production sources are free/open only: `usajobs`, `dice`,
   `h1b_sponsor`, and `tier1_ats`. Do not add paid LinkedIn providers or
   blocked anonymous aggregator scraping to this default path.
4. Public board terms are batched, then direct sponsor/ATS boards run once
   across all role names.
5. Records are staged, normalized, deduped, loaded into Cloud SQL/Postgres,
   and synced into `master_jobs`.
6. Visa classification and sponsor verification run on survivors.
7. `placeup-stale-jobs-sweeper` enforces the 30-day job snapshot retention
   window.
8. LinkedIn JD repair is a separate legacy cleanup worker for existing
   LinkedIn rows with thin descriptions or company=`LinkedIn`.

### Per-user ATS scoring on Jobs
1. Every `/api/jobs` call inspects the JWT.
2. If a user is logged in, `_active_resume_text(user_id)` reads the
   active resume blob from `data/resumes/<uid>/`, parses it.
3. For each job in the page, compute keyword overlap (`compute_keyword_overlap`).
4. Attach `match_score: int` to the response payload.
5. With `entry_level=true` (default), 0-5 yr roles bubble to the top.

### H1B import
- On startup, `import_h1b_excel(force=False)` reads
  `H1b_US_DataLIst.xlsx`, aggregates per (employer, city, state, FY),
  writes ~23,429 rows to `h1b_sponsors`. Skips if table already populated.

### Recruiter contact import
- `POST /api/contacts/import-csv` reads `sample user.csv` (or any
  path you pass), normalizes the messy "Last Name" column,
  auto-tags rows whose title matches "recruiter / talent / hr / hiring"
  as `role: "recruiter"`. Idempotent — same row → same id hash.
- `POST /api/contacts/enrich-emails` then fills missing emails via
  FinalScout → Hunter, in order, with the first hit per contact.

---

## 7. What WORKS today (verified end-to-end)

- ✅ Sign-up / sign-in / demo auto-seed.
- ✅ JWT-protected routes; password change.
- ✅ Job taxonomy: 12 categories, 100 roles, 533 scrape queries — single
  source of truth in `app/job_taxonomy.py`.
- ✅ Production free/open scheduled source policy.
- ✅ 0-5 yr experience bubbling to top of `/api/jobs`.
- ✅ Per-active-resume ATS scoring on every `/api/jobs` row.
- ✅ Visa Tracker: 23,429 real H1B records with search by company + state.
- ✅ Per-user alerts CRUD + settings.
- ✅ Resume upload persists to disk; subsequent ATS calls read it.
- ✅ Single rolling CSV + XLSX export (`placeup_jobs.csv`).
- ✅ No-cache headers on every `/api/*` response.
- ✅ FinalScout endpoint locked to verified live URL
  (`api.finalscout.com/v1/find/linkedin/single`, `linkedin_url` body).
- ✅ Contact CSV import (17 rows from sample) + recruiter auto-tagging.
- ✅ Contact discovery (free sources + BYOK paid) integrated into the
  scrape cycle (3 contacts per job, persisted with no duplicates).
- ✅ Frontend pages all bound to real endpoints (no mock fallbacks).
- ✅ Analytics returns real per-user data only (no synthetic series).

---

## 8. What's QUEUED / NOT YET DONE (open work)

These are the user's explicit asks that still need code. Pick any and run.

### ⏳ Signup form expansion (TASK #23)
The current `pages/SignUp.tsx` only takes first/last/email/password.
Needs to also collect:
- LinkedIn profile URL
- Years of experience (dropdown)
- Current position (text)
- Current company (text)
- Job preferences — pick **up to 5** role names from the
  `/api/jobs/taxonomy` payload (autocomplete or chip picker)
- Location preferences — pick multiple cities/regions
- Current visa status — dropdown:
  `F1 / F1-OPT / F1-STEM OPT / H-1B / O-1 / H-4 EAD / Green Card / US Citizen / Other`
- Resume upload (limit **1** during signup; replaces any prior)
- Current location (text or geocoded)

**Backend changes**:
- Extend `models/user.py::SignupRequest` with the new fields.
- Add `linkedin_url`, `current_role`, `current_company` to the
  `users` table (already has `linkedin_url`, `current_role`).
- Extend `user_preferences` to accept a JSON list of `target_roles`
  (≤5) and `target_locations`.
- The signup route should optionally accept a multipart resume in
  the same request (or do a follow-up PUT immediately after).

### ⏳ Dynamic resume Quick Wins + Profile Skills (TASK #24)
- The Resume page currently has hard-coded "Quick Wins" tips
  (e.g. "Add 'React 18' instead of just 'React'"). Make these dynamic:
  diff the user's parsed resume vs. their job preferences (or vs.
  the active job's JD) and surface the missing keywords as the tips.
- The Profile page has a hard-coded skills list. Replace it with the
  `skills` array from the parsed resume (`ats_scorer.parse_resume_with_llm`
  already extracts a structured skills list; surface it via a new
  `GET /api/user/resume/parsed` endpoint).

### Other open improvements (good to have)
- **`user_applications` lifecycle**: table exists, no endpoint yet
  records "Applied" actions. Wire the "Apply" button to
  `POST /api/applications` so the analytics page eventually shows
  real time-series.
- **Dashboard `OverviewPage.ACTIVITY`** is still a hard-coded
  array. Derive from real alerts + applications.
- **Per-cycle alert dispatch**: when a new scraped job has a high
  match score for a user, auto-create an alert. The pipeline
  exists but the bridge isn't built.
- **Workday / Lever direct ingestion**: aggregator coverage works
  for most cases; direct careers-page scraping is the long tail.
- **Tier-1 H1B sponsor recruiter pull**: one-shot job that runs
  enrichment over the top 500 H1B sponsors by petition volume
  (limited by API budgets — see `SCRAPING_ROADMAP.md`).
- **Email send**: `draft-email` returns a draft only; the user has
  to copy/paste. Goal mentions Gmail API via Workspace.
- **Firestore parity**: `user_store.py` is SQLite-only. The same
  interface needs a Firestore implementation for prod.

---

## 9. KNOWN bugs / gotchas

1. **Windows ↔ Linux mount sync**: this dev environment edits files
   via a Linux mount that occasionally lags behind the Windows side.
   Symptom: `Scheduler not started: unexpected indent (job_scraper.py, line 742)`
   when the Windows file has stale extra lines. **Fix**: open the
   complaining file in your editor and Ctrl-S to force a re-save,
   plus `Get-ChildItem -Recurse -Filter __pycache__ | Remove-Item -Recurse`
   to clear stale `.pyc`. Then restart `uvicorn`.
2. **`JobListResponse` enum strictness**: the legacy `JobCategory` enum
   doesn't match the taxonomy names. The `/api/jobs` route returns a
   plain dict (no `response_model=`) so `taxonomy_category` and `role`
   survive. **Don't re-add `response_model=JobListResponse`** — it
   strips unknown fields.
3. **bcrypt 4.x + passlib**: passlib 1.7 reads `bcrypt.__about__` which
   doesn't exist in bcrypt 4. We bypass passlib and call `bcrypt`
   directly. **Don't reintroduce passlib.**
4. **JWT_SECRET defaults to a placeholder**. **Production deploys
   MUST override** (`openssl rand -hex 32`).
5. **API keys in chat history** (Hunter + FinalScout) — the user
   pasted these once. They should be rotated and only stored in
   `backend/.env` going forward.
6. **`__pycache__` is read-only on the Linux mount** — can't `rm` it
   from this side. Stale `.pyc` files cause Windows uvicorn to load
   old code; clean from the Windows side.

---

## 10. Configuration (`backend/.env`)

```
# Server
APP_ENV=development
APP_PORT=8000
FRONTEND_URL=http://localhost:5173

# Auth — REQUIRED in production
JWT_SECRET=<64-char hex from `openssl rand -hex 32`>
JWT_EXPIRES_MINUTES=10080   # 7 days

# Database
DATABASE_BACKEND=sqlite     # or 'firestore'

# Scrape behavior
SCRAPE_INTERVAL_HOURS=8
JOB_INACTIVE_AFTER_DAYS=12
SCRAPE_MAX_CONCURRENCY=28

# LLM (optional — used by ats_scorer for richer parsing)
GROQ_API_KEY=
OPENAI_API_KEY=
LLM_PROVIDER=groq
LLM_MODEL=llama-3.3-70b-versatile

# Job scraper extras
RAPIDAPI_KEY=
USAJOBS_API_KEY=
USAJOBS_EMAIL=
GREENHOUSE_BOARD_TOKENS=    # comma-separated tokens

# Contact enrichment — fill any of these to light up the pipeline
APOLLO_API_KEY=
HUNTER_API_KEY=
FINALSCOUT_API_KEY=
SERPAPI_KEY=
GOOGLE_API_KEY=             # for Google CSE LinkedIn x-ray
GOOGLE_CSE_ID=
```

`frontend/.env.local` — optional. When `VITE_API_BASE` is empty,
requests use relative paths and Vite's dev proxy forwards them.

---

## 11. Run locally

### Backend
```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
cp .env.example .env  # fill in JWT_SECRET at minimum
uvicorn app.main:app --reload --port 8000
```

Expected boot log:
```
INFO  PlaceUp Career Backend starting up...
INFO  SQLite database initialized
INFO  Demo user already present: demo@placeup.dev   (or "Seeded demo user" first time)
INFO  H1B: imported 23429 sponsor records (or "already populated")
INFO  Scheduler configured (interval: 8h)
INFO  Application startup complete.
```

### Frontend
```powershell
cd frontend
npm install
npm run dev   # http://localhost:5173
```

### Sign in
- Email: `demo@placeup.dev`
- Password: `Password123!`
- Or click **"Use demo account"** on the SignIn page.

---

## 12. How the scheduler is supposed to behave

When working correctly, every 8 hours you should see in the log:

```
Background Scrape: Stored N new jobs
Background Scrape: Exported {'csv': '...', 'xlsx': '...'}
Background Scrape: Deactivated K stale jobs
Background Scrape: Persisted M contacts across J jobs
Geo-filtered Q non-US/CA jobs from R scraped
```

If you don't see "Scheduler configured" on startup, **the scheduler
didn't start** and Jobs page will stay empty forever. Check the file
sync issue in §9 #1.

---

## 13. How to extend (recipe per common task)

### Add a new job role to the taxonomy
1. Edit `app/job_taxonomy.py` — add a new `Role` to the relevant
   `Category`'s `roles` tuple. Include `synonyms` (used as scrape
   queries AND for matching incoming job titles to this role) and
   `visa` tags.
2. Restart backend. The frontend `/api/jobs/taxonomy` endpoint and
   the JobsPage sidebar pick it up automatically.

### Wire a new contact-enrichment provider
1. Add an `_enrichment.py` service in `app/services/` that exposes
   an async `find_email_by_*` returning a `Contact` model.
2. Hook it into `enrich_missing_emails` in `contact_csv_importer.py`
   (or `find_contacts` in `contact_finder.py` for the per-job path).
3. Add the `*_API_KEY` setting to `app/config.py` and `.env.example`.

### Add a new dashboard page
1. Create `frontend/src/app/components/dashboard/MyPage.tsx`.
2. Register the route in `frontend/src/app/routes.ts` under the
   `/dashboard` children.
3. If it needs sidebar nav, add to `NAV_ITEMS` in `Dashboard.tsx`.
4. Use `import * as api from "../../lib/api"` and add typed methods
   to `lib/api.ts` for any new backend calls.

### Test an endpoint without the frontend
- FastAPI auto-generates a Swagger UI at http://localhost:8000/docs.
- Click any endpoint → "Try it out" → "Execute".

### Probe FinalScout if it stops returning emails
```powershell
curl.exe "http://localhost:8000/api/contacts/debug/finalscout?linkedin_url=https://www.linkedin.com/in/<slug>"
```

---

## 14. Where docs live

- **AGENT_CONTEXT.md** ← this file (start here)
- **INTEGRATION.md** — original integration guide
- **GAP_REPORT.md** — older state-of-app analysis
- **SCRAPING_ROADMAP.md** — LinkedIn / FinalScout reality check
- **context.md** — project architecture overview (older)
- **agents.md** — AI agent instructions
- **anti-patterns.md** — common mistakes to avoid in this codebase
- **backend-pipeline.md** — original GCP architecture intent
- **component-registry.md** — component props/state catalog
- **guidelines.md** — design system + dev guidelines
- **skills.md** — copy-paste component patterns

---

## 15. Production data path (Postgres + ETL + GCP) — added 2026-05-10

The repo now contains a **dual-backend** data architecture: SQLite stays
the local dev fallback (zero setup, works offline), while a parallel
PostgreSQL + ETL pipeline is the production target.

### What's new on disk

```
backend/
├── alembic.ini                      # Alembic config (sqlalchemy.url points at local Postgres)
├── docker-compose.yml               # `docker compose up -d postgres` → local DB
├── migrations/                      # Alembic migration scripts
│   ├── env.py
│   ├── script.py.mako
│   └── versions/                    # auto-generated migrations live here
├── ETL_BACKEND.md                   # production-shape doc
├── deploy/                          # GCP deployment scripts (PowerShell)
│   ├── setup_gcp.ps1                # provision Cloud SQL + Artifact Registry + secrets
│   ├── deploy_backend.ps1           # build + push + deploy Cloud Run service
│   ├── run_migrations.ps1           # alembic upgrade head against Cloud SQL
│   ├── schedule_jobs.ps1            # Cloud Scheduler → Cloud Run jobs (6h scrape, 12h external API)
│   └── cloudrun-api.yaml            # Cloud Run service manifest
└── app/etl/                         # ETL pipeline (NEW — replaces direct DB writes from scrapers)
    ├── run_manager.py               # writes ingest_runs metrics
    ├── jobs_scraper.py              # CLI: python -m app.etl.jobs_scraper --queries "..."
    ├── external_api_ingest.py       # CLI: external API → staging → normalize → upsert
    ├── sources/                     # provider clients (one per board / API)
    ├── normalizers/                 # raw payload → canonical job/contact/company shape
    │   └── jobs.py
    └── loaders/                     # canonical → final tables (idempotent upsert)
        └── jobs.py
```

### How data flows in production

```
provider (LinkedIn, Indeed, USAJobs, Greenhouse, Apollo, …)
  → app/etl/sources/<provider>.py        (fetch raw)
  → staging_records                       (raw provider payload, full fidelity)
  → app/etl/normalizers/<entity>.py       (normalize to canonical shape)
  → normalized_payload                    (canonical job/contact/company)
  → app/etl/loaders/<entity>.py           (idempotent upsert to final tables)
  → companies / jobs / contacts           (final, deduplicated)
  → app/etl/run_manager.py                (write metrics to ingest_runs)
```

The contract is strict: **scrapers never write directly to final tables.**
Every record passes through `staging_records` first so we have full
provenance (which provider, when, raw payload) and can replay normalization
without re-fetching.

### Running the ETL locally

```powershell
cd backend
docker compose up -d postgres                     # spin up local Postgres
$env:DATABASE_BACKEND="postgres"
$env:DATABASE_URL="postgresql+psycopg://placeup:placeup_dev@localhost:5432/placeup"
alembic upgrade head                              # apply migrations
python -m app.etl.jobs_scraper --dry-run --queries "software engineer" --max-per-source 10
python -m app.etl.jobs_scraper --queries "software engineer" --max-per-source 10
uvicorn app.main:app --reload --port 8000
```

When `DATABASE_BACKEND=postgres` is unset (or `=sqlite`), the existing
SQLite path under `backend/data/placeup.db` keeps working — useful for
quick local dev without Docker.

### Deploying to GCP

```powershell
cd backend
.\deploy\setup_gcp.ps1 -ProjectId YOUR_PROJECT_ID -DbPassword "STRONG_PASSWORD"
.\deploy\deploy_backend.ps1 `
  -ProjectId steel-shine-492401-u6 `
  -Region us-east1 `
  -DbInstance placeup-backend `
  -UserDatabaseBackend firestore `
  -UserFirestoreProjectId placeup-firebase-641222668282 `
  -UserFirestoreDatabase "(default)" `
  -FrontendUrl "https://placeup-frontend-76tybrmgya-ue.a.run.app"
.\deploy\run_migrations.ps1 -ProjectId steel-shine-492401-u6 -Region us-east1 -DbInstance placeup-backend
.\deploy\schedule_jobs.ps1 -ProjectId steel-shine-492401-u6 -Region us-east1 -TimeZone America/Chicago
```

Run `deploy_backend.ps1` from `backend/`, not from the repo root. The backend
Dockerfile lives in `backend/`; running the script from the wrong directory can
skip the image build and redeploy an old `latest` image.

`setup_gcp.ps1` creates:
- Cloud SQL Postgres instance + database + user
- Artifact Registry repo for the container image
- Service accounts with least-privilege IAM
- Secret Manager entries for `JWT_SECRET`, `DATABASE_URL`

Provider API keys (FinalScout, Hunter, Apollo, Groq, etc.) are added
to Secret Manager **after** initial setup — see `ETL_BACKEND.md`.

`schedule_jobs.ps1` wires Cloud Scheduler to two Cloud Run *jobs* (not
the API service):
- `placeup-job-scraper-6h` — every 6h, runs `app.etl.jobs_scraper`
- `placeup-external-api-12h` — every 12h, runs `app.etl.external_api_ingest`

The API service stays up continuously and serves requests. Heavy ETL
runs in batch jobs so the API never slows down during a scrape.

### Current production scraper behavior

As of 2026-05-28, production scraping uses the Cloud Run job
`placeup-job-scraper-6h` with entrypoint `python -m app.etl.jobs_scraper_6h`.
It covers the full current taxonomy: 12 categories, 100 roles, and 533 scrape
terms. The old "64 batches" number came from 255 focused backfill terms divided
into groups of 4; it was not the number of jobs or roles.

Default production scraping is free/open-source only. The 6-hour scheduled
pipeline does not use paid LinkedIn providers or broad anonymous aggregator
scraping that commonly blocks Cloud Run. Current scheduled sources are
`usajobs`, `dice`, `h1b_sponsor`, and `tier1_ats`.

Future global ingestion sources must follow the same rule: official government
APIs/downloads, EURES, or public company ATS JSON endpoints. Do not add
Fantastic.jobs, paid LinkedIn pulls, or blocked aggregator scraping to the
default scheduled pipeline.

Production uses:

- `SCRAPER_PUBLIC_BATCH_CONCURRENCY=8`
- `SCRAPER_ROLE_BATCH_SIZE=4`
- `SCRAPE_MAX_CONCURRENCY=10`
- `SCRAPEGRAPH_DISCOVERY_MAX_URLS=220`
- `JOB_RETENTION_DAYS=30`
- Cloud Run job `--max-retries=0`

`jobs_scraper_6h.py` takes a Postgres advisory lock at startup. If Scheduler
fires while a manual scrape is still active, the second run exits successfully
instead of overlapping and flooding public boards.
Retries are disabled for the 6-hour scraper job so public-board failures do not
create a second long-running Cloud Run retry that holds the lock.

Manual run:

```powershell
gcloud run jobs execute placeup-job-scraper-6h `
  --region us-east1 `
  --project steel-shine-492401-u6
```

Check status:

```powershell
gcloud run jobs executions list `
  --job placeup-job-scraper-6h `
  --region us-east1 `
  --project steel-shine-492401-u6 `
  --limit=5
```

Check batch summaries:

```powershell
gcloud logging read 'resource.type="cloud_run_job" AND resource.labels.job_name="placeup-job-scraper-6h" AND textPayload:"Fetched"' `
  --project steel-shine-492401-u6 `
  --limit=20 `
  --format='value(timestamp,textPayload)'
```

After a scrape, run the live repair and retention jobs:

```powershell
gcloud run jobs execute placeup-linkedin-jd-repair --region us-east1 --project steel-shine-492401-u6 --wait
gcloud run jobs execute placeup-stale-jobs-sweeper --region us-east1 --project steel-shine-492401-u6 --wait
```

If `gcloud` says reauthentication failed, run `gcloud auth login` and confirm
the active account is `operations@placeupcareer.com`.

### Adding a new ETL source — recipe

1. Create `backend/app/etl/sources/<provider>.py` with an async
   `fetch(query, max_results) -> list[dict]` that returns raw provider
   payloads.
2. Create or extend a normalizer in
   `backend/app/etl/normalizers/<entity>.py` to shape the payload into
   the canonical format used by `loaders/`.
3. Create or extend a loader in `backend/app/etl/loaders/<entity>.py`
   for the upsert logic against the final table.
4. Wire a CLI entry point in `app/etl/jobs_scraper.py` or
   `app/etl/external_api_ingest.py` so Cloud Scheduler can trigger it.
5. If the source needs an API key, add it to `app/config.py` and to
   the GCP `secrets create` block in `deploy/setup_gcp.ps1`.

### What's still SQLite-only

The user-facing tables (`users`, `user_resumes`, `user_alerts`,
`user_preferences`, `user_alert_settings`, `user_applications`) currently
live in `local_db.py`'s SQLite schema. To go full-Postgres, port these
into Alembic migrations and into the SQLAlchemy session under
`backend/app/db/postgres.py` (not yet created — see `ETL_BACKEND.md` for
the planned shape).

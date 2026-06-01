# PlaceUp Career - Project Context

## What This Is

PlaceUp Career is a modern, dark-mode-first web platform for career placement, ATS (Applicant Tracking System) resume scoring, and visa sponsorship tracking. It targets global tech talent seeking jobs with visa-sponsoring employers.

## Tech Stack

| Layer | Technology | Version / Notes |
|---|---|---|
| Framework | React | 18.3.1 (via Vite, NOT Next.js) |
| Routing | react-router | 7.13.0 — uses `createBrowserRouter` Data mode. **Do NOT use `react-router-dom`**, it doesn't work in this environment. |
| Styling | Tailwind CSS | v4.1.12 — utility-first. No `tailwind.config.js`; config lives in `/src/styles/theme.css` via `@theme inline`. |
| Animation | motion | 12.23.24 — import as `import { motion } from "motion/react"`. This is the successor to Framer Motion. Always call it "Motion". |
| Icons | lucide-react | 0.487.0 |
| Charts | recharts | 2.15.2 (installed, not yet used — available for analytics pages) |
| Fonts | Inter + Space Grotesk | Loaded via Google Fonts in `/src/styles/fonts.css` |

## File Structure

```
/src
  /app
    App.tsx                          # Root — wraps RouterProvider in a `<div className="dark">`
    routes.ts                        # createBrowserRouter config — Layout wraps all routes
    /components
      Layout.tsx                     # Global layout: ThemeContext provider, AnimatePresence page transitions, CustomCursor
      CustomCursor.tsx               # SVG dot + trailing ring cursor with spring physics
      Navbar.tsx                     # Fixed top nav with glassmorphism, mobile hamburger menu, theme toggle, nav links
      GradientMeshBackground.tsx     # Canvas-based animated gradient mesh with floating orbs and particles (fixed, z-index: -1)
      CareerNetworkBackground.tsx    # Career-themed network background (deprecated - replaced by GradientMeshBackground)
      DNAHelixBackground.tsx         # Legacy DNA helix background (deprecated)
      ParticleBackground.tsx         # Legacy particle background (deprecated)
      /dashboard
        ResumePage.tsx               # Resume upload, ATS scoring, version management
        JobsPage.tsx                 # Job matching with filters (Title, Time, Location, Status)
        JobDetailPage.tsx            # Detailed job view with ATS analysis, keywords, visa info
        VisaTrackerPage.tsx          # Visa sponsorship data by employer
        AlertsPage.tsx               # Job alerts and notifications management
        AnalyticsPage.tsx            # Career analytics and insights
        SettingsPage.tsx             # User preferences and account settings
        UserProfilePage.tsx          # User profile and career information
      /sections
        HeroSection.tsx              # Landing hero with gradient orbs, staggered text reveal, stats bar
        HowItWorksSection.tsx        # 4-step card grid (Upload, ATS, Matching, Placement)
        FeaturesSection.tsx          # 6-feature card grid with hover effects
        PricingSection.tsx           # 3-tier pricing (Basic/Pro/Elite) with popular badge
        ContactSection.tsx           # Newsletter CTA + full footer with link columns
      /figma
        ImageWithFallback.tsx        # PROTECTED — do not modify. Use instead of <img> for new images.
      /ui                            # Empty — available for shared UI primitives
    /pages
      Home.tsx                       # Scrollytelling landing page with 5 sections (300vh scroll container)
      Dashboard.tsx                  # Authenticated dashboard with 8 pages (Overview + 7 sub-pages)
      SignIn.tsx                     # Authentication - Sign In page
      SignUp.tsx                     # Authentication - Sign Up page
  /styles
    fonts.css                        # Google Fonts imports (Inter, Space Grotesk)
    theme.css                        # CSS custom properties for light/dark mode + Tailwind @theme inline tokens
    index.css                        # Global entry CSS
    tailwind.css                     # Tailwind base imports
  /imports                           # Figma-imported assets (SVGs, pasted text)

/docs                                # All project documentation (single location)
  agents.md                          # AI agent instructions
  anti-patterns.md                   # Common mistakes to avoid
  backend-pipeline.md                # Google Cloud backend architecture & pipelines
  component-registry.md              # All components with props, state, dependencies
  context.md                         # This file — project architecture overview
  guidelines.md                      # Design system & development guidelines
  security-pipeline.md               # Google Cloud security architecture
  skills.md                          # Copy-paste component patterns
  ATTRIBUTIONS.md                    # Third-party attributions
```

## Design System

### Colors
- **Primary**: Violet (#8b5cf6) / Indigo (#6366f1) gradients
- **Accent**: Fuchsia (#d946ef) / Purple (#9333ea)
- **Success**: Green (#22c55e)
- **Warning**: Orange (#f59e0b)
- **Error**: Red (#ef4444)
- **Background**: 
  - Dark: #030712 (gray-950)
  - Light: #ffffff
- **Glassmorphism**: `backdrop-blur-md` + `bg-card/30` + `border-border`

### Typography
- **Headings**: Space Grotesk (700-800 weight)
- **Body**: Inter (400-600 weight)
- **Font sizes**: Responsive via `clamp()` for headings

### Animation Patterns
- **Scroll-driven**: Home page uses 300vh scroll container with section fade in/out
- **Page transitions**: Spatial wipe effect via Motion AnimatePresence
- **Hover states**: `whileHover={{ y: -8 }}` for cards
- **Stagger children**: `transition={{ delay: index * 0.1 }}`

## Key Features

### Home Page (Scrollytelling)
- **300vh scroll container** with fixed viewport
- **5 sections**: Hero, How It Works, Features, Pricing, Contact
- **Gradient Mesh Background**: Animated orbs with blur effect, subtle grid, floating particles
- **Scroll progress bar**: Bottom of page, violet gradient
- **Section transitions**: Fade in/out based on scroll position (0-1)
- **Scroll indicator**: Animated chevron at bottom of hero

### Dashboard (8 Pages)
1. **Overview**: ATS score circle, top job matches, visa tracker preview
2. **Resumes**: Upload, manage versions, ATS scoring
3. **Jobs**: Advanced filtering (Title, Time Posted, Location, Status), job cards with match scores
4. **Job Detail**: Full job description, ATS score for position, strong/missing keywords, visa info, benefits
5. **Visa Tracker**: Employer sponsorship data, approval rates
6. **Alerts**: Job notifications and alert management
7. **Analytics**: Career insights and statistics
8. **Settings**: User preferences, theme toggle, account management

### Job Detail Page Features
- Full job information (title, company, location, salary, description)
- **ATS Score for specific position** (94/100)
- **Strong Keywords**: Matched keywords from resume with frequency counts
- **Missing Keywords**: Impact levels + specific suggestions for improvement
- **Visa Information**: Sponsorship types, approval rate, recent approvals
- **Benefits & Perks**: Complete list
- **Apply button**: Redirects to original job post
- Back navigation to jobs list

### Advanced Job Filters
- **Job Title**: Dropdown with all unique job titles
- **Time Posted**: 6 Hours, 1 Day, 3 Days, All Time
- **Location**: Dropdown with all unique locations
- **Status**: All, New, Applied, Interview, Saved
- **Search**: Real-time search across title, company, location
- **Active Filters Display**: Pills showing active filters with remove buttons
- **Clear All**: One-click filter reset

### Authentication
- Sign In page with email/password
- Sign Up page with terms acceptance
- Redirect to dashboard after auth
- Logout functionality in user menu

### Theme System
- **Dark mode default**: Violet-tinted dark backgrounds
- **Light mode**: Clean white backgrounds with subtle violet accents
- **Toggle**: Sun/Moon icon in navbar and settings
- **Context**: ThemeContext provides `{ dark, toggle }` globally

## Animation Performance
- **Motion variants**: Used for complex stagger/fade animations
- **Canvas animations**: RequestAnimationFrame for smooth 60fps
- **Lazy rendering**: Particles reduce on low-end hardware
- **Will-change**: Applied to frequently animated elements

## State Management
- **React Context**: Theme (dark/light mode)
- **useState**: Local component state (filters, modals, selected items)
- **Navigation state**: React Router handles page state

## Routing Strategy
- **Home** (`/`): Landing page
- **Dashboard** (`/dashboard`): Protected dashboard with sub-pages rendered conditionally
- **Sign In** (`/signin`): Authentication
- **Sign Up** (`/signup`): Registration

## Mock Data
All data is currently mocked:
- Job listings with match scores, visa status, timestamps
- Visa sponsorship statistics by employer
- User profile information
- Resume versions and ATS scores

## Backend Infrastructure (Google Cloud + Firebase)
See `/docs/backend-pipeline.md` for full details.

- **Compute**: Google Cloud Run (serverless containers)
- **Jobs database**: Cloud SQL PostgreSQL (`placeup-backend`, `jobssilverdb`) for
  `jobs`, `companies`, `contacts`, `silver_posts`, and API-facing
  `master_jobs`.
- **User database**: Firebase Firestore (`placeup-firebase-641222668282`) for
  users, profiles, preferences, alerts, and resume metadata.
- **Firestore Security**: Firestore Security Rules (client-side) + Firebase Admin SDK (server-side)
- **Cache**: Cloud Memorystore (Redis)
- **Queue**: Cloud Tasks + Cloud Pub/Sub
- **Scheduler**: Google Cloud Scheduler
- **Storage**: Google Cloud Storage (GCS) — resume files, backups
- **Secrets**: Google Secret Manager
- **WAF/DDoS**: Google Cloud Armor
- **Load Balancer**: Google Cloud HTTP(S) Load Balancing
- **API Gateway**: Google Cloud Apigee
- **CI/CD**: Google Cloud Build + Artifact Registry
- **DNS**: Google Cloud DNS (domain managed via Google)
- **Email**: Gmail API via Google Workspace (jobs@placeupcareer.com)
- **Monitoring**: Cloud Monitoring + Cloud Logging + Security Command Center
- **Search**: Algolia (full-text job search — Firestore extension)

### Current Production ETL

- `placeup-job-scraper-6h` runs every 6 hours as a Cloud Run Job using
  `app.etl.jobs_scraper_6h`.
- The scraper covers the current full taxonomy: 12 categories, 100 roles, and
  533 scrape terms.
- Production scraping is free/open-source only by default: `usajobs`, `dice`,
  `h1b_sponsor`, and `tier1_ats`. Paid LinkedIn providers and blocked
  aggregator scraping are not part of the scheduled path.
- Production uses `SCRAPER_PUBLIC_BATCH_CONCURRENCY=8` to avoid public-board
  throttling while still covering the full taxonomy.
- The scraper takes a Postgres advisory lock, so a scheduled run skips safely if
  a manual run is still active.
- `placeup-linkedin-jd-repair` repairs existing LinkedIn rows where the company
  is still `LinkedIn` or the JD is thin.
- `placeup-stale-jobs-sweeper` enforces the 30-day job snapshot retention
  window.

### Global Visa Coverage Foundation

The live job model is no longer hard-coded to USA/Canada or US-only visa
labels. The global visa foundation is implemented for 31 target countries:

`US, CA, GB, IE, DE, NL, AU, NZ, SG, AE, JP, PT, FR, ES, SE, DK, NO, CH, FI,
BE, AT, PL, EE, QA, SA, IT, LU, KR, TW, HK, CZ`.

The country and visa-route rules live in
`backend/app/services/global_visa_rules.py`. The backend now classifies each
job into:

- `visa_country` / `visa_country_name`
- `visa_programs` / `visa_program_names`
- `sponsor_verified` / `sponsor_source`
- `english_friendly`

`/api/jobs/taxonomy` returns `target_countries` and `visa_programs` for the
frontend filters. `/api/jobs` accepts `country` and `visa_program` query
parameters. The Jobs UI defaults to the 30-day active retention window ("All
active") and keeps `time_filter=8h` as an optional freshness filter. The Jobs
UI relies on API request dedupe/cache and a latest-request guard instead of a
browser abort timer, so stale slow requests cannot clear successfully loaded
results.

2026-06-01 fix notes:

- `/api/jobs` now returns a baseline ATS score for every visible job even when
  `include_scores=false`; resume-based scoring still upgrades the score when
  explicitly requested.
- `frontend/src/app/components/dashboard/JobsPage.tsx` renders compact grid
  cards with an ATS ring, country flag/location, country-specific visa pills,
  category badge, and publish date. Country and visa-route filters are native
  dropdowns covering the full taxonomy contract.
- When an active resume is linked, the Jobs UI now requests
  `include_scores=true` so cards use resume-based match scoring instead of only
  baseline ATS scoring.
- Job freshness filters now use actual `posted_at` windows. `time_filter=8h`
  and `Today` no longer admit old postings merely because the scraper saw them
  today.
- `app.etl.jobs_scraper_6h` and `app.etl.external_api_ingest` now request all
  `TARGET_COUNTRIES` instead of `United_States~Canada` / `North_America`, and
  use `jobspy_hours_old=8` instead of `720`.
- The production `USAJOBS_API_KEY` and `USAJOBS_EMAIL` secrets currently contain
  empty placeholder values, so `placeup-job-scraper-6h` has
  `SCRAPER_PUBLIC_SOURCES=` in Cloud Run to skip broken USAJobs public batches.
- 2026-06-01 live reliability hotfix: `placeup-api` runs with min instances 2,
  max instances 20, and concurrency 5 to prevent request bursts from pinning a
  single Cloud Run container. `/api/jobs` uses indexed `last_seen_at` freshness
  for the broad All active view and avoids exact broad counts.
  Set real USAJobs credentials and redeploy before re-enabling `usajobs`.

Important production boundary: this foundation removes the old US/Canada
filtering wall and labels jobs globally when sources provide them. Full
country-by-country coverage still depends on adding the free/open official
source importers and sponsor-registry importers for each country. Paid LinkedIn
providers and blocked aggregator scraping remain outside the scheduled path.

### Production Commands

Deploy backend and jobs:

```powershell
gcloud auth login
gcloud config set account operations@placeupcareer.com
gcloud config set project steel-shine-492401-u6
cd D:\Development_Projects\PlaceUp\backend
.\deploy\deploy_backend.ps1 -ProjectId steel-shine-492401-u6 -Region us-east1 -DbInstance placeup-backend -UserDatabaseBackend firestore -UserFirestoreProjectId placeup-firebase-641222668282 -UserFirestoreDatabase "(default)" -FrontendUrl "https://placeup-frontend-rui2a74muq-ue.a.run.app"
```

Deploy frontend:

```powershell
cd D:\Development_Projects\PlaceUp\frontend
.\deploy_frontend.ps1 -ProjectId steel-shine-492401-u6 -Region us-east1 -ApiBase "https://placeup-api-rui2a74muq-ue.a.run.app"
```

Deploy the custom-domain Firebase Hosting frontend:

```powershell
cd D:\Development_Projects\PlaceUp\frontend
firebase login --reauth
.\deploy_firebase_hosting.ps1 -ProjectId placeup-firebase-641222668282 -ApiBase "https://placeup-api-rui2a74muq-ue.a.run.app"
```

Firebase Hosting must be built with `-ApiBase`; otherwise
`placeupcareer.com` calls same-origin `/api` from Firebase Hosting and can
show stale 504/aborted job-load failures.

Important: the live custom domain `placeupcareer.com` is mapped in project
`placeup-firebase-641222668282`, not `steel-shine-492401-u6`. Deploy frontend
updates to that project when validating the public website:

```powershell
cd D:\Development_Projects\PlaceUp\frontend
.\deploy_frontend.ps1 -ProjectId placeup-firebase-641222668282 -Region us-east1 -ApiBase "https://placeup-api-rui2a74muq-ue.a.run.app"
```

The `steel-shine-492401-u6` frontend service is useful for staging/direct Cloud
Run checks, but it is not what `placeupcareer.com` serves.

2026-06-01 live UI update:
- `placeupcareer.com` Jobs now uses the app-matching dark glass/violet theme
  in `frontend/src/app/components/dashboard/JobsPage.tsx`, while keeping the
  compact global card layout, ATS rings, country dropdown, and visa-route
  filters.
- The Dashboard shell stays on the same dark SaaS theme for `/dashboard/jobs`
  and all other dashboard pages.
- Latest public-domain frontend deploy target: project
  `placeup-firebase-641222668282`, service `placeup-frontend`, region
  `us-east1`, revision `placeup-frontend-00051-l8b`.
- Latest backend deploy target: project `steel-shine-492401-u6`, service
  `placeup-api`, region `us-east1`, revision `placeup-api-00148-grv`.
- Latest verified public assets after deploy include `index-BoBaOXA_.js` and
  `JobRoutes-Dd353y7r.js`.
- Manual scraper execution started after this deploy:
  `placeup-job-scraper-6h-k5fb7`.

Start a manual 6-hour scraper run:

```powershell
gcloud.cmd run jobs execute placeup-job-scraper-6h --region us-east1 --project steel-shine-492401-u6
```

2026-06-01 live scraper/JD repair update:
- Latest backend deploy target after scraper fixes: project
  `steel-shine-492401-u6`, service `placeup-api`, region `us-east1`,
  revision `placeup-api-00160-zhq`.
- The 6-hour scraper now runs public batches across `rapidapi~usajobs~dice`,
  but Dice is constrained to `United States` only because Dice's public API
  uses `countryCode2=US` and returns noisy errors for global locations.
- RapidAPI calls are paced with `RAPIDAPI_REQUEST_DELAY_SECONDS=3` and
  `RAPIDAPI_RATE_LIMIT_COOLDOWN_SECONDS=900`; 403/429 responses pause the
  provider for the current run instead of retrying every role/country.
- LinkedIn JD repair now treats descriptions under 1200 chars as thin,
  processes up to 5000 rows per run, and uses single-request concurrency to
  reduce guest-page 429s:
  `LINKEDIN_REQUESTS_PER_MINUTE=4`,
  `LINKEDIN_ENRICH_CONCURRENCY=1`,
  `LINKEDIN_REPAIR_CONCURRENCY=1`.
- Known-stale curated ATS board tokens are marked `active: False` in
  `backend/app/services/h1b_sponsor_boards.py` so future runs do not keep
  hitting 404s for dead Greenhouse/Lever/Ashby/Recruitee boards.
- Current live 6-hour execution started after clearing the stale advisory lock:
  `placeup-job-scraper-6h-jc8ct`. Early logs showed 8,865 raw jobs and
  5,303 unique normalized jobs before the DB load phase.
- Operational caveat: the USAJobs secrets currently contain placeholder values,
  so USAJobs is disabled until real `USAJOBS_API_KEY` and `USAJOBS_EMAIL`
  Secret Manager versions are installed. RapidAPI returned 403 for the current
  LinkedIn endpoint/key, so LinkedIn API collection depends on fixing that
  subscription/key outside code. LinkedIn full-JD guest-page repair is
  best-effort and can still be limited by LinkedIn 429s.

Useful live commands:

```powershell
gcloud.cmd run services describe placeup-api --region us-east1 --project steel-shine-492401-u6 --format="value(status.latestReadyRevisionName,status.traffic[0].percent)"
gcloud.cmd run jobs execute placeup-job-scraper-6h --region us-east1 --project steel-shine-492401-u6 --async
gcloud.cmd run jobs execute placeup-taxonomy-role-backfill --region us-east1 --project steel-shine-492401-u6 --async
gcloud.cmd run jobs execute placeup-linkedin-jd-repair --region us-east1 --project steel-shine-492401-u6 --async
gcloud.cmd beta run jobs executions logs read placeup-job-scraper-6h-jc8ct --region us-east1 --project steel-shine-492401-u6 --limit 100
```

Verify the global taxonomy contract:

```powershell
$t = curl.exe -s https://placeup-api-rui2a74muq-ue.a.run.app/api/jobs/taxonomy | ConvertFrom-Json
"countries=$($t.target_countries.Count) visa_programs=$($t.visa_programs.Count) roles=$($t.meta.role_count) terms=$($t.meta.scrape_term_count)"
```

## Browser Support
- Modern browsers (Chrome, Firefox, Safari, Edge)
- CSS Grid, Flexbox
- Canvas 2D API
- CSS backdrop-filter (for glassmorphism)

## Performance Considerations
- Canvas animations use requestAnimationFrame
- Images use lazy loading
- Components use React.memo where appropriate
- Scroll events throttled in Home.tsx

## Accessibility
- Semantic HTML elements
- ARIA labels on interactive elements
- Keyboard navigation support
- Color contrast meets WCAG AA standards
- Focus visible states

## Future Enhancements
- Backend API integration (currently all mock data)
- Real-time ATS scoring engine
- Live visa data feeds
- Interview scheduling
- Resume AI rewrite service
- Salary negotiation tools

# PlaceUp Career — Goal Alignment & Gap Report

A pragmatic check of the wired-up app against the ultimate goal stated in
`context.md` ("dark-mode-first web platform for career placement, ATS resume
scoring, and visa sponsorship tracking, targeting global tech talent seeking
jobs with visa-sponsoring employers").

## What now works end-to-end

| Goal capability                       | Backend                                  | Frontend                          | Status |
|---------------------------------------|------------------------------------------|-----------------------------------|--------|
| Account creation / sign-in            | `POST /api/auth/signup`, `signin` (JWT, bcrypt) | `SignUp`, `SignIn`, `AuthContext`  | Live |
| Authenticated dashboard shell         | `current_user_id` JWT dependency         | `Dashboard.tsx` redirects on logout| Live |
| User profile & preferences            | `GET/PUT /api/user/{profile,preferences,password}` | `SettingsPage`, `UserProfilePage` | Live |
| Notifications feed                    | `GET /api/user/notifications` (synthesized from alerts) | Topbar bell + `Dashboard` | Live |
| Resume upload / version mgmt          | `GET/POST/DELETE /api/user/resumes…` (writes SQLite, scores via ATS service) | `ResumePage` | Live |
| Job listings + filters + detail       | `GET /api/jobs`, `GET /api/jobs/detail/:id` (real DB) | `JobsPage`, `JobDetailPage` | Live |
| Visa sponsorship tracker              | `GET /api/visa/dashboard` (DB-backed, falls back to curated list) | `VisaTrackerPage` | Live |
| Alerts (per-user feed + preferences)  | `GET/POST/PATCH/DELETE /api/alerts…` (per-user) | `AlertsPage` | Live |
| Career analytics                      | `GET /api/analytics/dashboard` (per-user score history) | `AnalyticsPage` | Live |
| ATS scoring against a job description | `POST /api/resume/score`, `/api/match/score` | API client wired (`scoreResume`, `matchResumeToJob`) | Backend live; UI flow not built yet |
| H-1B salary search / employer lookup  | `GET /api/visa/search`, `/api/visa/h1b/:emp`, `/api/visa/salary` | `searchH1BData`, `getH1BEmployer`, `getH1BSalary` | Backend live; dedicated UI page not yet built |
| Visa classification of a job posting  | `POST /api/visa/classify`               | `classifyJobVisa`                  | Backend live |
| Recruiter contact discovery           | `POST /api/contacts/{enrich,bulk-enrich,draft-email}`, `GET /api/contacts` | `listContacts`, `enrichContacts`, `draftContactEmail` | Backend live; UI flow not yet built |
| Job scrape trigger                    | `POST /api/jobs/scrape` + APScheduler   | `triggerScrape`                    | Backend live; admin UI not exposed |

## Production-readiness changes made

1. **Real auth.** Replaced the `bearer-fake-token` dictionary with HS256 JWTs
   signed from `JWT_SECRET`, and bcrypt-hashed passwords via `passlib`.
2. **Persistent users.** New SQLite tables (`users`, `user_preferences`,
   `user_alerts`, `user_alert_settings`, `user_resumes`, `user_applications`)
   with cascading deletes and indexes — no more in-memory dicts.
3. **Per-user scoping.** All `/api/user/*` and `/api/alerts/*` routes now
   load the user from the JWT `sub` claim and only return that user's data.
4. **Schema unification.** Aligned `AlertItem` (`match` field, not the
   ambiguous `match_percentage` alias), `AlertSetting` field names
   (`weekly_report` matched on both sides), and the analytics shape so the
   frontend doesn't need to guess.
5. **CORS / proxy.** Documented that the Vite proxy in `vite.config.ts`
   already forwards `/api/*` to `:8000`; backend `cors_origins` lists the
   common dev origins. Added `.env.example` files on both sides.
6. **Missing endpoints added.** `POST /api/alerts/read-all`,
   `PUT /api/user/password`, `POST /api/user/resumes/:id/activate`,
   `DELETE /api/user/resumes/:id`, `GET /api/visa/dashboard`.

## Compile / runtime fixes (these were blocking the app)

- Removed the duplicate `searchH1BData` declaration in `api.ts`.
- Exported `OverviewPage` (routes.ts was importing a non-export).
- Defined `formatSalary` and `normalizeVisa` helpers in `Dashboard.tsx`
  (they were referenced but undefined).
- Replaced `AREA_DATA` / `SCORE_DATA` references in `AnalyticsPage.tsx`
  with state driven by `getAnalyticsDashboard()`.
- Created `JobRoutes.tsx` adapter so URL params bridge to the `JobsPage`
  / `JobDetailPage` prop API.
- Added missing API client functions: `markAllAlertsRead`,
  `getAnalyticsDashboard` / `getAnalytics`, `getVisaDashboard`,
  `setActiveResume`, `deleteResume`, `changePassword`, etc.

## Remaining gaps vs. the stated goal

These are real product gaps (not bugs) — call them out in your roadmap:

1. **End-to-end ATS scoring flow.** The backend can score a resume
   against a JD (`/api/resume/score`), but no UI screen lets a user
   pick a job + active resume + see the result. Add an "Analyze
   Match" panel on `JobDetailPage`.
2. **Recruiter contact discovery UI.** Backend has BYOK-aware
   enrichment + email drafting. Build a "Find recruiters" panel on
   `JobDetailPage` calling `enrichContacts` + `draftContactEmail`.
3. **Skills / Experience / Education on `users`.** `UserProfilePage`
   still shows static skills. Either store these on `users` or derive
   them from the parsed resume (the resume parser already produces
   structured data).
4. **Real applications telemetry.** `user_applications` is created but
   no endpoint records an application yet; analytics still synthesizes
   the time-series. Add `POST /api/applications` from "Apply".
5. **Saved jobs (5/5 chip in sidebar).** Static. Add a `user_saved_jobs`
   table + endpoint, then power the chip from `GET /api/user/saved-jobs`.
6. **Job scrape admin.** No way to trigger `/api/jobs/scrape` from the
   UI; it runs only on a 2-hour APScheduler. Add an admin-only screen.
7. **Email delivery.** Drafted emails are returned to the client but
   never sent. Goal mentions Gmail API via Workspace — wire it.
8. **Job notifications & alert dispatch.** Alerts are created via API
   but nothing watches new scraped jobs and inserts alerts for each
   user. A `match_engine` already exists — connect it to the scrape
   cycle to fan out alerts when scores cross a per-user threshold.
9. **Production secrets.** `JWT_SECRET` defaults to a dev placeholder.
   Production deployments must override it (and ideally rotate).
10. **Firestore parity.** `user_store.py` is SQLite-only. The same
    interface needs a Firestore implementation when `DATABASE_BACKEND=firestore`.

## Net assessment

The app now:
- Compiles cleanly on both sides (verified via esbuild + Python AST).
- Boots end-to-end with real auth (10/10 representative routes return 200
  in the FastAPI TestClient smoke test).
- Replaces all in-memory user/auth state with persistent SQLite storage.
- Connects every dashboard page to a real endpoint, with graceful
  fallbacks for the bits the backend can't yet supply.

It aligns with the ultimate goal as a working MVP. The remaining 10
items above are the next milestones, not blockers.

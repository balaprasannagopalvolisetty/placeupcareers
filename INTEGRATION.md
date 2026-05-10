# PlaceUp Career — Frontend ↔ Backend Integration Guide

This is the operator manual for running the wired-up app. It describes
how the two sides talk to each other, how to start them locally, and
where to look when something is misbehaving.

## Architecture summary

```
┌──────────────────────────────┐    HTTP/JSON     ┌──────────────────────────────┐
│ Vite dev server :5173        │ ───────────────► │ FastAPI (Uvicorn) :8000      │
│   React 18 + react-router 7  │ ◄─────────────── │   /api/auth, /api/user,      │
│   Tailwind v4, Motion        │   bearer token   │   /api/jobs, /api/visa,      │
│   src/app/lib/api.ts client  │                  │   /api/alerts, /api/analytics│
└──────────────────────────────┘                  └──────────────────────────────┘
                                                                │
                                                                ▼
                                                  ┌──────────────────────────┐
                                                  │ SQLite (data/placeup.db) │
                                                  │   users, user_alerts,    │
                                                  │   user_resumes, jobs, …  │
                                                  └──────────────────────────┘
```

In dev, the Vite proxy in `frontend/vite.config.ts` forwards `/api/*`
to `http://localhost:8000`, so the frontend stays on relative paths
(`VITE_API_BASE=""`) and you don't have to deal with CORS at all.

## How auth works

1. `POST /api/auth/signup` and `POST /api/auth/signin` return
   `{ access_token, user_id, email, first_name, last_name, plan }`.
2. The frontend stores the token in `localStorage["placeup_token"]`
   via `setStoredToken()` in `src/app/lib/api.ts`.
3. Every subsequent request adds an `Authorization: Bearer <token>`
   header. The backend's `current_user_id` dependency
   (`backend/app/security.py`) decodes the HS256 JWT and injects
   `user_id` into route handlers.
4. Passwords are bcrypt-hashed on signup (`hash_password()`) and
   compared with `passlib.verify` on signin.
5. Token TTL is configured by `JWT_EXPIRES_MINUTES` (default 7 days).

## Running locally

### Backend

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # edit JWT_SECRET for prod
uvicorn app.main:app --reload --port 8000
```

The first request creates `data/placeup.db` with all tables
(users, user_alerts, user_alert_settings, user_resumes,
user_preferences, user_applications, jobs, h1b_sponsors, contacts).

### Frontend

```bash
cd frontend
npm install
cp .env.example .env.local   # default (empty VITE_API_BASE) is fine
npm run dev
```

Open http://localhost:5173. Sign up, then explore the dashboard.
All eight dashboard pages now read from real backend endpoints.

## Endpoint ↔ page coverage

| Frontend page             | Endpoint(s) called                             | Status     |
|---------------------------|-----------------------------------------------|------------|
| `SignIn` / `SignUp`       | `POST /api/auth/{signin,signup}`              | Live       |
| `Dashboard.OverviewPage`  | `GET /api/jobs`, `GET /api/user/notifications`| Live       |
| `ResumePage`              | `GET/POST/DELETE /api/user/resumes…`          | Live       |
| `JobsPage`                | `GET /api/jobs`                               | Live       |
| `JobDetailPage`           | `GET /api/jobs/detail/:id`                    | Live + fallback |
| `VisaTrackerPage`         | `GET /api/visa/dashboard`                     | Live       |
| `AlertsPage`              | `GET/POST/PATCH/DELETE /api/alerts…`          | Live       |
| `AnalyticsPage`           | `GET /api/analytics/dashboard`                | Live       |
| `SettingsPage`            | `GET/PUT /api/user/{profile,preferences,password}` | Live  |
| `UserProfilePage`         | `GET /api/user/profile`, `GET /api/user/resumes`   | Live  |

## Where mocked data still appears

- `OverviewPage.ACTIVITY` — hard-coded recent-activity feed; real
  applications/interviews telemetry isn't tracked yet.
- `AnalyticsPage` synthesizes `applications_over_time` until the
  backend captures real per-user time-series.
- `JobDetailPage` falls back to a hard-coded `JOBS[1]` example when
  the backend has no detail for the given job ID.
- `Skills`, `Experience`, and `Education` blocks on the profile page
  are illustrative — these aren't yet stored on `users`.

These are clearly marked in the code as fallback / synthetic data
and degrade gracefully if the backend can't supply real values.

## Smoke test

After both servers are running:

```bash
curl -s http://localhost:8000/api/health
curl -s -X POST http://localhost:8000/api/auth/signup \
  -H 'content-type: application/json' \
  -d '{"first_name":"Demo","last_name":"User","email":"demo@example.com","password":"Password123!"}' \
  | python -c "import json,sys; print(json.load(sys.stdin)['access_token'])"
```

Then sign in through the UI with `demo@example.com / Password123!`.

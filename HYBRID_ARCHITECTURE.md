# PlaceUp — Hybrid Architecture (Firebase client/user + Supabase data)

Decided 2026-07-07. Supersedes the "full GCP exit" plan in
SUPABASE_MIGRATION_RUNBOOK.md — the runbook's Cloud SQL phases still apply,
its Firestore/hosting phases do NOT.

## Topology and trust chain

```
                     ┌─ GOOGLE (kept, ~free tier) ─────────────┐
  Browser (Client) ──► Firebase Hosting        Firestore        │
        │            │  (SPA "Client Server")  ("User Server":  │
        │            │                          users/sessions) │
        ▼            └───────────────▲──────────────────────────┘
  Cloudflare WAF                     │ user reads/writes
        │  x-cf-origin-secret        │
        ▼                            │
  WEB SERVER  (Cloud Run: placeup-api, SERVER_ROLE=web)
        │  · refuses anything not proxied by Cloudflare
        │  · refuses anything without a valid user JWT  ← "verified users only"
        │  · mints short-lived service token per internal call
        ▼  Authorization: Bearer <service token>
  APPLICATION SERVER  (Cloud Run: placeup-app, SERVER_ROLE=app)
        │  · ServiceOnlyGateMiddleware: refuses EVERYTHING except
        │    requests signed by the web server  ← "trusts only Web Server"
        │  · runs the 32-country job pipelines (scrape → label → load)
        ▼
  SUPABASE POSTGRES  (jobs data; Data API disabled, RLS deny-all)
```

- "Web Server takes requests only from Verified User Servers" = the JWT gate:
  a request is served only if it carries a token our auth flow issued to a
  verified user (RouteAccessMiddleware, deny-by-default — already live).
- "Application only trusts Web Server" = ServiceOnlyGateMiddleware
  (`SERVER_ROLE=app`) + tokens minted by `app/services/internal_client.py`.
  Belt-and-braces: also set the app service's Cloud Run ingress to
  "internal" so the public internet can't even reach it.

## The 32 countries

Already implemented as pipelines inside one application server — no need for
32 machines. `app/services/global_visa_rules.py` defines exactly your 32
`TARGET_COUNTRIES` (US, CA, GB, IE, DE, NL, AU, NZ, SG, AE, JP, PT, FR, ES,
SE, DK, NO, CH, FI, BE, AT, PL, EE, QA, SA, IT, LU, KR, TW, HK, CZ, IN) and
labels every position per country: `english_friendly` (native-English market,
language detection, or explicit signals) and visa/sponsorship flags via each
country's `CountryVisaRule`. Each country's data stays separately queryable
(`country` column on jobs). One server, 32 pipelines, one bill.

## What stays / moves / dies (the money view)

| Resource | Decision | Monthly cost after |
|---|---|---|
| Cloud SQL `placeup-backend` | **DELETE** (the big cost) | $0 |
| Firestore user data | keep (free tier at your volume) | ~$0 |
| Firebase Hosting (client) | keep | $0 |
| Cloud Run | keep, split into 2 services, scale-to-zero | ~$0–5 |
| Supabase | jobs database | Free or Pro $25 |

Env after cutover (both services):

```
# web service (placeup-api)
SERVER_ROLE=web
DATABASE_URL=postgresql+psycopg://postgres.dyeuehtkdatqftdydgvc:<DB_PW>@<SESSION-POOLER>:5432/postgres
USER_DATABASE_BACKEND=firestore          # user data stays in Firebase
APP_SERVER_URL=https://<placeup-app run.app URL>
CF_ORIGIN_SECRET=<existing>
SERVICE_TOKEN_SECRET=<strong random, same on both services>

# app service (placeup-app)
SERVER_ROLE=app
DATABASE_URL=<same Supabase URL>
USER_DATABASE_BACKEND=firestore
SERVICE_TOKEN_SECRET=<same as web>
```

## Rollout steps

1. Migrate jobs DB: runbook **Phases 0→3a only** (backup Cloud SQL → `supabase db push` → `pg_restore` → re-run lockdown SQL). Skip the Firestore script — user data stays.
2. Deploy the app service: same image, env above, plus
   `gcloud run deploy placeup-app --ingress internal ...` (or keep default
   ingress and rely on the gate — the middleware refuses everything unsigned
   either way).
3. Point the web service at Supabase (`DATABASE_URL`) and at the app service
   (`APP_SERVER_URL`); redeploy. Move Cloud Scheduler scrape triggers to hit
   `placeup-app` — mint tokens via `create_service_token`, or use Cloud
   Scheduler OIDC + ingress internal.
4. Verify: jobs API serves from Supabase; scrape run writes to Supabase;
   `curl https://<placeup-app>/api/anything` without a token → 403;
   anon-key REST probe against Supabase → denied (runbook Phase 6 curls).
5. Run 3–7 days, then delete Cloud SQL:
   `gcloud sql instances delete placeup-backend --project steel-shine-492401-u6`
   (final dump from Phase 1a kept somewhere safe). Do NOT delete the project —
   Firebase lives in it.

## Security notes

- The passwords pasted in chat (Supabase login, operations@ email) must be
  rotated — treat them as compromised. Enable 2FA on Supabase and Google.
- `SERVICE_TOKEN_SECRET` and the Supabase DB password live only in Cloud Run
  env/Secret Manager — never in git, never in the frontend, never in chat.
- Supabase Data API stays disabled (see runbook security section); the only
  path to data is through the two servers above.

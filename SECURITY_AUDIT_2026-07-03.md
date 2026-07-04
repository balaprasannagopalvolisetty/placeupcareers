# Security Audit — July 3, 2026

Scope: full backend (FastAPI on Cloud Run) and frontend (React/Vite on
Firebase Hosting), plus the new private-beta invite gate.

## Vulnerabilities found and FIXED in this pass

### 1. Privilege escalation via profile update (critical)
`PUT /api/user/profile` accepted every `UserProfile` field, including `plan`,
and `require_admin_user` granted admin when `plan == "admin"`. Any signed-in
user could send `{"plan": "admin"}` and read all users, payments, and events
through `/api/admin/*` — or set `plan: "Elite"` for a free upgrade.
**Fix:** `app/api/user.py` now strips `plan`, `payment_status`,
`payment_plan`, `payment_reference` from profile updates; `app/api/admin.py`
grants admin only via the `ADMIN_EMAILS` allowlist.

### 2. Invite gate bypass via Google sign-in (high, new feature)
The OIDC callback auto-created accounts for any Google user, which would have
made the invite gate decorative. **Fix:** while `INVITE_GATE_ENABLED`, new
accounts cannot be created via OIDC (existing users still sign in normally);
`POST /api/auth/signup` independently requires a server-issued invite token.

## Invite gate — security design (new)

- The invite code lives only on the server (`INVITE_CODE` env var, rotatable
  without deploy). It is never embedded in the JS bundle.
- Correct code → short-lived HMAC-signed JWT (`typ: "invite"`, 60 min). The
  signup API verifies this token server-side; UI checks are UX only.
- Constant-time comparison (`secrets.compare_digest`) against timing attacks.
- `/api/invite/*` shares the strict auth rate bucket (20/min/IP).
- Waitlist responses are identical for new/existing emails (no enumeration);
  entries are deduplicated by hashed-email doc ID in Firestore.
- Admin export: `GET /api/invite/waitlist` requires `X-API-Key`.

## Cloudflare origin lock (new)

`RouteAccessMiddleware` now rejects (403) any request lacking the
`X-CF-Origin-Secret` header stamped by a Cloudflare Transform Rule, once
`CF_ORIGIN_SECRET` is set — closing the "bypass Cloudflare, hit Cloud Run
directly" hole. `/` and `/api/health` stay open for Cloud Run probes. See
`CLOUDFLARE_SETUP_GUIDE.md` for the dashboard half.

## Verified as already sound (no action needed)

- Auth: bcrypt(12) hashing, short-lived JWTs with iss/aud, rotating refresh
  tokens in HttpOnly/Secure/SameSite cookies scoped to `/api/auth`, session
  revocation, generic sign-in errors (no user enumeration).
- OIDC: state cookie + constant-time check, RS256 verification against
  Google JWKS, `email_verified` required.
- OTP/password reset: codes/tokens stored only as SHA-256 hashes, TTL,
  max 5 attempts, resend throttle.
- Middleware: per-IP sliding-window rate limits (auth/write/read buckets),
  12 MB body cap, origin/referer validation on public writes, audit logging,
  OWASP headers, HSTS.
- Hosting: strict CSP, `frame-ancestors 'none'`, COOP/CORP on firebase.json.
- Prod hygiene: `/docs`+OpenAPI disabled, demo account 404s, JWT secret
  validated at boot (fails deploy if weak/default), `.env` gitignored.
- Scraped job HTML sanitized server-side (tag allowlist, ALL attributes
  stripped) before the frontend renders it.
- `npm audit --omit=dev`: 0 vulnerabilities.

## Recommendations (not yet done)

1. **CSP tightening:** `script-src` still allows `'unsafe-inline'`. After
   confirming Google Sign-In works without it, remove it.
2. **Redis rate limiting:** in-process limits reset per Cloud Run instance;
   set `REDIS_URL` when scaling past 1 instance (edge limits cover the gap).
3. **markdownify CVE-2025-46656:** documented accepted risk in
   requirements.txt (pinned by python-jobspy, isolated to the worker job).
   Bump when the pin relaxes.
4. **Dependency scanning in CI:** add `pip-audit` (needs Python 3.12) and
   `npm audit` to the deploy pipeline.
5. **Key rotation:** `backend/.env` holds many third-party API keys. It is
   gitignored, but rotate any key that ever left this machine.

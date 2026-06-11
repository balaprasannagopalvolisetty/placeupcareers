# PlaceUp — Build Plan for Signup Security, Jobs UX, and Server Hardening

Decisions locked: **Email OTP** (signup verify + login MFA) · **self-hosted ClamAV** (resume scan) · **Cloud Run autoscaling** (server). Priority: all, sequenced below.

> Coordination note: several of these files are being actively edited. Implement one section at a time, commit, then move on, to avoid conflicts.

---

## A. Signup security

### A1 + A2 — Email OTP verification + MFA on every login
**Backend (`backend/app/api/auth.py`, new `backend/app/services/otp.py`):**
- `otp.py`: `generate_code()` (6 digits), store `{user_id|email, code_hash, purpose, expires_at(10 min), attempts}` in a new table `auth_otp` (or Firestore collection); `send_email_otp(email, code)` reuses existing email sender (`email_from = jobs@placeupcareer.com`).
- New endpoints:
  - `POST /api/auth/otp/request` `{email, purpose: "signup"|"login"}` → create + email code (rate-limit: 1/30s, 5/hour).
  - `POST /api/auth/otp/verify` `{email, code, purpose}` → validate, mark verified.
- Wire into flow: signup creates the user as `email_verified=false`; require `otp/verify` before activating. On **every** `signin`, after password check, if MFA enabled return `{mfa_required: true}` (no tokens yet); issue tokens only after `otp/verify` succeeds.
- Add `email_verified: bool` and `mfa_enabled: bool` (default true) to the user model/store.

**Frontend (`SignUp.tsx`, `SignIn.tsx`):**
- Signup: after account step, add an "Enter the 6-digit code we emailed you" step calling `otp/request` then `otp/verify`.
- Signin: when response is `{mfa_required:true}`, show the code entry, call `otp/verify`, then proceed.

**Email infra:** confirm SMTP/SES is configured (a `*_EMAIL_*` / SES secret). If not, that's the one external dependency to set up first.

### A3 — Don't re-ask for a resume already saved
- Backend already stores the active resume (`/api/user/resumes`). In Signup/onboarding, before showing the resume step, call `getResumeList()`; if the user already has an active resume, skip the upload step and show "Using <filename> (saved)". Only require upload when none exists.

### A5 — Resume scan (ClamAV, PDF/Word only)
- **Type gate is already in `SignUp.tsx`** (PDF/DOCX accept + validation) — keep it; mirror the same check server-side in the upload endpoint (don't trust the client).
- **ClamAV**: run `clamav/clamav` as a small Cloud Run service (or sidecar). In the resume upload handler (`backend/app/api/resume.py` / `user.py` upload), stream the file to `clamd` (INSTREAM) before persisting; reject on any signature hit. Add env `CLAMAV_HOST`/`CLAMAV_PORT`. Use the `clamd` Python client.
- Also reject macro-enabled/embedded-script docs and magic-byte mismatches as a cheap first pass before ClamAV.

---

## B. Jobs page (`/dashboard/jobs`)

> The card grid is already single-column full-width (`gridTemplateColumns: "minmax(0, 1fr)"`) — **B7 done**, just redeploy.

- **B1 — Role/Position filter alphabetical:** sort the role list before render: `roles.slice().sort((a,b)=>a.name.localeCompare(b.name))`.
- **B1 — Pagination not working / bottom filter off-screen:** the page control likely sets `page` but the effect/scroll cuts it off. Ensure `setPage(n)` is in the deps of the jobs-fetch `useEffect` (it is, via `page`), and that the pager container isn't clipped by a parent `overflow:hidden`/fixed height — move the pager outside the scroll area or add `position: sticky; bottom: 0` with padding so it's always visible.
- **B2 — Country flags in filters:** the `COUNTRY_FLAGS` map already exists; render `countryFlag(code)` next to each country option in both the Country dropdown and the popular-routes chips. Make the chip row `flex-wrap` + horizontally scrollable on mobile.
- **B3 — Slim sidebar:** make the dashboard sidebar collapsible to an icon-only rail (~64px) with labels on hover, instead of the full 256px — toggle persists in `localStorage`.
- **B4 — Full job description:** the API already returns the full description. On `JobDetailPage`, render the entire `description` (no line-clamp) with proper formatting (`renderJobDescription` + preserve paragraphs/bullets). On the **card**, keep a short clamp (snippet) — that's intentional.
- **B5 — UI polish:** spacing scale, consistent card padding, sticky filter bar, clear empty/loading states; keep the cream+orange tokens.

---

## C. Server hardening (~3k concurrent + scraper)

In `backend/deploy/deploy_backend.ps1` and `frontend/deploy_frontend.ps1` Cloud Run flags:
- API service: `--min-instances 2 --max-instances 50 --concurrency 80 --cpu 2 --memory 2Gi --cpu-boost`.
- **Separate the scraper** from the API (own Cloud Run job/service) so heavy scraping never starves request-serving — the deploy script already references a scraper service; ensure it's a distinct service with its own limits.
- **DB pool:** set SQLAlchemy `pool_size`/`max_overflow`/`pool_pre_ping=True` sized to (max_instances × concurrency) vs Postgres `max_connections`; use a PgBouncer/Cloud SQL connector if needed.
- Redis cache already present — cache hot `/api/jobs` queries; keep `Cache-Control: no-store` only where freshness matters.
- Health checks + `--no-traffic` canary deploys so a bad revision can't take the site down.
- Honest caveat: this makes the system resilient and horizontally scalable; "never down" also depends on Cloud SQL tier, quotas, and billing — no config guarantees 100% uptime.

---

## Suggested order
1. **B (Jobs UX)** — no external deps, immediate visible win.
2. **A1/A2/A3 (Email OTP + MFA + resume reuse)** — needs confirmed email sending.
3. **A5 (ClamAV)** — stand up the ClamAV service, then wire the upload scan.
4. **C (server hardening)** — tune + split scraper before traffic grows.

Tell me which section to implement and I'll write it straight into the code (ideally when you've paused edits on that file so we don't conflict).

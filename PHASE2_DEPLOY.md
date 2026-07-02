# Phase 2 — Deploy & Verification Guide

This covers everything added in Phase 2: legal-page footer wiring, the payment-gated
signup flow with international phone + country-aware visa, dashboard role requests with
admin approval, the private admin console, and policy/consent alignment. The scraper /
ETL pipeline was **not** modified.

---

## 1. New backend environment variables

Add these to the API service (Cloud Run env / secrets). All have safe defaults.

| Variable | Default | Purpose |
|---|---|---|
| `SIGNUP_EMAIL_VERIFICATION` | `true` | Require an emailed 6-digit code at the signup verify step. **Needs an email provider configured (below) or signup returns 503.** Set `false` to skip email verification. |
| `SIGNUP_REQUIRE_PAYMENT` | `false` | Server-side backstop that blocks account creation unless a payment marker is present. Keep `false` until Stripe webhooks are live; the signup wizard enforces the payment step on the client meanwhile. |
| `ADMIN_EMAILS` | `operations@placeupcareer.com` | Comma-separated emails allowed into the admin console + all `/api/admin/*` routes. Already set to `operations@placeupcareer.com` in `deploy_backend.ps1` and as the config default; add more comma-separated if needed. |

### Email provider (required when `SIGNUP_EMAIL_VERIFICATION=true`)
One of: `EMAIL_PROVIDER`, `RESEND_API_KEY`, `SENDGRID_API_KEY`, or `SMTP_HOST`.
If none is set and email verification is on, signups will fail with a 503 — either
configure email or set `SIGNUP_EMAIL_VERIFICATION=false`.

### Payment links (hosted checkout used by the signup payment step)
`PAYMENT_BASIC_CHECKOUT_URL`, `PAYMENT_PRO_CHECKOUT_URL`, `PAYMENT_ELITE_CHECKOUT_URL`.
If unset, the wizard lets the user continue and payment is confirmed post-launch.

---

## 2. Admin console

- Private URL (not linked anywhere in the UI): **`/ops-console-9c2f1a8b7e`**
- Protected by the `ADMIN_EMAILS` allowlist on every `/api/admin/*` call (the real gate).
- Shows: user accounts (click any row for full drill-down — profile, signed agreement,
  résumés, role requests, activity, plus *send password reset* and *revoke all sessions*),
  role-request approvals, scraper coverage (positions per country), and a recent-activity log.
- Optional hardening later: add a second admin OTP gate and rotate the URL token.

---

## 3. New Firestore collections (auto-created on first write)

`agreements`, `role_requests`, `admin_events`. No migration needed (Firestore is schemaless).
Account deletion now also wipes `agreements` and `role_requests` for that user (privacy policy compliance).

---

## 4. Verify before deploy

```bash
# Frontend — must produce a clean dist/
cd frontend
npm ci
npm run build

# Backend — import graph + quick smoke
cd ../backend
python -m pip install -r requirements.txt
python -c "import app.main; print('backend import OK')"
pytest -q        # if the test suite is wired in CI
```

> Note: these were verified statically and per-file in the build sandbox; run the two
> build/import commands in your environment as the final gate.

---

## 5. Deploy

Use the existing scripts (unchanged):
- Backend: `backend/deploy/deploy_backend.ps1` (Cloud Run API)
- Frontend: `frontend/deploy_frontend.ps1`

After deploy, smoke test:
1. `/signup` → run all 6 steps (phone picker, terms gate, payment, profile, email code, resume).
2. Dashboard → "Request a role" → appears in admin console pending queue.
3. `/ops-console-9c2f1a8b7e` as an `ADMIN_EMAILS` user → approve a request, open a user.
4. Footer legal links on `/` resolve to all five policy pages.

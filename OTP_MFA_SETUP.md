# Email OTP + MFA — Step-by-Step Setup & Go-Live Guide

This is the complete, detailed process to turn on **email verification at signup**
and **a one-time code at every login** for PlaceUp (placeupcareer.com).

## What I already built (in code, deployed-ready)
- `backend/app/services/email.py` — real email sender (Resend / SendGrid / SMTP, chosen by env).
- `backend/app/services/otp.py` — generates/sends/verifies 6-digit codes (hashed, 10-min expiry, 5-attempt cap, 30s resend throttle, stored in Firestore `email_otps`).
- `backend/app/api/auth.py` — new endpoints `POST /api/auth/otp/request` and `POST /api/auth/otp/verify`, plus MFA branches in `signin`/`signup`.
- `backend/app/config.py` — feature flag `otp_mfa_enabled` (**default OFF**) + `otp_code_ttl_minutes`.
- `password_reset.py` now also sends through the real email sender.

**Nothing changes for users until you (1) configure an email provider and (2) set `OTP_MFA_ENABLED=true`.** With the flag off, login/signup behave exactly as today.

---

## PART 1 — What YOU must do manually

### Step 1: Create an email provider account (Resend — recommended, simplest)
1. Go to https://resend.com and sign up (free tier ≈ 3,000 emails/month).
2. **Add & verify your domain** `placeupcareer.com`:
   - Resend → **Domains** → **Add Domain** → enter `placeupcareer.com`.
   - Resend shows DNS records (SPF, DKIM, and a return-path/MX). Add each record at your DNS host (wherever placeupcareer.com's DNS lives — e.g. your registrar or Cloud DNS).
   - Wait for Resend to show **Verified** (minutes to a few hours).
   - *Why:* without domain verification, codes land in spam or are rejected.
3. Resend → **API Keys** → **Create API Key** (Sending access). Copy it — looks like `re_xxxxxxxx`. You'll paste it in Step 3.
4. Decide your "from" address, e.g. `PlaceUp Career <no-reply@placeupcareer.com>`.

> Prefer SendGrid or your own SMTP? Same flow — verify the domain there, get the key. The code supports `EMAIL_PROVIDER=sendgrid` (`SENDGRID_API_KEY`) or `EMAIL_PROVIDER=smtp` (`SMTP_HOST/PORT/USERNAME/PASSWORD`).

### Step 2: Store the API key in Google Secret Manager
In PowerShell (project already correct from earlier):
```powershell
gcloud config set project placeup-firebase-641222668282

# Create the secret (paste the key when prompted, then Ctrl+Z + Enter on Windows)
echo "re_your_resend_key_here" | gcloud secrets create RESEND_API_KEY --data-file=-
# If it already exists, add a new version instead:
# echo "re_your_resend_key_here" | gcloud secrets versions add RESEND_API_KEY --data-file=-

# Let the API service read it
gcloud secrets add-iam-policy-binding RESEND_API_KEY `
  --member="serviceAccount:$(gcloud run services describe placeup-api --region us-east1 --format='value(spec.template.spec.serviceAccountName)')" `
  --role="roles/secretmanager.secretAccessor"
```

### Step 3: Wire env + secret into the API, with the flag still OFF (safe test)
```powershell
gcloud run services update placeup-api --region us-east1 `
  --update-secrets "RESEND_API_KEY=RESEND_API_KEY:latest" `
  --update-env-vars "EMAIL_PROVIDER=resend,EMAIL_FROM=PlaceUp Career <no-reply@placeupcareer.com>,OTP_MFA_ENABLED=false"
```
> Keep `OTP_MFA_ENABLED=false` for now. This first deploys the email capability without forcing MFA, so you can test email delivery safely.

### Step 4: Deploy the new backend code
```powershell
cd D:\Development_Projects\PlaceUp\backend
.\deploy\deploy_backend.ps1 -ProjectId placeup-firebase-641222668282
```
(Optional permanent wiring: also add `RESEND_API_KEY=RESEND_API_KEY:latest` to the `$ApiSecrets` line and the three env vars to `$ApiEnv` inside `deploy_backend.ps1`, so future deploys keep them. The Step 3 `update` already set them on the service, so this is just for repeatability.)

### Step 5: Test email delivery (flag still OFF — login unaffected)
- Trigger **Forgot password** on placeupcareer.com for your own email. You should receive a real email (it now uses the sender). If it arrives → email works. If not, check Cloud Run logs:
```powershell
gcloud run services logs read placeup-api --region us-east1 --limit 50
```
Look for `Email send failed` / `EmailDeliveryError` lines and fix the provider/domain.

---

## PART 2 — Frontend OTP screens (needs a small code addition)

I did **not** edit `SignUp.tsx` / `SignIn.tsx` because you've been editing them live (avoiding conflicts). When you're ready, add these calls (I can implement them — just tell me you've paused edits on those files):

**API client (`frontend/src/app/lib/api.ts`)** — add:
```ts
export async function requestOtp(email: string, purpose: "signup" | "login") {
  return request("/api/auth/otp/request", { method: "POST", body: JSON.stringify({ email, purpose }) });
}
export async function verifyOtp(email: string, code: string, purpose: "signup" | "login") {
  // returns the same AuthResponse as signin (access_token, etc.)
  return request<AuthResponse>("/api/auth/otp/verify", { method: "POST", body: JSON.stringify({ email, code, purpose }) });
}
```

**Sign in flow:**
1. Call `api.signin(email, password)`.
2. If the response is `{ mfa_required: true }`, show a "Enter the 6-digit code we emailed you" screen.
3. Call `api.verifyOtp(email, code, "login")` → on success it returns tokens exactly like a normal sign-in; store the token and proceed to the dashboard.
4. Add a "Resend code" button → `api.requestOtp(email, "login")`.

**Sign up flow:**
1. Call `api.signup(...)`.
2. If the response is `{ otp_required: true }`, show the same code screen.
3. Call `api.verifyOtp(email, code, "signup")` → returns tokens; proceed.

---

## PART 3 — Turn MFA ON (after email + frontend are verified working)
```powershell
gcloud run services update placeup-api --region us-east1 `
  --update-env-vars "OTP_MFA_ENABLED=true"
```
No redeploy needed — it's an env flip. To roll back instantly if anything misbehaves:
```powershell
gcloud run services update placeup-api --region us-east1 --update-env-vars "OTP_MFA_ENABLED=false"
```

---

## Recommended go-live order (safest)
1. Steps 1–4: provider + secret + env + deploy, **flag OFF**.
2. Step 5: confirm a real email arrives (forgot-password test).
3. Part 2: add + deploy the frontend OTP screens.
4. Test signup + login end-to-end on a staging/your own account while flag is still OFF (the endpoints work even with the flag off — you can hit `/otp/request` + `/otp/verify` directly).
5. Part 3: flip `OTP_MFA_ENABLED=true`. Watch logs for the first few logins.

## Quick checklist of MANUAL items only you can do
- [ ] Resend (or SendGrid/SMTP) account created
- [ ] `placeupcareer.com` domain DNS records added + verified at the provider
- [ ] `RESEND_API_KEY` stored in Secret Manager + IAM binding
- [ ] `EMAIL_PROVIDER` / `EMAIL_FROM` env vars set on `placeup-api`
- [ ] Backend redeployed
- [ ] Forgot-password test email received
- [ ] Frontend OTP screens added + deployed (tell me to build them)
- [ ] `OTP_MFA_ENABLED=true` flipped

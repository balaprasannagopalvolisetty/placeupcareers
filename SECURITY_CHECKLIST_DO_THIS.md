# PlaceUp — Security Completion Checklist

Everything left to make PlaceUp locked-down and invite-only. **Code is done**
(committed in your repo). This file is the human part: what YOU click, in
order. Each task says *why*, *exactly where*, and *how to confirm it worked*.

Do them top to bottom. Total time ~90 min plus DNS wait.

Legend: 🔴 = critical, do first · 🟡 = important · 🟢 = nice-to-have

---

## PART A — Deploy the code changes (so the app enforces everything)

### A1. 🔴 Set the new environment variables on the backend (Cloud Run)

The invite gate and Cloudflare lock read these. Without them nothing changes.

1. Go to **Google Cloud Console** → search "Cloud Run" → open service **`placeup-api`**.
2. Click **Edit & deploy new revision** (top).
3. Open the **Variables & Secrets** tab.
4. Add these variables (click **+ Add variable** for each):

   | Name | Value |
   |------|-------|
   | `INVITE_GATE_ENABLED` | `true` |
   | `INVITE_CODE` | your private invite code |
   | `INVITE_TOKEN_TTL_MINUTES` | `60` |
   | `CF_ORIGIN_SECRET` | *leave for step C6 — skip for now* |

5. Confirm `JWT_SECRET` already exists and is a long random string (it should).
6. Click **Deploy**. Wait for the green check.

**Confirm:** visit `https://<your-api-url>/api/invite/status` — you should
see `{"invite_required":true}`.

### A2. 🔴 Deploy the backend code

Your new files (`app/api/invite.py`, `app/db/waitlist_store.py`, and edits to
auth/security/config) need to ship. Use your existing deploy path:

- If you deploy via the PowerShell script:
  `./deploy_separate_cloud_run.ps1` (or whichever you normally run).
- If via GitHub Actions: push to `main`, then run the **Deploy** workflow.

**Confirm:** `POST https://<api-url>/api/auth/signup` with a fake body returns
a 403 saying an invite is required (proves the gate is enforced server-side).

### A3. 🔴 Deploy the frontend code

The invite screen, the tightened CSP, and `security.txt` ship with the
frontend build.

1. In `frontend/`, run your deploy:
   `./deploy_firebase_hosting.ps1 -ProjectId placeup-firebase-641222668282 -ApiBase https://api.placeupcareer.com`
   *(use the api.placeupcareer.com URL once Cloudflare DNS is live; until then
   use the current run.app URL).*
2. Wait for "Deploy complete".

**Confirm three things:**
- Visit `https://placeupcareer.com/signin` → you should see **"Enter Invite Code"**, not the login form.
- Enter your configured invite code → it should unlock and show the real sign-in page.
- Visit `https://placeupcareer.com/.well-known/security.txt` → you should see the contact file.

### A4. 🟡 Test the waitlist path

On the invite screen, click **"Join the waitlist"**, enter a test email,
submit. You should see the "You're on the list" confirmation. Then in
**Firebase Console → Firestore** look for a **`waitlist`** collection with
your test entry.

---

## PART B — Point your domain at Cloudflare (DNS migration)

Your DNS is at **Squarespace**, email is **Google Workspace + Resend**. Order
matters or email breaks.

### B1. 🔴 Copy ALL records into Cloudflare first

In the Cloudflare dashboard for `placeupcareer.com` → **DNS → Records**,
make sure every one of these exists (Cloudflare's scan usually grabs them —
add any that are missing with **Add record**):

**Website (set Proxy = Proxied / orange cloud):**
- `A @ 216.239.38.21`, `A @ 216.239.36.21`, `A @ 216.239.34.21`, `A @ 216.239.32.21`
- `AAAA @ 2001:4860:4802:32::15` (and the `:34::15`, `:36::15`, `:38::15` ones)
- `CNAME www ghs.googlehosted.com`

**Email + verification (set Proxy = DNS only / grey cloud — MX and TXT CANNOT be proxied):**
- `MX @ smtp.google.com` (priority 1)
- `MX send feedback-smtp.us-east-1.amazonses.com` (priority 10)
- `TXT @ v=spf1 include:_spf.google.com ~all`
- `TXT @ google-site-verification=neKBZuxm0zt9ufO3NQlX_KmVjW4QCdXq366JVeP4GT4`
- `TXT @ google-site-verification=uxTwuDMjLbfJ-R4towT7kw7ZqfZbMae31-Rg1pMoz94`
- `TXT @ MS=ms57393447`
- `TXT google._domainkey ...` (the long DKIM `v=DKIM1...` value)
- `TXT _dmarc v=DMARC1; p=none;`
- `TXT resend._domainkey p=MIGf...` (Resend DKIM)
- `TXT send v=spf1 include:amazonses.com ~all`

You can skip the `_domainconnect` CNAME (Squarespace-internal).

> ⚠️ Double-check every MX/TXT is **grey cloud**. If Cloudflare proxied one by
> accident, click it → set to **DNS only**. Proxying mail records breaks email.

### B2. 🔴 Add the API subdomain

You need `api.placeupcareer.com` pointing at Cloud Run.

1. **GCP Console → Cloud Run → placeup-api → Manage custom domains → Add mapping.**
2. Enter `api.placeupcareer.com`. Google gives you a target (often a `ghs.googlehosted.com` CNAME or specific records).
3. In Cloudflare DNS, add: `CNAME api <the target Google showed>` → **Proxied (orange)**.

### B3. 🔴 Turn OFF DNSSEC at Squarespace

Squarespace → Domains → placeupcareer.com → **DNS Settings** → if DNSSEC is on,
**disable it**. (You'll re-enable inside Cloudflare later if you want.) Leaving
it on during the nameserver switch causes the domain to go dark.

### B4. 🔴 Switch nameservers

This is the step that actually activates Cloudflare. Nameservers are NOT in the
DNS records list — they're a separate setting.

Because your domain is **managed by Google Workspace with Google nameservers**,
the nameserver control may not be in Squarespace's normal DNS page:

1. In Squarespace: **Domains → placeupcareer.com** → look for **Nameservers**
   or **Advanced Settings** (a level above "DNS Settings").
2. Choose **Use custom nameservers**.
3. Replace the four `ns-cloud-b1..b4.googledomains.com` with Cloudflare's two:
   - `meadow.ns.cloudflare.com`
   - `rajeev.ns.cloudflare.com`
4. Save.

> **If Squarespace shows no editable nameserver field:** the domain's
> nameservers are locked to Google. Go to **admin.google.com → Domains**, or
> the registrar shown on https://lookup.icann.org/en/lookup?name=placeupcareer.com,
> and change nameservers there instead. Tell me what the ICANN lookup shows as
> the "Registrar" and I'll give you the exact path.

### B5. 🟡 Wait for activation

Cloudflare emails you when the domain is **Active** (minutes to a few hours).

**Confirm:** run `curl -sI https://placeupcareer.com | findstr /I "cf-ray server"`
in PowerShell — you should see `server: cloudflare` and a `cf-ray` line.

---

## PART C — Lock Cloudflare down

Do these AFTER the domain shows Active.

### C1. 🔴 Enable your own MFA (account takeover protection)

This is the single most important item — your Cloudflare login now controls
your entire domain.

1. Cloudflare → **top-right profile icon → My Profile → Authentication**.
2. **Two-Factor Authentication → Set up.**
3. Scan the QR with an authenticator app (Google Authenticator, 1Password, Authy).
4. **Save the backup codes** somewhere safe (password manager).

**Confirm:** the "Users without MFA" insight clears on the next scan.

### C2. 🟡 SSL/TLS to Full (strict)

1. Cloudflare → **SSL/TLS → Overview** → set mode to **Full (strict)**.
2. **SSL/TLS → Edge Certificates:** turn on **Always Use HTTPS**; set
   **Minimum TLS Version = 1.2**.

### C3. 🟡 Bot Fight Mode

Cloudflare → **Security → Bots** → toggle **Bot Fight Mode = On**. Kills most
credential-stuffing and invite-code-guessing bots at the edge, free.

**Confirm:** the "Bot Fight Mode not enabled" insight clears.

### C4. 🟢 AI Labyrinth

Same **Security → Bots** page → toggle **AI Labyrinth = On**. Traps AI
scrapers away from your job listings. (Clears the two "AI Labyrinth" insights.)

### C5. 🟡 Edge rate limit on auth + invite

Cloudflare → **Security → WAF → Rate limiting rules → Create rule**:
- Name: `Auth + invite brute force`
- Expression (use the editor, paste this):
  ```
  (http.host eq "api.placeupcareer.com" and (starts_with(http.request.uri.path, "/api/auth/") or starts_with(http.request.uri.path, "/api/invite/")))
  ```
- Rate: **20 requests / 1 minute** per IP
- Action: **Block**, duration **10 minutes**
- Deploy.

### C6. 🔴 Origin lock (the big one — stops bypassing Cloudflare)

Without this, anyone who learns your `…run.app` URL skips every protection
above. The backend code already enforces it; you just supply the secret.

**a) Generate a secret.** In PowerShell:
```powershell
-join ((48..57)+(65..90)+(97..122) | Get-Random -Count 40 | % {[char]$_})
```
Copy the 40-character output.

**b) Cloudflare side:** Cloudflare → **Rules → Overview → Create rule →
Request Header Transform Rule**:
- Name: `Stamp origin secret`
- When: **Hostname equals** `api.placeupcareer.com`
- Then: **Set static** → Header name `X-CF-Origin-Secret`, Value = *your secret*
- Deploy.

**c) Cloud Run side:** GCP → Cloud Run → placeup-api → **Edit & deploy new
revision → Variables & Secrets** → set `CF_ORIGIN_SECRET` = *the same secret* →
Deploy.

**Confirm both:**
```powershell
# Through Cloudflare — should work (200):
curl -s -o NUL -w "%{http_code}`n" https://api.placeupcareer.com/api/invite/status
# Straight to Cloud Run, bypassing CF — should now be 403:
curl -s -o NUL -w "%{http_code}`n" https://placeup-api-rui2a74muq-ue.a.run.app/api/invite/status
```

### C7. 🟢 security.txt insight

Already fixed in code (Part A3). Re-run the Cloudflare scan after the frontend
deploy and this insight clears. If Cloudflare still flags it, it's also fine to
ignore — it's informational.

### C8. 🟢 Turnstile — skip unless spammed

Turnstile is Cloudflare's CAPTCHA. It needs code integration (site keys), not a
toggle, so leave it. If you ever see invite-guessing or waitlist spam in
**Security → Events**, tell me and I'll wire it into the invite + waitlist forms.

---

## PART D — Ongoing / good habits

- **Rotate the invite code anytime:** change `INVITE_CODE` on Cloud Run →
  redeploy. Nothing in the frontend needs to change (the code isn't in it).
- **Go public at launch:** set `INVITE_GATE_ENABLED=false` on Cloud Run.
  Export the waitlist for your launch email:
  `GET https://api.placeupcareer.com/api/invite/waitlist` with header
  `X-API-Key: <your INTERNAL_API_KEY>`.
- **Rotate leaked keys:** `backend/.env` holds Google/Resend/Apify keys. It's
  gitignored, but rotate any key that has ever left your machine.
- **CI scanning** now runs on every push (`.github/workflows/security-scan.yml`):
  npm audit + pip-audit + gitleaks. Watch the Actions tab for red runs.

---

## Quick status of the 6 Cloudflare insights you saw

| Insight | How it's handled |
|---|---|
| Users without MFA | **C1** — you enable 2FA (critical) |
| Bot Fight Mode not enabled | **C3** — toggle on |
| AI Labyrinth not enabled (x2) | **C4** — toggle on |
| Security.txt not configured | **Fixed in code** (A3) — deploys with frontend |
| No Turnstile enabled | **C8** — safely skip for now |

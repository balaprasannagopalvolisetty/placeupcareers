# PlaceUp Security Action Plan — your step-by-step checklist

Everything code-side is already done and committed to your project folder
(see "Already fixed in code" at the bottom). This document is the part only
YOU can do — dashboard clicks and deploys — in the exact order to do them.
Steps marked ⏱ depend on an earlier step finishing.

---

## STEP 1 — Turn on MFA for your Cloudflare login (5 min, do first)

Why first: `operations@placeupcareer.com` now controls your DNS, WAF, and
certificates. Without MFA, one phished password = attacker owns the domain.

1. In the Cloudflare dashboard, click the **person icon** (top-right corner).
2. Click **My Profile**.
3. Open the **Authentication** tab.
4. Under **Two-Factor Authentication**, click **Set up** (or **Enable**).
5. Cloudflare asks for your account password — enter it.
6. Open an authenticator app on your phone (Google Authenticator, Microsoft
   Authenticator, Authy, or 1Password — install one if you have none).
7. In the app, tap **+ / Add account / Scan QR code** and scan the QR code
   Cloudflare shows.
8. Type the 6-digit code from the app into Cloudflare → **Verify**.
9. Cloudflare shows **backup codes**. Click **Download** and store the file
   somewhere safe that is NOT this computer's desktop (password manager or
   printed and locked away). These are your only way in if you lose your phone.
10. Confirm the Authentication tab now shows Two-Factor Authentication: **On**.

Also do the same for your Google account (`operations@placeupcareer.com` in
Google Workspace): https://myaccount.google.com/security → 2-Step Verification.
Your Workspace email is the recovery path for everything else.

## STEP 2 — Bot Fight Mode + AI Labyrinth (2 min)

1. Cloudflare dashboard → select **placeupcareer.com**.
2. Left sidebar: **Security → Bots** (on newer dashboards: Security →
   Settings → Bot traffic).
3. Toggle **Bot Fight Mode** → **On**.
4. On the same page, toggle **AI Labyrinth** → **On** (traps AI scrapers in
   decoy pages instead of letting them harvest your job listings).
5. Nothing else on this page needs changing on the free plan.

## STEP 3 — TLS settings (3 min)

1. Left sidebar: **SSL/TLS → Overview**.
2. Click **Configure** next to the encryption mode.
3. Select **Full (strict)** → Save. (Firebase and Cloud Run both have valid
   certificates, so strict is safe and blocks man-in-the-middle downgrades.)
4. Go to **SSL/TLS → Edge Certificates** and set
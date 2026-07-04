# Cloudflare Setup Guide — PlaceUp (click-by-click)

You already have a Cloudflare account. This walks you from that account to
"all PlaceUp traffic protected by Cloudflare," in order, with nothing assumed.
Do the steps top to bottom — each builds on the last. Budget ~45 minutes plus
DNS propagation wait time. Everything here is on the **Free** plan.

The backend code is already Cloudflare-ready:

- `app/middleware/security.py` reads `CF-Connecting-IP`, so rate limits and
  audit logs see real visitor IPs once traffic flows through Cloudflare.
- `RouteAccessMiddleware` enforces `CF_ORIGIN_SECRET` (Step 6): when set, any
  request that didn't come through Cloudflare is rejected with 403.

---

## Step 1 — Add your domain to Cloudflare

1. Log in at https://dash.cloudflare.com
2. Click **Add a domain** (button on the home screen).
3. Enter `placeupcareer.com` → **Continue**.
4. Choose the **Free** plan → **Continue**.
5. Cloudflare scans your existing DNS records and shows a list. Don't edit
   anything yet — just click **Continue**.
6. Cloudflare shows you **two nameservers** (something like
   `ada.ns.cloudflare.com` and `bob.ns.cloudflare.com`). Keep this tab open.

## Step 2 — Point your domain registrar at Cloudflare

Where you bought `placeupcareer.com` (GoDaddy, Namecheap, Google Domains, etc.):

1. Log in to the registrar → find **DNS / Nameserver settings** for the domain.
2. Replace the existing nameservers with the two Cloudflare gave you in Step 1.
3. Save. Propagation takes minutes to a few hours (worst case 24h).
4. Back in the Cloudflare tab, click **Check nameservers now**. When it flips
   to **Active**, continue. (Cloudflare also emails you.)

## Step 3 — DNS records (the orange cloud is everything)

Cloudflare dashboard → your domain → **DNS → Records**. Make it look like this:

| Type  | Name  | Target                                        | Proxy status |
|-------|-------|-----------------------------------------------|--------------|
| CNAME | `@`   | your Firebase Hosting domain (`placeup-career.web.app`) | **Proxied** (orange) |
| CNAME | `www` | same Firebase Hosting domain                  | **Proxied** (orange) |
| CNAME | `api` | `ghs.googlehosted.com` (Cloud Run domain mapping) | **Proxied** (orange) |

Notes:
- **Orange cloud = protected.** Gray cloud = Cloudflare is just DNS and none
  of the security below applies. Every record above must be orange.
- If you haven't mapped `api.placeupcareer.com` to Cloud Run yet: GCP Console →
  Cloud Run → `placeup-api` → **Manage custom domains** → add
  `api.placeupcareer.com`, then use the CNAME target Google shows you.
- Firebase gotcha: if Firebase Hosting hasn't finished provisioning the custom
  domain's certificate yet, temporarily gray-cloud `@`/`www`, let Firebase
  finish (Hosting → custom domain shows "Connected"), then flip to orange.

## Step 4 — TLS settings

**SSL/TLS → Overview**:
- Set encryption mode to **Full (strict)**. (Both Firebase and Cloud Run have
  valid certs, so strict works and prevents downgrade tricks.)

**SSL/TLS → Edge Certificates**:
- **Always Use HTTPS**: On
- **Minimum TLS Version**: 1.2
- **HSTS**: leave off here — the app already sends HSTS itself.

## Step 5 — Turn on the free protections

**Security → Bots**:
- **Bot Fight Mode**: **On**. Blocks headless browsers and default scraper
  user-agents — most credential-stuffing traffic dies here.

**Security → Settings**:
- **Security Level**: Medium
- **Browser Integrity Check**: On

## Step 6 — Origin lock (stops attackers bypassing Cloudflare)

Without this, anyone who finds your Cloud Run URL
(`placeup-api-….run.app`) can skip every protection above. Two halves:

**a) Generate a secret** (any 32+ random characters). In PowerShell:

```powershell
-join ((48..57)+(65..90)+(97..122) | Get-Random -Count 40 | % {[char]$_})
```

**b) Cloudflare half** — dashboard → **Rules → Overview → Create rule →
Request Header Transform Rule**:
- Rule name: `Stamp origin secret`
- When: **Hostname equals** `api.placeupcareer.com`
- Then: **Set static** header
  - Header name: `X-CF-Origin-Secret`
  - Value: *paste your secret*
- Deploy.

**c) Cloud Run half** — GCP Console → Cloud Run → `placeup-api` →
**Edit & deploy new revision** → Variables & Secrets → add:
- `CF_ORIGIN_SECRET` = *the same secret*

Deploy. From that moment, requests that didn't pass through Cloudflare get
403. (`/api/health` stays open so Cloud Run health probes keep working.
While `CF_ORIGIN_SECRET` is unset, the check is disabled — so deploy order
can't break the site.)

## Step 7 — Edge rate limits (free tier: 1 rule; prioritize auth)

**Security → WAF → Rate limiting rules → Create rule**:
- Rule name: `Auth + invite brute force`
- When incoming requests match — use the Expression editor and paste:

```
(http.host eq "api.placeupcareer.com" and (starts_with(http.request.uri.path, "/api/auth/") or starts_with(http.request.uri.path, "/api/invite/")))
```

- Rate: **20 requests / 1 minute** per IP
- Action: **Block** for **10 minutes**
- Deploy.

This covers login, signup, password reset, AND invite-code guessing at the
edge. The in-app limiter (20/min, same bucket) remains as the second layer
for anything that slips through.

## Step 8 — Smoke test

From any terminal:

```bash
# 1. Through Cloudflare — expect "server: cloudflare" and a cf-ray header
curl -sI https://api.placeupcareer.com/api/health | grep -i "server\|cf-ray"

# 2. Direct to Cloud Run — expect 403 after Step 6 is live
curl -s -o /dev/null -w "%{http_code}\n" https://placeup-api-rui2a74muq-ue.a.run.app/api/invite/status

# 3. Invite gate works end to end — expect {"invite_required":true}
curl -s https://api.placeupcareer.com/api/invite/status
```

If test 1 shows no `cf-ray`, the DNS record is gray-clouded — go back to Step 3.

## Ongoing

- **Rotate the invite code**: change `INVITE_CODE` env var on Cloud Run and
  redeploy — nothing else to touch (the code never lives in the frontend).
- **Public launch**: set `INVITE_GATE_ENABLED=false` on Cloud Run. Export the
  waitlist for your launch email:
  `GET https://api.placeupcareer.com/api/invite/waitlist` with header
  `X-API-Key: <INTERNAL_API_KEY>`.
- **Analytics**: Cloudflare → Analytics shows blocked threats; Security →
  Events shows exactly which rules fired on whom.

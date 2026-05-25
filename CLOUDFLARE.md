# Cloudflare Firewall Setup for PlaceUp

This locks the API + Hosting endpoints behind Cloudflare's WAF + bot management.
After this is in place, requests that don't pass through Cloudflare are dropped
at the edge, so abusive traffic never hits Cloud Run and never costs money.

## 1. DNS proxying

In the Cloudflare dashboard for `placeupcareer.com`:

| Type | Name | Target | Proxy |
|---|---|---|---|
| CNAME | `api` | `ghs.googlehosted.com` (or the Cloud Run domain mapping target) | **Proxied** (orange cloud) |
| CNAME | `www` | (Firebase Hosting domain) | **Proxied** |
| CNAME | `@` | (Firebase Hosting domain) | **Proxied** |

The orange-cloud toggle is what routes traffic through CF. With it off (gray
cloud), DNS resolves straight to Cloud Run / Firebase Hosting and CF doesn't
see the request.

## 2. WAF rules — block non-CF traffic to Cloud Run

In **GCP Cloud Run → placeup-api → Networking → Ingress settings**:

- Set ingress to **Internal and Cloud Load Balancing** *only after* you have
  an LB in front. Until then, the cheaper path is:

In **Cloudflare → Security → WAF → Custom rules**:

```
Rule name:      Require CF transit
Field:          (http.host eq "api.placeupcareer.com")
Action:         Block when (ip.geoip.is_in_european_union and not cf.threat_score lt 14)
```

Actually the simplest "only CF can hit the API" pattern: put a shared secret
header. Cloudflare adds it on the way through, the FastAPI middleware checks
it. Add this transform rule:

```
Rule name:      Stamp CF-Origin-Secret
URL:            api.placeupcareer.com/*
Modify header:  Set static
Name:           X-CF-Origin-Secret
Value:          <generate a 32-byte random string>
```

Then in `app/middleware/security.py`, gate non-public routes on the header
being present and matching. The infrastructure for that already exists in
`RouteAccessMiddleware`; add a `cf_origin_secret` field to settings + a check
in `dispatch()` once you've generated the secret.

## 3. Rate limiting at the edge (free tier)

In **Cloudflare → Security → Rate limiting rules**:

```
Rule name:      Aggressive auth limit
URL:            api.placeupcareer.com/api/auth/*
Threshold:      20 requests per 1 minute per IP
Action:         Block for 10 minutes
```

```
Rule name:      Standard API read limit
URL:            api.placeupcareer.com/api/jobs*
Threshold:      300 requests per 1 minute per IP
Action:         Managed challenge for 5 minutes
```

These compound with the in-process limiter in `app/middleware/security.py` —
edge limits stop the flood before it reaches Cloud Run; the app-side limiter
catches anything that slips through CF (e.g. authenticated abuse).

## 4. Bot Fight Mode

**Security → Bots → Bot Fight Mode** → **On**. Free tier blocks the most
obvious crawlers (Headless Chrome, default scrapy User-Agents) without
config. This stops the bulk of the credential-stuffing traffic that
otherwise lights up `/api/auth/signin`.

## 5. Backend already trusts CF

`app/middleware/security.py:_client_ip` reads `CF-Connecting-IP` first.
That means once DNS is proxied, the in-app rate limiter and the access log
both see the real visitor IP — not Cloudflare's edge IP — so 429s and
audit logs stay actionable.

## 6. Quick smoke test

```bash
# Direct hit (bypassing CF) — should still work until you add the CF-only secret check
curl -sI https://placeup-api-rui2a74muq-ue.a.run.app/api/health

# Through CF
curl -sI https://api.placeupcareer.com/api/health | grep -i "cf-ray\|server"
# Expect:  server: cloudflare
#          cf-ray: 89a...
```

If `cf-ray` is present, CF is in the path. If not, the DNS record isn't
proxied (gray cloud) and you should toggle it before tightening any rules.

## Cost

Free plan covers everything in this doc. Pro ($25/mo) adds image
optimization and a higher rate-limit ceiling, but the free WAF + Bot
Fight Mode is enough for the current traffic level.

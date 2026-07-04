# PlaceUp — Zero-Trust Application Security Architecture

"Never trust, always verify." No request is trusted because of where it comes
from; every request proves identity and authorization on its own, credentials
are short-lived, and repeated abuse is contained automatically. This document
maps each zero-trust tenet to the actual code, then gives the infra/IAM
playbook to complete the model at the platform layer.

---

## 1. The five tenets → where they live in code

### Tenet 1 — Verify explicitly (authenticate every request)
- **`app/zero_trust.py` → `principal_from_access_token()`** turns a bearer JWT
  into a verified `Principal` only after checking signature, `exp`, `iat`,
  `sub`, issuer, audience, and `typ == "access"`. Nothing is trusted from an
  unsigned claim.
- **`app/middleware/security.py` → `RouteAccessMiddleware`** is the gate: a
  request reaches a handler only if it matches an explicit public allowlist OR
  carries a valid credential.
- Session revocation is still enforced in `app/security.py → current_user_id`
  (the token's `sid` must map to a live session), so logout/revoke takes
  effect immediately even within a token's 15-minute life.

### Tenet 2 — Least privilege
- **`Principal.scopes`** carries only what the signed token grants. `admin` is
  an explicit superscope, and admin *membership* is authoritative from the
  `ADMIN_EMAILS` allowlist (`app/api/admin.py`), never from a user-writable
  field (that privilege-escalation hole was closed).
- **`require_scope(principal, scope)`** asserts the specific permission a
  handler needs — nothing broader.
- Access tokens live **15 minutes**; refresh tokens rotate and are stored only
  as hashes.

### Tenet 3 — Deny by default
- `RouteAccessMiddleware` refuses anything not explicitly allowed: unknown
  paths, unauthenticated `/api/*`, bad request origins, and traffic that
  bypassed Cloudflare all get the uniform block. Adding a new route is
  *secure by default* — you must consciously add it to a public allowlist to
  expose it.
- **`require_authenticated` / `require_owner`** raise `AccessDenied` on the
  *absence* of proof, so a handler that forgets a check still can't be reached
  anonymously (the middleware already required a principal).

### Tenet 4 — Object-level authorization (stop IDOR)
- **`require_owner(principal, resource_owner_id)`** is the per-object check: a
  caller may touch a resource only if they own it or hold `admin`. Use it any
  time a handler loads a record by an id that could belong to someone else.
- Today most endpoints are already safe because they query by the
  authenticated `current_user_id` rather than an id from the request; the
  only cross-user surface (`/api/admin/users/{id}`) is admin-gated.

### Tenet 5 — Assume breach (contain + observe)
- **Auto-ban** (`BanTracker`): repeated auth/authorization failures from one
  IP trip a temporary block. Tuned by `ZT_BAN_THRESHOLD` (default 8) over
  `ZT_BAN_WINDOW_SECONDS` (300) for `ZT_BAN_DURATION_SECONDS` (900).
  Login, OTP, invite-code, and password-reset failures all feed it, as do
  IDOR probes (a handler-level `AccessDenied`) and direct-to-origin bypass
  attempts. A present-but-expired token does **not** feed it, so real users
  whose token lapsed are never banned.
- **Uniform denial** (`denial_response`): every refusal returns the SAME body —
  no "wrong password vs no such user" oracle, no route-existence leak. It
  always points the user to `SECURITY_CONTACT_EMAIL` (contact@placeupcareer.com)
  and includes a `retry_after` when temporarily blocked.
- **Audit**: `AuditLogMiddleware` logs sensitive-surface access with
  user/IP/status; the `AccessDenied` handler logs the internal reason (never
  returned to the caller).

---

## 2. Service-to-service identity

Internal workers (the scraper job, the ATS-scoring worker) previously
authenticated with one long-lived shared key. Zero-trust replaces that with
short-lived, named, signed identities:

- **`create_service_token("ats-worker", scopes=[...])`** mints an HMAC-signed
  token (`typ: "service"`, `sub: "svc:ats-worker"`, default 5-min TTL,
  audience `placeup-career-internal`).
- Workers send it as **`X-Service-Token`**. `require_internal_api_key` accepts
  it (preferred) or the legacy `X-API-Key` (fallback). A leaked service token
  self-expires and is attributable to a named service; the shared key is the
  break-glass path only.
- Signed with `SERVICE_TOKEN_SECRET` (falls back to `JWT_SECRET` if unset).

Migration: have each worker call `create_service_token(...)` at startup (or
per batch) and attach `X-Service-Token`. Once all workers use it, you can
retire `INTERNAL_API_KEY`.

---

## 3. New environment variables

Set these on Cloud Run (all have safe defaults, so deploying without them
changes nothing):

| Variable | Default | Purpose |
|---|---|---|
| `SECURITY_CONTACT_EMAIL` | `contact@placeupcareer.com` | Shown in every block response |
| `ZT_BAN_THRESHOLD` | `8` | Auth failures per window before temp-ban (0 disables) |
| `ZT_BAN_WINDOW_SECONDS` | `300` | Window over which failures are counted |
| `ZT_BAN_DURATION_SECONDS` | `900` | Temp-ban length |
| `SERVICE_TOKEN_SECRET` | (uses `JWT_SECRET`) | HMAC key for service tokens |
| `SERVICE_TOKEN_TTL_SECONDS` | `300` | Service-token lifetime |

> Note: the auto-ban is in-process (per Cloud Run instance). With >1 instance,
> an attacker's failures spread across instances, so raise the ceiling by
> backing `BanTracker` with Redis (`REDIS_URL`) — the interface is unchanged.
> The Cloudflare edge rate-limit (20/min on `/api/auth` + `/api/invite`) is the
> cross-instance backstop meanwhile.

---

## 4. Infra / IAM playbook (platform layer — clicks, no code)

Application-layer zero-trust only holds if the platform underneath is also
least-privilege. Do these in GCP:

### 4.1 🔴 Lock Cloud Run ingress to Cloudflare
- **Cloud Run → placeup-api → Networking → Ingress:** once the Cloudflare
  origin secret (`CF_ORIGIN_SECRET`) is live and verified, set ingress to
  **Internal + Cloud Load Balancing** behind an external LB, OR keep "All" but
  rely on the app's origin-secret check (already enforced). The secret check
  is the app-level equivalent; the ingress setting is defense-in-depth.

### 4.2 🔴 Least-privilege service accounts
- Give `placeup-api`, the scraper job, and the ATS worker **separate** service
  accounts, each with only the roles it needs (e.g. the API needs Firestore
  read/write + Secret Manager accessor; the scraper needs its data bucket, not
  user Firestore).
- **Remove `roles/editor`** from any of them — default compute SA is
  over-privileged. Grant granular roles instead.

### 4.3 🔴 Secrets in Secret Manager, not env text
- Move `JWT_SECRET`, `INTERNAL_API_KEY`, `SERVICE_TOKEN_SECRET`,
  `CF_ORIGIN_SECRET`, and third-party API keys into **Secret Manager**, and
  reference them in Cloud Run as secret env vars (not plain values). Grant only
  each service's SA `roles/secretmanager.secretAccessor` on the specific
  secrets it uses.

### 4.4 🟡 Rotate + short-lived credentials
- Rotate `JWT_SECRET`/`SERVICE_TOKEN_SECRET` on a schedule. Keep access-token
  TTL short (15 min — already set).

### 4.5 🟡 VPC egress control (optional, higher tier)
- Put the scraper/worker behind a **VPC connector** with egress restricted to
  the specific job-board hosts it scrapes, so a compromised scraper can't
  exfiltrate to arbitrary destinations.

### 4.6 🟡 Firestore Security Rules
- Even though the API mediates all access, set Firestore rules to **deny all
  client access** (only the API's service account reads/writes), so a leaked
  Firebase web config can't be used to read the DB directly.

---

## 5. What a blocked user experiences

Any unauthorized, unverified, or abusive request gets one consistent response:

```json
{
  "detail": "You don't have access to this resource. If you believe this is a
             mistake, please reach out to our team at contact@placeupcareer.com.",
  "contact": "contact@placeupcareer.com"
}
```

If they've tripped the auto-ban, it becomes a 429 with:

```json
{
  "detail": "Access is temporarily blocked. Please wait a few minutes and try
             again. If you believe this is a mistake, reach out to
             contact@placeupcareer.com.",
  "contact": "contact@placeupcareer.com",
  "retry_after": 900
}
```

The frontend can read `detail` and show it directly; `retry_after` (seconds)
tells it when to allow a retry.

---

## 6. Test coverage

`backend/tests/test_zero_trust.py` (26 tests, all passing) covers token→
principal verification (valid, expired, wrong-type, forged-signature,
wrong-audience), service-token round-trips and cross-type rejection,
`require_scope` / `require_owner` (including the IDOR-block and admin-override
cases), the uniform denial payload, and the ban tracker's threshold, window
expiry, per-IP isolation, streak-clear, and disabled-mode behaviour. Run the
full backend suite (`pytest`) on deploy to exercise these alongside the
existing auth/middleware tests.

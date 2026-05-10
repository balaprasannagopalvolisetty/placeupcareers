# PlaceUp Career — Security Pipeline Documentation
**Version:** 4.0.0 · March 2026 · Google Cloud + Firebase Edition  
**Classification:** Confidential — Internal Developer Use Only

> **Google Cloud Migration:** All security infrastructure runs on Google Cloud Platform (GCP). The primary database is **Firebase Firestore** — security is enforced through **Firestore Security Rules** (client-side) and **Firebase Admin SDK** (server-side, bypasses rules). Cloudflare WAF → Google Cloud Armor, AWS GuardDuty → Google Security Command Center, HashiCorp Vault → Google Secret Manager, AWS CloudWatch → Google Cloud Logging, AWS KMS → Google Cloud KMS, PostgreSQL RLS → Firestore Security Rules.

---

## Table of Contents

1. [Security Philosophy](#1-security-philosophy)
2. [8-Layer Defense Stack](#2-8-layer-defense-stack)
3. [Cloud Armor WAF & DDoS Defense](#3-cloud-armor-waf--ddos-defense)
4. [Authentication & Zero Trust](#4-authentication--zero-trust)
5. [Encryption & Data Protection](#5-encryption--data-protection)
6. [Database Security](#6-database-security)
7. [CI/CD Security Pipeline (Cloud Build)](#7-cicd-security-pipeline-cloud-build)
8. [Compliance & Audit](#8-compliance--audit)
9. [Frontend Security](#9-frontend-security)
10. [Incident Response](#10-incident-response)
11. [Security Checklist for Developers](#11-security-checklist-for-developers)

---

## 1. Security Philosophy

PlaceUp uses a **defense-in-depth** strategy across the Google Cloud ecosystem. Every layer is designed as if it is the **last** line of defense. An attacker must bypass **all 8 layers simultaneously** to reach sensitive data.

### Core Principles

| Principle | Implementation |
|-----------|---------------|
| **Zero Trust** | Never trust, always verify. Every request proves identity via Google IAM — including internal Cloud Run services. |
| **Least Privilege** | Each Cloud Run service has a dedicated Service Account with minimum IAM roles. |
| **Assume Breach** | Full Cloud Logging audit trail, Security Command Center anomaly detection, immediate incident response. |
| **Fail Secure** | Every error defaults to deny. Cloud Armor blocks unknown patterns by default. |
| **Data Minimization** | Collect only what is necessary. PII anonymized in Cloud Logging. Purge on schedule via Cloud SQL TTL jobs. |

---

## 2. 8-Layer Defense Stack

```
 Internet
    │
    ▼
┌───────────────────────────────────────────────────────────┐
│  Layer 1 · Edge Security                                   │  ← CRITICAL
│  Google Cloud Armor (WAF + DDoS + IP Reputation)           │
│  Google Cloud CDN (edge caching + SSL offload)             │
└───────────────────────────────────────────────────────────┘
    │
    ▼
┌───────────────────────────────────────────────────────────┐
│  Layer 2 · Load Balancer & SSL                            │  ← HIGH
│  Google Cloud HTTP(S) Load Balancing                       │
│  Managed SSL via Google-managed certificates (TLS 1.3)    │
└───────────────────────────────────────────────────────────┘
    │
    ▼
┌───────────────────────────────────────────────────────────┐
│  Layer 3 · API Gateway                                    │  ← HIGH
│  Google Cloud Apigee — JWT validation, rate limiting       │
└───────────────────────────────────────────────────────────┘
    │
    ▼
┌───────────────────────────────────────────────────────────┐
│  Layer 4 · Application Security                           │  ← HIGH
│  Helmet.js · CORS · Input validation · Firebase Admin SDK  │
│  Cloud Run IAM — no unauthenticated invocation            │
└───────────────────────────────────────────────────────────┘
    │
    ▼
┌───────────────────────────────────────────────────────────┐
│  Layer 5 · Authentication & Sessions                      │  ← CRITICAL
│  Argon2id · JWT RS256 · MFA TOTP · Refresh rotate         │
│  Google Identity Platform (optional social OAuth)          │
└───────────────────────────────────────────────────────────┘
    │
    ▼
┌───────────────────────────────────────────────────────────┐
│  Layer 6 · Data Security                                  │  ← CRITICAL
│  Firebase Firestore (Google AES-256 at rest · TLS 1.3)    │
│  Firestore Security Rules · Cloud KMS key management       │
└───────────────────────────────────────────────────────────┘
    │
    ▼
┌───────────────────────────────────────────────────────────┐
│  Layer 7 · Infrastructure Security                       │  ← HIGH
│  Google Secret Manager · VPC · Artifact Registry scanning  │
│  Cloud Run IAM service accounts · Distroless containers   │
└───────────────────────────────────────────────────────────┘
    │
    ▼
┌───────────────────────────────────────────────────────────┐
│  Layer 8 · Monitoring & Incident Response                 │  ← HIGH
│  Cloud Monitoring · Security Command Center (SCC)          │
│  Cloud Logging · Cloud Error Reporting · PagerDuty         │
└───────────────────────────────────────────────────────────┘
    │
    ▼
 Firebase Firestore — AES-256 encrypted at rest by Google
```

### Layer Details

#### Layer 1 — Edge Security (CRITICAL) — Google Cloud Armor
- **Cloud Armor WAF** — blocks OWASP Top 10 before traffic hits load balancer
- **Adaptive Protection** — ML-based DDoS mitigation, auto-detects volumetric attacks
- **IP reputation filtering** — Google Threat Intelligence integration
- **Bot detection** — distinguishes human traffic from scrapers using reCAPTCHA integration
- **Rate limiting at edge** — 1,000 req/min per IP cap via Cloud Armor
- **reCAPTCHA Enterprise challenge** — triggers on suspicious behavioural patterns
- **SSL/TLS 1.3 only** — TLS 1.0 and 1.1 explicitly blocked via SSL policy
- **Cloud CDN** — edge caching for static assets + SSL offloading

#### Layer 2 — Load Balancer & SSL (HIGH) — Google Cloud Load Balancing
- **Google-managed SSL certificates** — automatic renewal, HSTS preload included
- **HTTP Strict Transport Security (HSTS)** — `max-age=31536000; includeSubDomains; preload`
- **TLS 1.3 minimum** — enforced via GCP SSL policy
- **Health checks** — Cloud Run services automatically get health endpoints
- **Global load balancing** — Anycast IP, routes to nearest healthy region
- **Backend security policy** — Cloud Armor policy attached to backend service

#### Layer 3 — API Gateway (HIGH) — Google Cloud Apigee
- **JWT validation** on every protected route before forwarding to Cloud Run
- **Rate limiting:** 100 req/15min global, 5 req/15min for `/api/auth/*`
- **Request logging** — IP, user agent, timestamp, response code to Cloud Logging
- **API key rotation** — Apigee API key management with automated rotation
- **Strip internal headers** from responses before returning to clients
- **IP restriction** — whitelist admin endpoints to office/VPN IPs only
- **Bot detection plugin** — block non-browser User-Agents on auth routes

#### Layer 4 — Application Security (HIGH)
- **Helmet.js** — sets 11 security HTTP response headers automatically
- **CORS** — strict origin whitelist, credentials only from `FRONTEND_URL`
- **Input validation** — Zod schema validation on **all** request bodies
- **NoSQL injection prevention** — Firebase Admin SDK uses typed APIs (no raw query strings)
- **XSS** — Content Security Policy headers + output encoding
- **CSRF** — SameSite=Strict cookies + origin verification header
- **Cloud Run IAM** — `--no-allow-unauthenticated` on all non-public services
- **Dependency scanning** — Artifact Registry vulnerability scanning on every image push

#### Layer 5 — Authentication & Sessions (CRITICAL)
- Password hashing — Argon2id, 64 MB memory cost, 3 iterations, 4 threads
- JWT access tokens — 15-minute expiry (short-lived)
- Refresh tokens — 7-day expiry, httpOnly cookie, rotated on every use
- MFA — TOTP via Google Authenticator / Authy
- Account lockout — 5 failed attempts → 15-minute cooldown
- **Google Identity Platform** — optional OAuth2 for "Sign in with Google" flow
- Password reset — time-limited tokens (15 min), single-use, HTTPS only
- Session invalidation — immediate on logout, password change, suspicious IP

#### Layer 6 — Data Security (CRITICAL)
- **Encryption at rest** — Firebase Firestore uses Google-managed AES-256 by default (cannot be disabled)
- **Customer-managed keys (CMEK)** — Cloud KMS keys for Firestore CMEK (Blaze plan)
- **Encryption in transit** — TLS 1.3 on all Firestore connections (enforced by Firebase SDK)
- **Field-level encryption** — Sensitive PII fields (MFA secrets, contact emails) encrypted with Cloud KMS before storing in Firestore
- **Firestore Security Rules** — declarative rules enforce multi-tenant isolation for client SDK access
- **Firebase Admin SDK** — server-side (Cloud Run) bypasses rules using service account; never exposed to browser
- **Data minimization** — only collect what is required for service delivery
- **PII anonymization** — client data anonymized in all Cloud Logging entries
- **Secure deletion** — document deletion via Admin SDK + Cloud KMS key destruction for cryptographic erasure
- **No sensitive data in URLs** — no tokens or passwords in query strings

#### Layer 7 — Infrastructure Security (HIGH)
- **Secrets management** — Google Secret Manager (zero hardcoded credentials anywhere)
- **IAM Least Privilege** — each Cloud Run service has a dedicated Service Account
- **VPC** — Cloud SQL not publicly accessible; Cloud Run connects via VPC connector
- **Private Service Connect** — Cloud SQL private IP, no public endpoint
- **Artifact Registry scanning** — automatic CVE scanning on every Docker image push
- **Container Distroless images** — minimal attack surface, no shell access
- **Binary Authorization** — only signed images from trusted Artifact Registry can deploy
- **Organization Policy** — GCP organization constraints prevent public bucket creation etc.

#### Layer 8 — Monitoring & Incident Response (HIGH)
- **Cloud Monitoring** — real-time alerts on anomalous traffic patterns, error rates
- **Security Command Center (SCC)** — ML-based threat detection, replaces AWS GuardDuty
- **Cloud Logging** — all events 90-day retention + BigQuery export for long-term
- **Cloud Trace** — distributed tracing across all Cloud Run microservices
- **Cloud Error Reporting** — automatic error grouping, alerts to PagerDuty
- **Audit trail** — immutable `audit_logs` table + Cloud Audit Logs for GCP API calls
- **PagerDuty** — on-call escalation for P0/P1 incidents (GCP integration available)
- **Penetration testing** — quarterly third-party pen test

---

## 3. Cloud Armor WAF & DDoS Defense

### 3.1 Cloud Armor Security Policy Setup

```bash
# Create a Cloud Armor security policy
gcloud compute security-policies create placeup-waf-policy \
  --description="PlaceUp Career WAF Policy"

# Rule 1: Pre-configured OWASP Top 10 protections
gcloud compute security-policies rules create 1000 \
  --security-policy=placeup-waf-policy \
  --expression="evaluatePreconfiguredExpr('sqli-v33-stable')" \
  --action=deny-403 \
  --description="Block SQL injection"

gcloud compute security-policies rules create 1001 \
  --security-policy=placeup-waf-policy \
  --expression="evaluatePreconfiguredExpr('xss-v33-stable')" \
  --action=deny-403 \
  --description="Block XSS"

gcloud compute security-policies rules create 1002 \
  --security-policy=placeup-waf-policy \
  --expression="evaluatePreconfiguredExpr('lfi-v33-stable')" \
  --action=deny-403 \
  --description="Block path traversal / LFI"

# Rule 2: Rate limit auth endpoints — 5 req/min
gcloud compute security-policies rules create 2000 \
  --security-policy=placeup-waf-policy \
  --expression="request.path.matches('/api/auth/.*')" \
  --action=throttle \
  --rate-limit-threshold-count=5 \
  --rate-limit-threshold-interval-sec=60 \
  --conform-action=allow \
  --exceed-action=deny-429 \
  --enforce-on-key=IP \
  --description="Strict auth rate limit"

# Rule 3: reCAPTCHA Enterprise for suspicious IPs
gcloud compute security-policies rules create 3000 \
  --security-policy=placeup-waf-policy \
  --expression="request.headers['user-agent'].size() == 0" \
  --action=deny-403 \
  --description="Block requests without User-Agent"

# Rule 4: Block requests without User-Agent
gcloud compute security-policies rules create 4000 \
  --security-policy=placeup-waf-policy \
  --expression="origin.region_code == 'KP'" \
  --action=deny-403 \
  --description="Block from high-risk regions (customize as needed)"

# Attach policy to backend service (Load Balancer)
gcloud compute backend-services update placeup-api-backend \
  --security-policy=placeup-waf-policy \
  --global

# Enable Adaptive Protection (ML-based DDoS)
gcloud compute security-policies update placeup-waf-policy \
  --enable-layer7-ddos-defense
```

### 3.2 DDoS Mitigation Matrix (Google Cloud)

| Attack Type | GCP Protection | Threshold | Response |
|-------------|---------------|-----------|----------|
| L3/L4 Volumetric | Google's global network scrubbing | Any volume | Auto-absorbed at Google's edge |
| L7 HTTP Flood | Cloud Armor Adaptive Protection | 500 req/min/IP | ML-based: warn → throttle → block |
| Slowloris | Cloud Run max concurrency + timeouts | 60s request timeout | Automatic timeout & close |
| API Abuse | Cloud Armor rate limiting per endpoint | 100 req/15min global | 429 Too Many Requests |
| Credential Stuffing | Auth rate limit + reCAPTCHA Enterprise | 5 failures/15min | Lock + Cloud Monitoring alert |
| Bot Traffic | Cloud Armor bot management (reCAPTCHA) | Automated detection | Challenge or block bots |

### 3.3 Cloud Armor Custom Rules (CEL Expressions)

```bash
# Advanced CEL rule examples for Cloud Armor

# Block SQL injection in query params
--expression="request.query.matches('(?i)(union|select|insert|update|delete|drop|exec)')"

# Block XSS in request body
--expression="request.body.matches('(?i)(<script|javascript:|onerror=|onload=)')"

# Geo-restriction example (allow only USA + Canada)
--expression="!origin.region_code.matches('US|CA')"

# Block requests to admin from non-VPN IPs
--expression="request.path.matches('/api/admin/.*') && !inIpRange(origin.ip, '10.0.0.0/8')"
```

---

## 4. Authentication & Zero Trust

### 4.1 JWT Implementation (`src/auth/jwt.js`)

```javascript
import jwt            from 'jsonwebtoken';
import { randomBytes } from 'crypto';

const ACCESS_EXPIRY  = '15m';
const REFRESH_EXPIRY = '7d';

export const signAccessToken = (payload) =>
  jwt.sign(payload, process.env.JWT_PRIVATE_KEY, {
    expiresIn: ACCESS_EXPIRY,
    algorithm: 'RS256',
    issuer:    'placeupcareer.com',
    audience:  'placeup-api',
  });

export const signRefreshToken = async (userId) => {
  const token = randomBytes(64).toString('hex');
  const hash  = hashToken(token);
  await db.refreshToken.create({ data: { userId, hash, expiresAt: add7Days() } });
  return token;
};

export const rotateRefreshToken = async (incomingToken) => {
  const hash   = hashToken(incomingToken);
  const stored = await db.refreshToken.findUnique({ where: { hash } });
  if (!stored || stored.expiresAt < new Date()) throw new Error('INVALID_TOKEN');
  await db.refreshToken.delete({ where: { hash } });
  return issueNewRefreshToken(stored.userId);
};
```

### 4.2 Google Identity Platform (Optional — "Sign in with Google")

```javascript
// src/auth/googleOAuth.js — optional social login
import { OAuth2Client } from 'google-auth-library';

const client = new OAuth2Client(process.env.GOOGLE_CLIENT_ID);

export async function verifyGoogleToken(idToken) {
  const ticket = await client.verifyIdToken({
    idToken,
    audience: process.env.GOOGLE_CLIENT_ID,
  });
  const payload = ticket.getPayload();
  return {
    googleId: payload.sub,
    email:    payload.email,
    name:     payload.name,
    picture:  payload.picture,
    verified: payload.email_verified,
  };
}

// Frontend sends the Google ID token → backend verifies with Google
// then issues a PlaceUp JWT for session management
router.post('/api/auth/google', async (req, res) => {
  const profile = await verifyGoogleToken(req.body.credential);
  const user    = await findOrCreateUser(profile);
  const tokens  = await issueTokens(user.id);
  res.json(tokens);
});
```

### 4.3 MFA — TOTP Setup (`src/auth/mfa.js`)

```javascript
import speakeasy from 'speakeasy';
import qrcode    from 'qrcode';

export const setupMFA = async (userId) => {
  const secret = speakeasy.generateSecret({ length: 32 });
  // Encrypt MFA secret using Cloud KMS before storing
  const encryptedSecret = await encryptWithKMS(secret.base32);
  await db.client.update({
    where: { id: userId },
    data:  { mfa_secret: encryptedSecret },
  });
  const otpUrl = speakeasy.otpauthURL({
    secret: secret.base32,
    label:  'PlaceUp Career',
    issuer: 'PlaceUp Career',
  });
  return qrcode.toDataURL(otpUrl);
};

export const verifyMFA = (secret, token) =>
  speakeasy.totp.verify({ secret, encoding: 'base32', token, window: 1 });
```

### 4.4 Cloud KMS Encryption for PII (`src/crypto/kms.js`)

Google Cloud KMS replaces pgcrypto application-level keys for envelope encryption:

```javascript
import { KeyManagementServiceClient } from '@google-cloud/kms';

const kmsClient = new KeyManagementServiceClient();

const KEY_NAME = `projects/${process.env.GCP_PROJECT_ID}/locations/us-central1` +
                 `/keyRings/placeup-keyring/cryptoKeys/placeup-pii-key`;

export async function encryptWithKMS(plaintext) {
  const [result] = await kmsClient.encrypt({
    name:      KEY_NAME,
    plaintext: Buffer.from(plaintext),
  });
  return result.ciphertext.toString('base64');
}

export async function decryptWithKMS(ciphertext) {
  const [result] = await kmsClient.decrypt({
    name:       KEY_NAME,
    ciphertext: Buffer.from(ciphertext, 'base64'),
  });
  return result.plaintext.toString('utf8');
}
```

```bash
# Create Cloud KMS keyring and key
gcloud kms keyrings create placeup-keyring --location=us-central1

gcloud kms keys create placeup-pii-key \
  --location=us-central1 \
  --keyring=placeup-keyring \
  --purpose=encryption \
  --rotation-period=90d \
  --next-rotation-time=$(date -u -d '+90 days' +%Y-%m-%dT%H:%M:%SZ)
```

### 4.5 Password Hashing — Argon2id (`src/auth/password.js`)

```javascript
import argon2 from 'argon2';

const ARGON2_CONFIG = {
  type:        argon2.argon2id,
  memoryCost:  65536,
  timeCost:    3,
  parallelism: 4,
};

export const hashPassword   = (plain) => argon2.hash(plain, ARGON2_CONFIG);
export const verifyPassword = (hash, plain) => argon2.verify(hash, plain);
```

### 4.6 Zero Trust with Google Cloud IAM

| Principle | GCP Implementation | Status |
|-----------|-------------------|--------|
| Verify explicitly | Every API request validates JWT + Cloud Run OIDC token verification | ✓ Implemented |
| Least privilege | Each Cloud Run service has a dedicated Service Account with minimum roles | ✓ Implemented |
| Assume breach | Cloud Logging captures all actions; SCC alerts on anomaly | ✓ Implemented |
| Micro-segmentation | Cloud Run services communicate via VPC connector only (no public internet) | ✓ Implemented |
| Device trust | User agent + IP logged in Cloud Logging; anomaly triggers re-auth | ✓ Implemented |
| Continuous validation | Token expiry 15 min — forced re-validation; Cloud Armor blocks abnormal patterns | ✓ Implemented |

### 4.7 Account Lockout Flow

```
Attempt 1–4: Login allowed, failed attempts logged to audit_logs + Cloud Logging
Attempt 5:   Account locked for 15 minutes
             → Cloud Monitoring alert fired: "5 failed logins for user {email} from IP {ip}"
             → Cloud Armor rate-limit rule auto-throttles the IP
Attempt 10+: SCC anomaly detection flags → PagerDuty escalation (credential stuffing)
```

---

## 5. Encryption & Data Protection

### 5.1 Encryption Overview

| Data | At Rest | In Transit | Key Management |
|------|---------|-----------|----------------|
| Cloud SQL DB | AES-256 (Google-managed) | TLS 1.3 (require-ssl) | Google-managed default keys |
| Cloud SQL DB (CMEK) | AES-256 (Cloud KMS) | TLS 1.3 | Cloud KMS — customer controls key lifecycle |
| PII fields (MFA secrets, contact emails) | Cloud KMS envelope encryption | TLS 1.3 | Cloud KMS — 90-day auto-rotation |
| GCS backups | AES-256 (Google-managed or CMEK) | TLS 1.3 | Cloud KMS |
| API keys | Argon2id hash | TLS 1.3 | Never stored plaintext |
| Passwords | Argon2id (64 MB / 3 iter) | TLS 1.3 | Hash only — never stored |
| JWT signing key | RS256 private key | N/A | Google Secret Manager |
| Stripe payment data | Stripe handles entirely | TLS 1.3 | Stripe — never on PlaceUp servers |
| Session tokens (refresh) | SHA-256 hash in Cloud SQL | httpOnly cookie | Rotated on every use |

### 5.2 Field-Level Encryption for PII (Cloud KMS + Firestore)

Firebase Firestore stores all data encrypted at rest by default (Google-managed AES-256). For sensitive PII fields (MFA secrets, contact emails), an extra layer of application-level encryption uses **Cloud KMS envelope encryption** before writing to Firestore:

```javascript
// src/crypto/fieldEncrypt.js
import { encryptWithKMS, decryptWithKMS } from './kms.js';

/**
 * Encrypt a string field before writing to Firestore
 * (used for: mfa_secret, contact_email)
 */
export async function encryptField(plaintext) {
  return encryptWithKMS(plaintext);  // returns base64 ciphertext
}

/**
 * Decrypt a field read from Firestore
 * (server-side only, never in client SDK)
 */
export async function decryptField(ciphertext) {
  return decryptWithKMS(ciphertext);
}

// Usage when writing a job's contact email:
const encryptedEmail = await encryptField(contact.email);
await db.collection('jobs').doc(jobId).update({
  contact_email: encryptedEmail,   // stored as encrypted base64 in Firestore
});

// Usage when reading for Pro/Elite clients (server-side only):
const jobDoc = await db.collection('jobs').doc(jobId).get();
const plainEmail = await decryptField(jobDoc.data().contact_email);
```

### 5.3 Secrets Management — Google Secret Manager

Google Secret Manager replaces HashiCorp Vault:

```bash
# Store all production secrets in Secret Manager
gcloud secrets create JWT_PRIVATE_KEY \
  --replication-policy=user-managed \
  --locations=us-central1

gcloud secrets create STRIPE_SECRET_KEY \
  --replication-policy=automatic

# Add secret versions
echo -n "your_secret_value" | gcloud secrets versions add JWT_PRIVATE_KEY --data-file=-

# Access a secret in application code
import { SecretManagerServiceClient } from '@google-cloud/secret-manager';

const client = new SecretManagerServiceClient();

async function getSecret(name) {
  const [version] = await client.accessSecretVersion({
    name: `projects/${process.env.GCP_PROJECT_ID}/secrets/${name}/versions/latest`,
  });
  return version.payload.data.toString('utf8');
}

# Application retrieves secrets at startup
const jwtPrivateKey = await getSecret('JWT_PRIVATE_KEY');

# Automatic 90-day rotation via Cloud KMS key rotation policy
gcloud secrets versions add JWT_PRIVATE_KEY \
  --data-file=./new-key.pem
```

### 5.4 Backup Security (Google Cloud Storage)

```bash
# Create GCS backup bucket with lifecycle rules
gcloud storage buckets create gs://placeup-backups \
  --location=us-east1 \
  --uniform-bucket-level-access

# Enable CMEK encryption on the bucket
gcloud storage buckets update gs://placeup-backups \
  --default-encryption-key=projects/placeup-career-prod/locations/us-central1/keyRings/placeup-keyring/cryptoKeys/placeup-backup-key

# Bucket lifecycle: delete after 30 days, archive quarterly snapshots after 1 year
gcloud storage buckets update gs://placeup-backups \
  --lifecycle-file=./lifecycle.json
```

| Property | Implementation |
|----------|---------------|
| Automated backups | Cloud SQL PITR (Point-in-Time Recovery) — every 5 minutes |
| Backup encryption | CMEK via Cloud KMS before GCS upload |
| Backup retention | 30-day rolling + quarterly snapshots for 1 year |
| Recovery testing | Monthly restore drill — verify backup integrity |
| Geo-redundancy | GCS multi-region bucket (`us` multi-region) |
| Key management | Cloud KMS — separate key from application encryption key |

---

## 6. Database Security

### 6.1 Firestore Security Rules (Client-Side Access Control)

Firestore Security Rules replace PostgreSQL Row-Level Security. Rules are evaluated for every request from the **client SDK** (browser). The **Firebase Admin SDK** (used by Cloud Run services) bypasses rules entirely and has full access — it must never be exposed to the browser.

```javascript
// firestore.rules
rules_version = '2';
service cloud.firestore {
  match /databases/{database}/documents {

    // Helper: verify the caller is authenticated and owns the document
    function isOwner(userId) {
      return request.auth != null && request.auth.uid == userId;
    }

    // Jobs — readable by any authenticated user; writes via Admin SDK only
    match /jobs/{jobId} {
      allow read: if request.auth != null;
      allow write: if false;  // Admin SDK only (fetcher Cloud Run Job)
    }

    // Clients — can only read/update own document
    match /clients/{userId} {
      allow read, update: if isOwner(userId);
      allow create:       if false;  // registration via server API only
      allow delete:       if false;  // GDPR deletion via server API only
    }

    // Client resumes subcollection
    match /clients/{userId}/resumes/{resumeId} {
      allow read, write: if isOwner(userId);
    }

    // Alert prefs — own document only
    match /alertPrefs/{userId} {
      allow read, write: if isOwner(userId);
    }

    // Payments — read-only, own records only
    match /payments/{paymentId} {
      allow read: if request.auth != null &&
                     resource.data.client_id == request.auth.uid;
      allow write: if false;  // Stripe webhook via server API only
    }

    // Audit logs — no client access whatsoever
    match /auditLogs/{logId} {
      allow read, write: if false;  // Admin SDK only
    }

    // H1B Sponsors — readable by authenticated users
    match /h1bSponsors/{sponsorId} {
      allow read:  if request.auth != null;
      allow write: if false;  // quarterly import job only
    }
  }
}
```

### 6.2 Firebase Admin SDK — Server-Side Access

All Cloud Run services access Firestore via the **Firebase Admin SDK** using Application Default Credentials (ADC). The Admin SDK bypasses Security Rules and is the only way to perform privileged writes (job ingestion, payment updates, audit logging):

```javascript
// src/db/firebase.js — used by all Cloud Run services
import admin from 'firebase-admin';

if (!admin.apps.length) {
  admin.initializeApp({
    credential: admin.credential.applicationDefault(),
    projectId:  process.env.GCP_PROJECT_ID,
  });
}

export const db    = admin.firestore();
export const fauth = admin.auth();   // Firebase Auth (if used)
export { admin };
```

```bash
# Grant Firestore access to Cloud Run service accounts
gcloud projects add-iam-policy-binding placeup-career-prod \
  --member="serviceAccount:api-sa@placeup-career-prod.iam.gserviceaccount.com" \
  --role="roles/datastore.user"        # Firestore read/write

gcloud projects add-iam-policy-binding placeup-career-prod \
  --member="serviceAccount:fetcher-sa@placeup-career-prod.iam.gserviceaccount.com" \
  --role="roles/datastore.user"        # Fetcher: jobs + h1bSponsors
```

### 6.3 Firestore IAM Roles

| Service Account | IAM Role | Collections Accessed |
|-----------------|----------|---------------------|
| `api-sa` | `roles/datastore.user` | clients, jobs, payments, alertPrefs, auditLogs |
| `fetcher-sa` | `roles/datastore.user` | jobs, h1bSponsors, auditLogs |
| `enricher-sa` | `roles/datastore.user` | jobs (update contact fields) |
| `alerts-sa` | `roles/datastore.viewer` | alertPrefs, clients (read-only) |
| `admin-sa` | `roles/datastore.owner` | All collections (admin dashboard) |

### 6.4 Audit Log Collection (Immutable — Admin SDK Only)

Firestore Security Rules block all client SDK access to `auditLogs`. Server-side writes use Admin SDK:

```javascript
// src/middleware/audit.js
import { db, admin } from '../db/firebase.js';

export async function auditLog(userId, event, metadata = {}, req = null) {
  await db.collection('auditLogs').add({
    client_id:  userId || null,
    event,
    ip_address: req?.ip || null,
    user_agent: req?.headers?.['user-agent'] || null,
    metadata:   { ...metadata, timestamp: new Date().toISOString() },
    createdAt:  admin.firestore.FieldValue.serverTimestamp(),
  });
}

// Usage:
// await auditLog(req.user.id, 'USER_LOGIN',      { success: true }, req);
// await auditLog(req.user.id, 'CONTACT_UNLOCKED', { jobId, companyName }, req);
// await auditLog(req.user.id, 'SUSPICIOUS_ACTIVITY', { reason: 'ip_change' }, req);
```

**Events logged to `auditLogs` collection:**

| Event | Trigger |
|-------|---------|
| `USER_LOGIN` | Every login attempt (success and failure) with IP |
| `USER_REGISTER` | New account creation |
| `PASSWORD_RESET` | Password changed |
| `MFA_ENABLED` | 2FA activated |
| `PAYMENT_SUCCESS` | Subscription payment |
| `PLAN_UPGRADE` | Plan change |
| `DATA_EXPORT` | Client downloads their GDPR export |
| `CONTACT_UNLOCKED` | Hiring manager email viewed (Pro/Elite) |
| `ADMIN_ACTION` | Any admin dashboard action |
| `SUSPICIOUS_ACTIVITY` | Multiple failed logins, unusual IP pattern |

### 6.5 Firestore CMEK (Customer-Managed Encryption Keys)

On the **Blaze (pay-as-you-go) plan**, Firestore supports CMEK via Cloud KMS:

```bash
# Enable Firestore CMEK (must be done at database creation time)
gcloud firestore databases create \
  --location=us-central1 \
  --type=firestore-native \
  --kms-key-name=projects/placeup-career-prod/locations/us-central1/keyRings/placeup-keyring/cryptoKeys/placeup-firestore-key

# Create the Firestore KMS key
gcloud kms keys create placeup-firestore-key \
  --location=us-central1 \
  --keyring=placeup-keyring \
  --purpose=encryption \
  --rotation-period=365d
```

---

## 7. CI/CD Security Pipeline (Cloud Build)

### 7.1 Cloud Build Security Pipeline (`cloudbuild.yaml`)

```yaml
steps:
  # ── Stage 1: Dependency Security Scan ──────────────────────────
  - name: 'node:20-alpine'
    id: snyk-scan
    entrypoint: 'sh'
    args:
      - '-c'
      - |
        npm install -g snyk
        snyk test --severity-threshold=high --fail-on=all
    secretEnv: ['SNYK_TOKEN']

  # ── Stage 2: OWASP Dependency Check ────────────────────────────
  - name: 'owasp/dependency-check'
    id: owasp-check
    waitFor: ['snyk-scan']
    args:
      - '--project=PlaceUp Career'
      - '--scan=/workspace'
      - '--format=JSON'
      - '--out=/workspace/reports'
      - '--failOnCVSS=7'

  # ── Stage 3: Unit Tests ─────────────────────────────────────────
  - name: 'node:20-alpine'
    id: run-tests
    waitFor: ['snyk-scan']
    entrypoint: 'sh'
    args: ['-c', 'npm ci && npm test -- --coverage']

  # ── Stage 4: Build Distroless Docker Image ──────────────────────
  - name: 'gcr.io/cloud-builders/docker'
    id: build-image
    waitFor: ['run-tests']
    args:
      - 'build'
      - '-t'
      - 'us-central1-docker.pkg.dev/$PROJECT_ID/placeup/api:$COMMIT_SHA'
      - '--file=Dockerfile.distroless'
      - '.'

  # ── Stage 5: Push to Artifact Registry ─────────────────────────
  - name: 'gcr.io/cloud-builders/docker'
    id: push-image
    waitFor: ['build-image']
    args:
      - 'push'
      - 'us-central1-docker.pkg.dev/$PROJECT_ID/placeup/api:$COMMIT_SHA'

  # ── Stage 6: Artifact Registry Vulnerability Scan ───────────────
  - name: 'gcr.io/google.com/cloudsdktool/cloud-sdk'
    id: artifact-vulnerability-scan
    waitFor: ['push-image']
    entrypoint: 'bash'
    args:
      - '-c'
      - |
        # Wait for scan to complete (Artifact Registry scans automatically on push)
        gcloud artifacts docker images describe \
          us-central1-docker.pkg.dev/$PROJECT_ID/placeup/api:$COMMIT_SHA \
          --show-package-vulnerability \
          --format='value(vulnerabilityDetails.summary.fixableCriticalCount)' | \
        xargs -I{} bash -c '[ {} -eq 0 ] || (echo "CRITICAL CVEs found!" && exit 1)'

  # ── Stage 7: Sign Image with Binary Authorization ───────────────
  - name: 'gcr.io/google.com/cloudsdktool/cloud-sdk'
    id: sign-image
    waitFor: ['artifact-vulnerability-scan']
    entrypoint: 'bash'
    args:
      - '-c'
      - |
        gcloud beta container binauthz attestations sign-and-create \
          --artifact-url="us-central1-docker.pkg.dev/$PROJECT_ID/placeup/api:$COMMIT_SHA" \
          --attestor=projects/$PROJECT_ID/attestors/placeup-attestor \
          --keyversion=projects/$PROJECT_ID/locations/us-central1/keyRings/placeup-keyring/cryptoKeys/binauthz-key/cryptoKeyVersions/1

  # ── Stage 8: Deploy to Cloud Run (Production) ───────────────────
  - name: 'gcr.io/google.com/cloudsdktool/cloud-sdk'
    id: deploy-production
    waitFor: ['sign-image']
    entrypoint: 'gcloud'
    args:
      - 'run'
      - 'deploy'
      - 'placeup-api'
      - '--image=us-central1-docker.pkg.dev/$PROJECT_ID/placeup/api:$COMMIT_SHA'
      - '--region=us-central1'
      - '--platform=managed'
      - '--no-allow-unauthenticated'

availableSecrets:
  secretManager:
    - versionName: projects/$PROJECT_ID/secrets/SNYK_TOKEN/versions/latest
      env: 'SNYK_TOKEN'

options:
  logging: CLOUD_LOGGING_ONLY
  machineType: E2_HIGHCPU_8

# Cloud Build trigger: fires on push to main branch
# Configure in: Cloud Build → Triggers → Connect GitHub repo
```

### 7.2 Security Gate Requirements

Every push to `main` must pass **all** gates before deploying:

| Gate | Tool | Threshold | Action on Fail |
|------|------|-----------|----------------|
| Dependency CVE scan | Snyk | HIGH or CRITICAL | Block deploy |
| OWASP Dependency Check | OWASP DC | CVSS ≥ 7.0 | Block deploy |
| Container CVE scan | Artifact Registry | Any CRITICAL | Block push |
| Binary Authorization | Cloud Binary Auth | Unsigned image | Block Cloud Run deploy |
| Unit & integration tests | Jest / Supertest | Any failure | Block deploy |
| Code coverage | Jest | < 80% | Warn (not block) |
| Secret detection | Secret Scanning (GitHub + Cloud Build) | Any secret found | Block immediately |
| Linting & type check | ESLint + TypeScript | Any error | Block deploy |

### 7.3 Cloud Build Daily Security Scan

```bash
# Create a daily Cloud Scheduler trigger for security scans
gcloud scheduler jobs create http daily-security-scan \
  --schedule="0 6 * * *" \
  --uri="https://cloudbuild.googleapis.com/v1/projects/placeup-career-prod/builds" \
  --message-body='{"source":{"repoSource":{"repoName":"placeup-career","branchName":"main"}},"steps":[{"name":"node:20","entrypoint":"npx","args":["snyk","monitor"]}]}' \
  --oauth-service-account-email=scheduler-sa@placeup-career-prod.iam.gserviceaccount.com \
  --time-zone="UTC"
```

### 7.4 Binary Authorization Policy

```yaml
# binauthz-policy.yaml — only signed images from Cloud Build can deploy
defaultAdmissionRule:
  evaluationMode: REQUIRE_ATTESTATION
  enforcementMode: ENFORCED_BLOCK_AND_AUDIT_LOG
  requireAttestationsBy:
    - projects/placeup-career-prod/attestors/placeup-attestor

clusterAdmissionRules: {}
```

```bash
# Apply Binary Authorization policy to Cloud Run
gcloud beta run services update placeup-api \
  --binary-authorization=default \
  --region=us-central1
```

---

## 8. Compliance & Audit

### 8.1 Compliance Standards

| Standard | Requirement | PlaceUp Implementation | Status |
|----------|-------------|------------------------|--------|
| **PCI-DSS** | No card data on servers | Stripe handles all card processing | ✓ Compliant |
| **GDPR** | Data subject rights, privacy by design | Privacy policy, data export, deletion APIs | ✓ Ready |
| **CCPA** | California privacy rights | Opt-out, data access, deletion endpoints | ✓ Ready |
| **SOC 2 Type I** | Security controls documented | Architecture docs + Cloud Audit Logs + Cloud Logging | ✓ In Progress |
| **CAN-SPAM** | Cold email compliance | Unsubscribe links, sender identity via Google Workspace | ✓ Compliant |
| **CASL** | Canadian anti-spam | Consent-based outreach only | ✓ Compliant |

### 8.2 GDPR Data Rights Endpoints

| GDPR Right | HTTP Endpoint | Notes |
|------------|--------------|-------|
| Right to access | `GET /api/clients/me/export` | Returns all data as JSON archive |
| Right to deletion | `DELETE /api/clients/me` | Anonymizes PII, deletes account |
| Right to portability | CSV export of job applications + profile | Available to all plans |
| Right to rectification | `PUT /api/clients/me` | Update profile at any time |

### 8.3 Google Cloud Audit Logs

All GCP API calls are automatically logged to **Cloud Audit Logs** (cannot be disabled):

```bash
# View Cloud Audit Logs for Cloud SQL access
gcloud logging read \
  'logName="projects/placeup-career-prod/logs/cloudaudit.googleapis.com%2Fdata_access"' \
  --limit=50 \
  --format=json

# Export Cloud Audit Logs to BigQuery for long-term analysis
gcloud logging sinks create placeup-audit-export \
  bigquery.googleapis.com/projects/placeup-career-prod/datasets/audit_logs \
  --log-filter='logName:"cloudaudit.googleapis.com"'
```

### 8.4 Data Retention Policy

| Data Type | Retention Period | Deletion Method |
|-----------|-----------------|-----------------|
| Active client data | Active + 2 years after cancellation | Firestore document deletion + Cloud KMS key destruction |
| Payment records | 7 years (legal requirement) | Anonymize PII fields, retain transaction IDs in Firestore |
| Cloud Audit Logs | 5 years (BigQuery export) | Append-only `auditLogs` collection — never deleted |
| Cloud Logging entries | 90 days (extended in BigQuery) | Automatic log sink to BigQuery |
| Job listings | 30 days from posting | Firestore batch delete via Cloud Scheduler cron |
| Redis sessions | 15 minutes (access) / 7 days (refresh) | Automatic Memorystore TTL expiry |

---

## 9. Frontend Security

### 9.1 Token Storage Strategy

```
❌ NEVER:   localStorage.setItem('token', jwt)    — vulnerable to XSS
❌ NEVER:   sessionStorage.setItem('token', jwt)  — vulnerable to XSS

✓ CORRECT:  Access token → JavaScript memory (React context store)
✓ CORRECT:  Refresh token → httpOnly + SameSite=Strict + Secure cookie
             (JavaScript cannot read httpOnly cookies)
```

### 9.2 Axios Security Interceptors (`src/lib/api.ts`)

```typescript
import axios from 'axios';
import { getToken, setToken, clearToken } from '../store/authStore';

const api = axios.create({
  baseURL:         import.meta.env.VITE_API_URL,
  withCredentials: true,
});

api.interceptors.request.use(config => {
  const token = getToken();
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

api.interceptors.response.use(
  res => res,
  async err => {
    if (err.response?.status === 401 && !err.config._retry) {
      err.config._retry = true;
      try {
        const { data } = await axios.post('/api/auth/refresh', {}, { withCredentials: true });
        setToken(data.accessToken);
        err.config.headers.Authorization = `Bearer ${data.accessToken}`;
        return api.request(err.config);
      } catch {
        clearToken();
        window.location.href = '/login';
      }
    }
    return Promise.reject(err);
  }
);

export default api;
```

### 9.3 Route Guards (`src/components/ProtectedRoute.tsx`)

```typescript
import { Navigate, Outlet } from 'react-router';
import { useAuthStore }     from '../store/authStore';
import { usePlan }          from '../hooks/usePlan';

export function ProtectedRoute() {
  const { isAuthenticated } = useAuthStore();
  return isAuthenticated ? <Outlet /> : <Navigate to="/login" replace />;
}

export function PlanRoute({ minPlan }: { minPlan: 'pro' | 'elite' }) {
  const { plan, isActive } = usePlan();
  const planRank = { starter: 1, pro: 2, elite: 3 };
  const hasAccess = isActive && planRank[plan] >= planRank[minPlan];
  return hasAccess ? <Outlet /> : <Navigate to="/pricing?upgrade=true" replace />;
}
```

### 9.4 Content Security Policy

Set via Helmet.js on the backend:

```
Content-Security-Policy:
  default-src 'self';
  script-src  'self' https://js.stripe.com https://www.recaptcha.net;
  frame-src   https://js.stripe.com https://www.recaptcha.net;
  connect-src 'self' https://api.stripe.com https://www.googleapis.com;
  img-src     'self' data: https:;
  style-src   'self' 'unsafe-inline';
```

> `unsafe-inline` for styles is acceptable; `unsafe-inline` for scripts is **never** acceptable.

### 9.5 Frontend Security Checklist

- [ ] JWT access token in JavaScript memory only (never `localStorage`)
- [ ] Refresh token in `httpOnly; SameSite=Strict; Secure` cookie
- [ ] Axios auto-refresh interceptor in place
- [ ] All user-generated content rendered through DOMPurify before `dangerouslySetInnerHTML`
- [ ] Stripe.js loaded from Stripe CDN — payment form is an iframe (card data never in your JS)
- [ ] Route guards on all authenticated pages
- [ ] Plan guards on Pro/Elite feature pages
- [ ] CSP headers matching backend Helmet.js config
- [ ] No API keys in `VITE_` prefixed env vars except `STRIPE_PUBLISHABLE_KEY`
- [ ] reCAPTCHA Enterprise token sent on all auth form submissions

---

## 10. Incident Response

### 10.1 Severity Levels

| Level | Description | Response Time | Escalation |
|-------|-------------|--------------|------------|
| **P0 — Critical** | Data breach, payment system down, auth bypass | 15 minutes | PagerDuty → All engineers |
| **P1 — High** | Scheduler down 3+ cycles, Cloud SQL unreachable, sustained DDoS | 1 hour | PagerDuty → On-call engineer |
| **P2 — Medium** | Single fetch cycle failure, elevated error rate | 4 hours | Cloud Monitoring alert → Responsible engineer |
| **P3 — Low** | Monitoring gap, failed backup, minor performance | Next business day | GitHub issue |

### 10.2 Breach Response Protocol

```
1. DETECT     → Security Command Center (SCC) / Cloud Monitoring fires anomaly alert
2. CONTAIN    → Cloud Armor auto-blocks suspicious IPs
               → Revoke all active JWT tokens (rotate JWT_PRIVATE_KEY in Secret Manager)
               → Disable affected user accounts
               → Revoke compromised Cloud Run service account keys
3. ASSESS     → Review audit_logs table for scope of compromise
               → Review Cloud Audit Logs for GCP API calls
               → Identify what data may have been accessed
4. NOTIFY     → Inform affected users within 72 hours (GDPR requirement)
               → File regulatory notification if required (>500 records)
5. REMEDIATE  → Patch vulnerability via Cloud Build pipeline
               → Rotate all secrets in Google Secret Manager
               → Force password reset for affected users
               → Rotate Cloud KMS keys
6. REVIEW     → Post-mortem within 48 hours
               → Update Cloud Armor security policy rules
               → Schedule additional pen test
```

### 10.3 Automated Security Responses (Cloud Monitoring Alerting)

| Trigger | Automated Action |
|---------|-----------------|
| 10+ failed logins from same IP in 5 min | Cloud Armor auto-block IP + Cloud Monitoring alert → Slack |
| 50+ failed logins in 5 min | PagerDuty page + temporary Cloud Armor global auth throttle |
| SQL injection pattern detected | Cloud Armor WAF block + log to Cloud Logging |
| SCC anomaly: unusual data export volume | Flag account + alert admin via Cloud Monitoring |
| Payment webhook HMAC failure | Reject with 400 + log attempted forgery |
| JWT with invalid signature | Reject with 401 + log anomaly to Cloud Logging |
| Admin endpoint accessed from unexpected IP | Cloud Armor block + require MFA re-verify |
| Cloud Run service account key rotation due | Automated alert 7 days before expiry |

---

## 11. Security Checklist for Developers

Run this checklist before every PR merge and before every production deployment.

### General Security

- [ ] No secrets, API keys, or passwords committed to Git
- [ ] All environment variables loaded from Google Secret Manager (never `.env` in prod)
- [ ] All new API endpoints have authentication middleware
- [ ] All new API endpoints have input validation (Zod)
- [ ] No raw Firestore queries constructed from unsanitized user input
- [ ] Argon2id used for any new password storage
- [ ] Audit log calls added for any new sensitive user action

### Google Cloud + Firebase Specific

- [ ] New Cloud Run service has its own dedicated Service Account
- [ ] Service Account has minimum required IAM roles (least privilege)
- [ ] New Cloud Run service deployed with `--no-allow-unauthenticated`
- [ ] Firestore Security Rules updated for any new collections
- [ ] Firestore Security Rules tested with Firebase Emulator Suite (`firebase emulators:start`)
- [ ] Admin SDK used for all privileged server-side Firestore writes
- [ ] Client SDK never used for sensitive operations (payments, audit logs, admin)
- [ ] New GCS buckets have `uniform-bucket-level-access` enabled
- [ ] New secrets stored in Secret Manager (not env vars in Cloud Run YAML)
- [ ] Cloud Armor security policy updated if new public endpoints added
- [ ] VPC connector attached if service needs private Cloud SQL access

### Authentication & Sessions

- [ ] JWT expiry is 15 minutes for access tokens
- [ ] Refresh tokens rotate on each use
- [ ] MFA flow tested end-to-end
- [ ] Account lockout triggers at 5 failed attempts
- [ ] Password reset tokens are one-time use and expire in 15 minutes

### Frontend

- [ ] Access token stored in memory only (not `localStorage`)
- [ ] `withCredentials: true` on Axios instance
- [ ] Route guards applied to all protected pages
- [ ] Plan guards applied to all gated features
- [ ] DOMPurify wrapping any user-generated HTML
- [ ] CSP headers allow only required domains

### CI/CD (Cloud Build)

- [ ] Snyk passes with no HIGH/CRITICAL vulnerabilities
- [ ] OWASP Dependency Check passes CVSS < 7.0
- [ ] Artifact Registry scan passes with no CRITICAL CVEs
- [ ] Binary Authorization attestation created for new image
- [ ] All tests green
- [ ] Docker image uses Distroless base image
- [ ] Cloud Build trigger requires pull request approval before deploying to production

### Database

- [ ] Firestore Security Rules updated for any new collections
- [ ] New PII fields encrypted with Cloud KMS before writing to Firestore
- [ ] `auditLogs` collection has `allow read, write: if false` in Security Rules
- [ ] New Firestore collections have appropriate indexes in `firestore.indexes.json`
- [ ] Firestore Security Rules deployed (`firebase deploy --only firestore:rules`)
- [ ] Indexes deployed (`firebase deploy --only firestore:indexes`)
- [ ] No sensitive data (passwords, raw keys) stored as plaintext Firestore fields

### Compliance

- [ ] New data collection documented in privacy policy
- [ ] GDPR export endpoint includes any new Firestore fields
- [ ] Deletion endpoint removes or anonymizes any new PII Firestore fields
- [ ] Audit log events added for any new billable/sensitive actions
- [ ] Cloud Audit Logs verified for new GCP resources

---

## Quarterly Security Review Schedule

| Quarter | Activity |
|---------|----------|
| Q1 | Third-party penetration test — full scope |
| Q2 | Internal security audit — all 8 layers reviewed; GCP IAM permissions review |
| Q3 | Disaster recovery drill — simulate Cloud SQL failure + breach |
| Q4 | Compliance review — GDPR, CCPA, PCI-DSS assessment + SOC 2 evidence collection |
| Ongoing | Monthly: GCS backup restore drill · Snyk daily scan · Artifact Registry scan on every deploy · Firestore Security Rules review |

---

*PlaceUp Career — Enterprise Documentation v4.0.0 · March 2026*  
*Google Cloud + Firebase Edition — Confidential — Internal Developer Use Only — Share under NDA only via secure link with expiry*
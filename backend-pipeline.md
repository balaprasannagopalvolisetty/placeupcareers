# PlaceUp Career — Backend Pipeline Documentation
**Version:** 4.0.0 · March 2026 · Google Cloud + Firebase Edition  
**Classification:** Confidential — Internal Developer Use Only

> **Infrastructure Stack:** Domain `placeupcareer.com` is managed via **Google Cloud DNS / Google Domains**. All backend services run on **Google Cloud Platform (GCP)**. The primary database is **Firebase Firestore** (NoSQL document database), chosen for its real-time capabilities, offline support, built-in security rules, and seamless Google Cloud integration.

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Job Data Pipeline](#2-job-data-pipeline)
3. [Visa Classification Engine](#3-visa-classification-engine)
4. [Email Enrichment Pipeline](#4-email-enrichment-pipeline)
5. [Async Queue System (Cloud Tasks + Pub/Sub)](#5-async-queue-system-cloud-tasks--pubsub)
6. [REST API Layer](#6-rest-api-layer)
7. [Payment Pipeline (Stripe)](#7-payment-pipeline-stripe)
8. [Alert Dispatch Pipeline](#8-alert-dispatch-pipeline)
9. [Microservices Architecture](#9-microservices-architecture)
10. [Firebase Database Pipeline](#10-firebase-database-pipeline)
11. [Frontend Integration Points](#11-frontend-integration-points)
12. [Monitoring & Scheduler](#12-monitoring--scheduler)
13. [Environment Variables](#13-environment-variables)

---

## 1. Architecture Overview

PlaceUp operates a **7-layer Google Cloud + Firebase enterprise architecture**. Every layer is independently scalable, fault-tolerant, and secured via Google Cloud IAM.

```
┌───────────────────────────────────────────────────────────────────┐
│  L1  Google Cloud Armor  (WAF + DDoS + IP Reputation + reCAPTCHA) │
├───────────────────────────────────────────────────────────────────┤
│  L2  Google Cloud HTTP(S) Load Balancing  (SSL Termination)        │
├───────────────────────────────────────────────────────────────────┤
│  L3  Google Cloud Apigee  (Auth, Rate Limiting, API Routing)       │
├───────────────────────────────────────────────────────────────────┤
│  L4  Google Cloud Run  (Microservices — stateless containers)      │
├───────────────────────────────────────────────────────────────────┤
│  L5  Cloud Tasks + Cloud Pub/Sub + Cloud Memorystore (Redis)       │
├───────────────────────────────────────────────────────────────────┤
│  L6  Firebase Firestore  (Primary NoSQL DB + Real-time)            │
├───────────────────────────────────────────────────────────────────┤
│  L7  Google Cloud Storage (GCS)  (Backups, Resume Files, Media)    │
└───────────────────────────────────────────────────────────────────┘
```

### Full Data Flow (Every 2 Hours)

| Step | Action | Google / Firebase Service |
|------|---------|--------------------------|
| 1 | Cloud Armor WAF filters incoming request | Cloud Armor |
| 2 | Load balancer distributes traffic | Cloud HTTP(S) LB |
| 3 | Apigee validates JWT + rate limits | Apigee API Gateway |
| 4 | Cloud Scheduler fires cron (every 2 hours) | Cloud Scheduler |
| 5 | Fetcher Cloud Run job runs all sources in parallel | Cloud Run Jobs |
| 6 | Classifier processes every raw job | Cloud Run (classifier) |
| 7 | Apollo.io enriches with hiring manager | Cloud Run (enricher) |
| 8 | Cloud Tasks handles async task queue | Cloud Tasks |
| 9 | Jobs written to Firebase Firestore | Firebase Admin SDK |
| 10 | Cloud Memorystore cache invalidated | Cloud Memorystore |
| 11 | React frontend fetches paginated results | REST API + Firestore SDK |
| 12 | Gmail API dispatches matching alerts | Gmail API (Workspace) |

### GCP + Firebase Project Setup

```bash
# Project: placeup-career-prod
gcloud projects create placeup-career-prod --name="PlaceUp Career"
gcloud config set project placeup-career-prod

# Enable required APIs
gcloud services enable \
  run.googleapis.com \
  firestore.googleapis.com \
  firebase.googleapis.com \
  cloudtasks.googleapis.com \
  pubsub.googleapis.com \
  redis.googleapis.com \
  secretmanager.googleapis.com \
  cloudbuild.googleapis.com \
  cloudscheduler.googleapis.com \
  dns.googleapis.com \
  compute.googleapis.com \
  cloudarmor.googleapis.com \
  apigee.googleapis.com \
  monitoring.googleapis.com \
  logging.googleapis.com \
  cloudtrace.googleapis.com \
  clouderrorreporting.googleapis.com \
  gmail.googleapis.com

# Initialize Firebase in the same GCP project
firebase init firestore --project placeup-career-prod
```

---

## 2. Job Data Pipeline

### 2.1 Data Sources

| Source | Type | Cost | Rate Limit | Records/Cycle |
|--------|------|------|------------|---------------|
| **JSearch (RapidAPI)** | Paid REST API | $15/mo (Basic 50K req) | ~10,800 req/mo needed | 42 queries × pages |
| **USAJobs API** | Free Gov API | $0 | 500 req/hour | Government jobs |
| **Idealist API** | Free Nonprofit API | $0 | Generous | NGO / nonprofit jobs |
| **USCIS H-1B Hub** | Free CSV | $0 | N/A (annual import) | 4M+ petitions FY2009+ |
| **DOL LCA Disclosure** | Free CSV | $0 | N/A (quarterly) | 4.8M+ LCA filings |

### 2.2 JSearch Query Strings (42 per cycle)

Each query = 1 API call. All 42 run in parallel via `Promise.allSettled()`.

**Technology & Engineering (6 queries)**
```
"Software Engineer OPT visa USA"
"Machine Learning Engineer H1B sponsorship"
"Data Engineer STEM OPT"
"DevOps Engineer visa sponsorship"
"Cybersecurity Analyst OPT friendly"
"QA Automation Engineer H1B sponsor"
```

**Data & Analytics (5 queries)**
```
"Data Analyst OPT friendly USA"
"Business Analyst H1B sponsor"
"Data Scientist visa sponsorship"
"Business Intelligence Developer OPT"
"Quantitative Analyst H1B visa"
```

**Finance & Accounting (5 queries)**
```
"Financial Analyst OPT visa USA"
"CPA Accountant H1B sponsorship"
"Investment Banking Analyst visa"
"Risk Analyst OPT friendly"
"Actuary H1B sponsor USA"
```

*(+ Healthcare, Mechanical, Business, Marketing, Education, Government, Design — total 42 queries)*

**Query Volume Math:**
```
42 queries/cycle × 12 cycles/day × 30 days = 15,120 API calls/month
→ JSearch Basic $15/mo plan (50K req) = sufficient with headroom
```

### 2.3 Fetcher Script (`src/fetcher/index.js`)

```javascript
import { QUERIES }             from './queries.js';
import { fetchJSearch }        from './sources/jsearch.js';
import { fetchUSAJobs }        from './sources/usajobs.js';
import { fetchIdealist }       from './sources/idealist.js';
import { classifyJob }         from '../classifier.js';
import { findHiringManager }   from '../emailFinder.js';
import { uscisLookup }         from '../uscis.js';
import { db }                  from '../db/firebase.js';   // Firebase Admin SDK
import { sendMatchAlerts }     from '../alerts.js';

async function runFetchCycle() {
  const started = Date.now();
  console.log('[FETCH] Cycle started:', new Date().toISOString());

  const [jsearchRaw, usaRaw, idealistRaw] = await Promise.all([
    Promise.allSettled(QUERIES.map(q => fetchJSearch(q))),
    fetchUSAJobs(),
    fetchIdealist(),
  ]);

  const allJobs = [
    ...jsearchRaw.flatMap(r => r.status === 'fulfilled' ? r.value : []),
    ...usaRaw,
    ...idealistRaw,
  ];
  console.log(`[FETCH] Raw jobs: ${allJobs.length}`);

  let inserted = 0, skipped = 0, discarded = 0;

  for (const job of allJobs) {
    // Check for duplicates using Firestore
    const existing = await db.collection('jobs').where('job_id', '==', job.job_id).limit(1).get();
    if (!existing.empty) { skipped++; continue; }

    const uscisMatch = await uscisLookup(job.company_name);
    const classification = classifyJob(job, uscisMatch);
    if (classification.discard) { discarded++; continue; }

    const contact = await findHiringManager(job.company_name);

    // Write to Firestore
    await db.collection('jobs').add({
      ...job,
      ...classification,
      ...contact,
      createdAt:  admin.firestore.FieldValue.serverTimestamp(),
      expiresAt:  new Date(Date.now() + 30 * 24 * 60 * 60 * 1000),
    });
    inserted++;
  }

  // Clean expired listings (older than 30 days)
  const expiredSnap = await db.collection('jobs')
    .where('expiresAt', '<', new Date())
    .get();
  const batch = db.batch();
  expiredSnap.docs.forEach(doc => batch.delete(doc.ref));
  await batch.commit();

  await sendMatchAlerts();

  console.log(
    `[FETCH] Done in ${Date.now() - started}ms. ` +
    `Inserted:${inserted} Skipped:${skipped} Discarded:${discarded} Expired:${expiredSnap.size}`
  );
}

runFetchCycle().catch(err => {
  console.error('[FETCH] CRITICAL ERROR:', err);
  process.exit(1);
});
```

### 2.4 JSearch API Request (`src/sources/jsearch.js`)

```javascript
const fetchJSearch = async (query) => {
  const res = await fetch(
    `https://jsearch.p.rapidapi.com/search?query=${encodeURIComponent(query)}&num_pages=1&date_posted=3days&country=us`,
    {
      headers: {
        'X-RapidAPI-Key':  process.env.RAPIDAPI_KEY,
        'X-RapidAPI-Host': 'jsearch.p.rapidapi.com',
      },
    }
  );
  const { data } = await res.json();
  return data;
};
```

### 2.5 Google Cloud Scheduler — Job Fetcher

```bash
# Create Cloud Scheduler job — triggers Cloud Run Job every 2 hours
gcloud scheduler jobs create http placeup-job-fetcher \
  --schedule="0 */2 * * *" \
  --uri="https://fetcher-xxxxxxxx-uc.a.run.app/run" \
  --http-method=POST \
  --oidc-service-account-email=fetcher-sa@placeup-career-prod.iam.gserviceaccount.com \
  --time-zone="America/New_York" \
  --location=us-central1
```

---

## 3. Visa Classification Engine

### 3.1 Keyword Scoring Matrix

| Visa Type | Score Weight | Trigger Keywords | Negative Override |
|-----------|-------------|-----------------|-------------------|
| OPT | +30 | `opt`, `cpt`, `f-1`, `f1 visa`, `student visa`, `international students ok` | Score → 0 if negative found |
| STEM OPT | +40 | `stem opt`, `24 month extension`, `stem extension`, `e-verify` | STEM categories only |
| H-1B | +50 | `h-1b sponsor`, `h1b`, `will sponsor`, `visa sponsorship`, `work authorization` | Must reach ≥60 total |
| Any Visa | +20 | `visa friendly`, `all work authorizations`, `no restriction` | Boosts borderline cases |
| **Negative** | **−30** | `no sponsorship`, `us citizens only`, `no visa`, `gc only`, `permanent resident only` | Sets `discard=true` if score <10 |

### 3.2 USCIS Cross-Reference Bonus

```
uscisMatch.petition_count ≥  5  → +30 bonus (employer has history)
uscisMatch.petition_count ≥ 50  → +20 additional bonus (major sponsor)
```

### 3.3 Classification Code (`src/classifier.js`)

```javascript
const STEM_CATS = ['technology', 'data', 'healthcare', 'engineering'];

export function classifyJob(job, uscisMatch) {
  let score = 0;
  const txt = `${job.title} ${job.description}`.toLowerCase();

  if (/\bopt\b|cpt|f-1|student visa|international students/i.test(txt)) score += 30;
  if (/stem opt|24.month|stem extension|e-verify/i.test(txt))            score += 40;
  if (/h-?1b|visa sponsor|will sponsor|work auth/i.test(txt))            score += 50;
  if (/visa friendly|all work auth|no restriction/i.test(txt))           score += 20;
  if (/no sponsor|citizens only|gc only|perm.?resident only/i.test(txt)) score -= 30;

  if (uscisMatch?.petition_count >= 5)  score += 30;
  if (uscisMatch?.petition_count >= 50) score += 20;

  const isStem = STEM_CATS.includes(job.category);
  return {
    visa_opt:      score >= 40,
    visa_stem_opt: score >= 50 && isStem,
    visa_h1b:      score >= 60,
    h1b_verified:  !!uscisMatch?.petition_count && uscisMatch.petition_count >= 5,
    visa_score:    Math.min(100, Math.max(0, score)),
    discard:       score < 10,
  };
}
```

### 3.4 Output Flags → Frontend Mapping

| Firestore Field | Frontend Display | Dashboard Filter Tab |
|----------------|-----------------|---------------------|
| `visa_opt = true` | Green "OPT" badge | "OPT" filter button |
| `visa_stem_opt = true` | Blue "STEM OPT" badge | "STEM OPT" filter button |
| `visa_h1b = true` | Gold "H-1B" badge | "H-1B" filter button |
| `h1b_verified = true` | Checkmark on H-1B badge | "Verified" sub-filter |
| `visa_score` | Score bar in Job Detail | ATS-style score circle |

---

## 4. Email Enrichment Pipeline

### 4.1 Apollo.io Integration (`src/emailFinder.js`)

```javascript
import { companyToDomain } from './utils/domainResolver.js';

const RECRUITER_TITLES = [
  'Technical Recruiter', 'Senior Recruiter', 'Recruiter',
  'Talent Acquisition Specialist', 'Talent Acquisition Manager',
  'Hiring Manager', 'Engineering Manager', 'HR Director',
  'People Operations', 'Head of Talent', 'University Recruiter',
];

export async function findHiringManager(companyName) {
  try {
    const domain = await companyToDomain(companyName);
    if (!domain) return null;

    const res = await fetch('https://api.apollo.io/v1/people/search', {
      method: 'POST',
      headers: {
        'x-api-key':    process.env.APOLLO_API_KEY,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        organization_domains: [domain],
        person_titles:        RECRUITER_TITLES,
        per_page:             1,
      }),
    });

    const { people } = await res.json();
    if (!people?.length || !people[0].email) return null;

    const p = people[0];
    if (p.email_status === 'invalid') return null;

    return {
      contact_name:     `${p.first_name} ${p.last_name}`,
      contact_title:    p.title,
      contact_email:    p.email,          // stored encrypted via Cloud KMS
      contact_linkedin: p.linkedin_url,
      contact_verified: p.email_status === 'verified',
      contact_source:   'apollo',
      contact_fetched:  admin.firestore.FieldValue.serverTimestamp(),
    };
  } catch {
    return null;
  }
}
```

### 4.2 Plan-Gated Access (Frontend)

```javascript
// middleware/planGuard.js
export const requirePlan = (...plans) => (req, res, next) => {
  const clientPlan = req.user.plan;
  const planRank   = { starter: 1, pro: 2, elite: 3 };
  const minRank    = Math.min(...plans.map(p => planRank[p] || 0));
  if ((planRank[clientPlan] || 0) < minRank) {
    return res.status(403).json({
      error:       'PLAN_UPGRADE_REQUIRED',
      message:     `This feature requires ${plans[0]} plan or higher`,
      upgrade_url: process.env.FRONTEND_URL + '/pricing',
    });
  }
  next();
};

router.get('/jobs/:id/contact', authenticate, requirePlan('pro', 'elite'), handler);
```

---

## 5. Async Queue System (Cloud Tasks + Pub/Sub)

### 5.1 Queue Architecture

```
Job Fetch Cycle
     │
     ├──▶  Cloud Tasks Queue: classifyQueue    → Cloud Run (classifier service)
     │
     ├──▶  Cloud Tasks Queue: emailEnrichQueue → Cloud Run (enricher — rate-limited)
     │
     └──▶  Cloud Pub/Sub Topic: job-alerts     → Cloud Run (alerts service)
```

### 5.2 Cloud Tasks Setup (`src/queue/cloudTasks.js`)

```javascript
import { CloudTasksClient } from '@google-cloud/tasks';

const client  = new CloudTasksClient();
const PROJECT = process.env.GCP_PROJECT_ID;   // placeup-career-prod
const REGION  = process.env.GCP_REGION;       // us-central1

export async function enqueueTask(queue, serviceUrl, payload) {
  const parent = client.queuePath(PROJECT, REGION, queue);

  const task = {
    httpRequest: {
      httpMethod: 'POST',
      url:        serviceUrl,
      headers:    { 'Content-Type': 'application/json' },
      body:       Buffer.from(JSON.stringify(payload)).toString('base64'),
      oidcToken:  {
        serviceAccountEmail: `tasks-sa@${PROJECT}.iam.gserviceaccount.com`,
      },
    },
  };

  const [response] = await client.createTask({ parent, task });
  return response.name;
}

// Usage: enqueue email enrichment task
await enqueueTask(
  'email-enrichment',
  `https://enricher-xxxxxxxx-uc.a.run.app/enrich`,
  { companyName: job.company_name, jobId: job.id }
);
```

### 5.3 Cloud Pub/Sub for Alert Events (`src/queue/pubsub.js`)

```javascript
import { PubSub } from '@google-cloud/pubsub';

const pubsub = new PubSub({ projectId: process.env.GCP_PROJECT_ID });

export async function publishJobAlerts(newJobIds) {
  const topic = pubsub.topic('job-alerts');
  const message = Buffer.from(JSON.stringify({ jobIds: newJobIds, ts: Date.now() }));
  await topic.publishMessage({ data: message });
  console.log(`[PUB/SUB] Published alert event for ${newJobIds.length} new jobs`);
}

export async function handleAlertMessage(req, res) {
  const message = JSON.parse(
    Buffer.from(req.body.message.data, 'base64').toString()
  );
  await sendMatchAlerts(message.jobIds);
  res.status(200).send('OK');
}
```

### 5.4 Cloud Task Queues — GCP Configuration

```bash
gcloud tasks queues create email-enrichment \
  --location=us-central1 \
  --max-concurrent-dispatches=5 \
  --max-dispatches-per-second=2 \
  --max-attempts=3 \
  --min-backoff=1s \
  --max-backoff=30s

gcloud tasks queues create classify-jobs \
  --location=us-central1 \
  --max-concurrent-dispatches=20 \
  --max-attempts=3
```

### 5.5 Retry & Failure Strategy

| Scenario | Behaviour |
|----------|-----------|
| Apollo.io timeout | Cloud Tasks retry 3× with exponential backoff (1s, 5s, 30s) |
| Firestore write failure | Cloud Tasks retry 5× — Cloud Monitoring alert if all fail |
| Gmail API bounce | Log to `auditLogs` Firestore collection, mark alert as failed |
| Queue backlog >10K tasks | Cloud Monitoring alert → on-call via PagerDuty |

---

## 6. REST API Layer

### 6.1 Security Middleware Stack (`app.js`)

```javascript
import express   from 'express';
import helmet    from 'helmet';
import cors      from 'cors';
import rateLimit from 'express-rate-limit';

const app = express();

app.use(helmet({
  contentSecurityPolicy: {
    directives: {
      defaultSrc: ["'self'"],
      scriptSrc:  ["'self'", 'https://js.stripe.com'],
      frameSrc:   ['https://js.stripe.com'],
      connectSrc: ["'self'", 'https://api.stripe.com'],
    },
  },
  hsts: { maxAge: 31_536_000, includeSubDomains: true, preload: true },
}));

app.use(cors({
  origin:      process.env.FRONTEND_URL,
  credentials: true,
  methods:     ['GET', 'POST', 'PUT', 'DELETE'],
}));

// Global rate limiter — 100 req/15min per IP
app.use(rateLimit({ windowMs: 15 * 60 * 1000, max: 100, standardHeaders: true }));

// Auth endpoints — strict limit — 5 attempts/15min
const authLimiter = rateLimit({ windowMs: 15 * 60 * 1000, max: 5 });
app.use('/api/auth', authLimiter);
```

### 6.2 All API Endpoints

**Authentication**

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| POST | `/api/auth/register` | Public | Register client — hash password, send verify email |
| POST | `/api/auth/login` | Public | Returns JWT (15m) + refresh token (7d) |
| POST | `/api/auth/refresh` | Refresh token | Issue new access token |
| POST | `/api/auth/logout` | JWT | Invalidate refresh token |
| POST | `/api/auth/mfa/setup` | JWT | Generate TOTP QR code for 2FA |
| POST | `/api/auth/mfa/verify` | JWT | Verify TOTP code |
| POST | `/api/auth/forgot` | Public | Send password reset email |
| POST | `/api/auth/reset` | Token | Reset password with secure token |

**Jobs**

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | `/api/jobs` | JWT | All jobs with filters (category, visa, date, location) |
| GET | `/api/jobs/opt` | JWT | OPT-eligible jobs only |
| GET | `/api/jobs/stem` | JWT | STEM OPT jobs only |
| GET | `/api/jobs/h1b` | JWT | H-1B verified sponsor jobs |
| GET | `/api/jobs/:id` | JWT | Single job detail (full description + ATS data) |
| GET | `/api/categories` | JWT | All 10 categories + job counts |
| GET | `/api/stats` | JWT | System stats + last refresh timestamp |

**Payments**

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| POST | `/api/payments/create-session` | JWT | Create Stripe checkout session |
| POST | `/api/payments/webhook` | Stripe sig | Handle Stripe webhook events |
| GET | `/api/payments/portal` | JWT | Stripe customer portal redirect URL |

**Clients**

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | `/api/clients/me` | JWT | Own profile |
| PUT | `/api/clients/me` | JWT | Update profile |
| GET | `/api/clients/me/export` | JWT | GDPR data export |
| DELETE | `/api/clients/me` | JWT | GDPR account deletion (anonymize) |

**Alerts**

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | `/api/alerts/prefs` | JWT | Get alert preferences |
| PUT | `/api/alerts/prefs` | JWT | Update alert preferences |

**Admin**

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | `/api/admin/stats` | Admin JWT | Dashboard metrics |
| GET | `/api/admin/clients` | Admin JWT | All clients list |
| GET | `/api/admin/logs` | Admin JWT | Audit log viewer |
| GET | `/api/health` | Public | System health + uptime |

### 6.3 Frontend API Integration (`src/lib/api.ts`)

```typescript
import axios from 'axios';

const api = axios.create({
  baseURL:         import.meta.env.VITE_API_URL,
  withCredentials: true,
});

api.interceptors.request.use(config => {
  const token = getAccessTokenFromMemory();
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

api.interceptors.response.use(
  res => res,
  async err => {
    if (err.response?.status === 401 && !err.config._retry) {
      err.config._retry = true;
      const { data } = await axios.post('/api/auth/refresh', {}, { withCredentials: true });
      setAccessTokenInMemory(data.accessToken);
      err.config.headers.Authorization = `Bearer ${data.accessToken}`;
      return api.request(err.config);
    }
    return Promise.reject(err);
  }
);

export default api;
```

---

## 7. Payment Pipeline (Stripe)

### 7.1 Pricing Plans

| Plan | Price | Stripe Price ID Env | Features |
|------|-------|---------------------|----------|
| Starter | $99/month | `STRIPE_STARTER_PRICE_ID` | ATS resume, LinkedIn optimization, 20 apps/week, 1 mock interview |
| Pro | $150/month | `STRIPE_PRO_PRICE_ID` | All Starter + 100+ cold emails, 50–100 apps/week, hiring manager contacts |
| Elite | $249/month | `STRIPE_ELITE_PRICE_ID` | All Pro + referral support, dedicated manager, priority queue, weekly reports |

### 7.2 Checkout Session Creation

```javascript
import Stripe from 'stripe';
const stripe = new Stripe(process.env.STRIPE_SECRET_KEY);

const session = await stripe.checkout.sessions.create({
  mode:                 'subscription',
  payment_method_types: ['card'],
  line_items: [{ price: process.env.STRIPE_PRO_PRICE_ID, quantity: 1 }],
  success_url: `${process.env.FRONTEND_URL}/dashboard?session_id={CHECKOUT_SESSION_ID}`,
  cancel_url:  `${process.env.FRONTEND_URL}/pricing`,
  metadata:    { userId: user.id, plan: 'pro' },
});
res.json({ url: session.url });
```

### 7.3 Stripe Webhook Handler — writes to Firestore

```javascript
import Stripe from 'stripe';
import { db } from '../db/firebase.js';

const stripe = new Stripe(process.env.STRIPE_SECRET_KEY);

export const stripeWebhook = async (req, res) => {
  const sig = req.headers['stripe-signature'];
  let event;

  try {
    event = stripe.webhooks.constructEvent(
      req.rawBody, sig, process.env.STRIPE_WEBHOOK_SECRET
    );
  } catch (err) {
    return res.status(400).send(`Webhook Error: ${err.message}`);
  }

  switch (event.type) {
    case 'checkout.session.completed': {
      const session = event.data.object;
      // Update Firestore client document with new plan
      await db.collection('clients').doc(session.metadata.userId).update({
        plan:              session.metadata.plan,
        sub_status:        'active',
        stripe_customer:   session.customer,
        stripe_sub_id:     session.subscription,
        plan_activated_at: admin.firestore.FieldValue.serverTimestamp(),
      });
      break;
    }
    case 'customer.subscription.updated': {
      const sub = event.data.object;
      const snap = await db.collection('clients')
        .where('stripe_sub_id', '==', sub.id).limit(1).get();
      if (!snap.empty) {
        await snap.docs[0].ref.update({ sub_status: sub.status });
      }
      break;
    }
    case 'customer.subscription.deleted': {
      const sub = event.data.object;
      const snap = await db.collection('clients')
        .where('stripe_sub_id', '==', sub.id).limit(1).get();
      if (!snap.empty) {
        await snap.docs[0].ref.update({ plan: 'starter', sub_status: 'cancelled' });
      }
      break;
    }
    case 'invoice.payment_failed':
      await handlePaymentFailure(event.data.object); break;
    case 'invoice.payment_succeeded':
      await logPayment(event.data.object);           break;
  }

  res.json({ received: true });
};
```

---

## 8. Alert Dispatch Pipeline

### 8.1 Alert Flow (Google Workspace Gmail API)

```
New jobs inserted into Firestore
        │
        ▼
Cloud Pub/Sub publishes to job-alerts topic
        │
        ▼
Alerts Cloud Run service receives push subscription
        │
        ▼
Query /alertPrefs where is_active == true
        │
        ▼
Match new job fields against each client's preferences
        │
        ▼
Gmail API sends DKIM-signed email from jobs@placeupcareer.com
```

### 8.2 Gmail API Alert (`src/alerts/gmail.js`)

```javascript
import { google } from 'googleapis';

const auth = new google.auth.GoogleAuth({
  credentials: JSON.parse(process.env.GOOGLE_SERVICE_ACCOUNT_JSON),
  scopes: ['https://www.googleapis.com/auth/gmail.send'],
});

const gmail = google.gmail({ version: 'v1', auth });

export async function sendAlertEmail({ to, subject, html }) {
  const authClient = await auth.getClient();
  authClient.subject = 'jobs@placeupcareer.com';

  const message = [
    `From: PlaceUp Career <jobs@placeupcareer.com>`,
    `To: ${to}`,
    `Subject: ${subject}`,
    `MIME-Version: 1.0`,
    `Content-Type: text/html; charset=UTF-8`,
    ``,
    html,
  ].join('\n');

  const encoded = Buffer.from(message)
    .toString('base64')
    .replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');

  await gmail.users.messages.send({
    userId: 'me',
    requestBody: { raw: encoded },
    auth: authClient,
  });
}
```

### 8.3 Alert Matching Logic

A client receives an alert when **all** preferences match a newly inserted Firestore job document:

- `alertPrefs.categories` ∩ `job.category` is non-empty
- `alertPrefs.visa_types` ∩ job visa flags is non-empty
- `alertPrefs.locations` ∩ `job.location` matches (or no location filter set)
- `job.salary_min >= alertPrefs.salary_min` (if set)
- `alertPrefs.is_active == true`

---

## 9. Microservices Architecture

### 9.1 Service Deployment (Google Cloud Run)

| Service | Responsibility | Scaling |
|---------|---------------|---------| 
| API Gateway | Main REST API | Auto 0→100 instances |
| Job Fetcher | JSearch/USAJobs/Idealist cycle | Cloud Run Job (scheduled) |
| Classifier | Visa classification engine | Auto horizontal |
| Email Enricher | Apollo.io contact lookup | Rate-limited via Cloud Tasks |
| Alert Service | Match alerts, Gmail API dispatch | Pub/Sub push |
| Payment Service | Stripe integration | Auto |
| Admin Service | Dashboard, analytics | Low traffic |
| Auth Service | JWT, MFA, password, sessions | Auto horizontal |

### 9.2 Deploy a Service to Cloud Run

```bash
# Build and push to Artifact Registry
gcloud builds submit \
  --tag us-central1-docker.pkg.dev/placeup-career-prod/placeup/api:$COMMIT_SHA

# Deploy to Cloud Run with Firestore access
gcloud run deploy placeup-api \
  --image us-central1-docker.pkg.dev/placeup-career-prod/placeup/api:$COMMIT_SHA \
  --region us-central1 \
  --platform managed \
  --no-allow-unauthenticated \
  --service-account api-sa@placeup-career-prod.iam.gserviceaccount.com \
  --set-secrets="JWT_PRIVATE_KEY=JWT_PRIVATE_KEY:latest,STRIPE_SECRET_KEY=STRIPE_SECRET_KEY:latest" \
  --set-env-vars="GCP_PROJECT_ID=placeup-career-prod" \
  --min-instances=1 \
  --max-instances=100
```

### 9.3 Deployment Stack

| Component | MVP | Growth | Enterprise |
|-----------|-----|--------|------------|
| Compute | Cloud Run (serverless) | Cloud Run (min instances) | Cloud Run + GKE Autopilot |
| Scheduler | Cloud Scheduler | Cloud Scheduler | Cloud Scheduler |
| Container Registry | Artifact Registry | Artifact Registry | Artifact Registry |
| Database | Firebase Firestore (Spark/free) | Firebase Firestore (Blaze) | Firestore + BigQuery export |
| Cache | Cloud Memorystore 1GB | Cloud Memorystore 5GB | Cloud Memorystore HA |
| CI/CD | Cloud Build | Cloud Build | Cloud Build + Artifact Registry |

---

## 10. Firebase Database Pipeline

### 10.1 Why Firebase Firestore

| Feature | Benefit |
|---------|---------|
| NoSQL document model | Flexible schema — jobs have varying fields by category |
| Real-time listeners | Dashboard updates live without polling |
| Offline support | Frontend works offline with Firestore SDK cache |
| Security Rules | Declarative, co-located security policies |
| Serverless | No Cloud SQL instance to manage or patch |
| Google Cloud native | Same IAM, billing, and project as all other services |
| Firebase Admin SDK | Server-side access from Cloud Run with service account |

### 10.2 Firestore Collection Structure

```
firestore/
├── clients/                         # User accounts
│   └── {userId}/
│       ├── email: string
│       ├── password_hash: string    # Argon2id (never in client SDK queries)
│       ├── plan: 'starter'|'pro'|'elite'
│       ├── sub_status: string
│       ├── stripe_customer: string
│       ├── stripe_sub_id: string
│       ├── mfa_secret: string       # Encrypted via Cloud KMS
│       ├── mfa_enabled: boolean
│       ├── createdAt: timestamp
│       └── resumes/                 # Subcollection
│           └── {resumeId}/
│               ├── name: string
│               ├── ats_score: number
│               ├── gcs_url: string  # Cloud Storage URL
│               └── uploadedAt: timestamp
│
├── jobs/                            # Job listings (written by fetcher)
│   └── {jobId}/
│       ├── job_id: string           # External source ID (unique)
│       ├── title: string
│       ├── company: string
│       ├── location: string
│       ├── salary_min: number
│       ├── salary_max: number
│       ├── description: string
│       ├── category: string
│       ├── visa_opt: boolean
│       ├── visa_stem_opt: boolean
│       ├── visa_h1b: boolean
│       ├── h1b_verified: boolean
│       ├── visa_score: number
│       ├── contact_email: string    # Encrypted (Cloud KMS), Pro/Elite only
│       ├── contact_name: string
│       ├── contact_title: string
│       ├── contact_linkedin: string
│       ├── source_url: string
│       ├── createdAt: timestamp
│       └── expiresAt: timestamp
│
├── h1bSponsors/                     # USCIS H-1B data (imported quarterly)
│   └── {sponsorId}/
│       ├── employer_name: string
│       ├── petition_count: number
│       ├── fiscal_year: string
│       └── approval_rate: number
│
├── payments/                        # Stripe payment records
│   └── {paymentId}/
│       ├── client_id: string
│       ├── stripe_payment_id: string
│       ├── amount: number
│       ├── plan: string
│       ├── status: string
│       └── createdAt: timestamp
│
├── auditLogs/                       # Immutable audit trail
│   └── {logId}/
│       ├── client_id: string
│       ├── event: string
│       ├── ip_address: string
│       ├── user_agent: string
│       ├── metadata: map
│       └── createdAt: timestamp
│
└── alertPrefs/                      # Per-user alert settings
    └── {userId}/
        ├── categories: string[]
        ├── visa_types: string[]
        ├── locations: string[]
        ├── salary_min: number
        └── is_active: boolean
```

### 10.3 Firebase Admin SDK Setup (`src/db/firebase.js`)

```javascript
import admin from 'firebase-admin';

// Cloud Run — uses Application Default Credentials (service account auto-injected)
// Local dev — set GOOGLE_APPLICATION_CREDENTIALS env var
if (!admin.apps.length) {
  admin.initializeApp({
    credential:  admin.credential.applicationDefault(),
    projectId:   process.env.GCP_PROJECT_ID,
  });
}

export const db     = admin.firestore();
export const auth   = admin.auth();         // Firebase Auth (optional)
export { admin };
```

### 10.4 Firestore Composite Indexes (`firestore.indexes.json`)

```json
{
  "indexes": [
    {
      "collectionGroup": "jobs",
      "queryScope": "COLLECTION",
      "fields": [
        { "fieldPath": "visa_opt",    "order": "ASCENDING" },
        { "fieldPath": "createdAt",   "order": "DESCENDING" }
      ]
    },
    {
      "collectionGroup": "jobs",
      "queryScope": "COLLECTION",
      "fields": [
        { "fieldPath": "visa_h1b",    "order": "ASCENDING" },
        { "fieldPath": "createdAt",   "order": "DESCENDING" }
      ]
    },
    {
      "collectionGroup": "jobs",
      "queryScope": "COLLECTION",
      "fields": [
        { "fieldPath": "category",    "order": "ASCENDING" },
        { "fieldPath": "visa_opt",    "order": "ASCENDING" },
        { "fieldPath": "createdAt",   "order": "DESCENDING" }
      ]
    },
    {
      "collectionGroup": "jobs",
      "queryScope": "COLLECTION",
      "fields": [
        { "fieldPath": "visa_h1b",    "order": "ASCENDING" },
        { "fieldPath": "category",    "order": "ASCENDING" },
        { "fieldPath": "createdAt",   "order": "DESCENDING" }
      ]
    },
    {
      "collectionGroup": "auditLogs",
      "queryScope": "COLLECTION",
      "fields": [
        { "fieldPath": "client_id",   "order": "ASCENDING" },
        { "fieldPath": "createdAt",   "order": "DESCENDING" }
      ]
    }
  ],
  "fieldOverrides": []
}
```

### 10.5 Common Firestore Queries (Server-Side, Admin SDK)

```javascript
// Jobs: filter by visa type + date, paginated
const jobsQuery = await db.collection('jobs')
  .where('visa_opt', '==', true)
  .where('expiresAt', '>', new Date())
  .orderBy('expiresAt')
  .orderBy('createdAt', 'desc')
  .limit(20)
  .startAfter(lastDoc)  // cursor-based pagination
  .get();

// Jobs: full-text search — use Firestore with Algolia (or Cloud Search)
// Firestore does not support native full-text search;
// index job title/description in Algolia on write for search functionality.

// Clients: get by email (registration / login)
const clientSnap = await db.collection('clients')
  .where('email', '==', email)
  .limit(1)
  .get();

// Alert prefs: find active alerts matching a job category
const alertsSnap = await db.collection('alertPrefs')
  .where('is_active', '==', true)
  .where('categories', 'array-contains', job.category)
  .get();
```

### 10.6 Cloud Memorystore (Redis) Cache Strategy

Firestore reads are fast but charged per read operation. Redis caches frequently-accessed paginated results:

```bash
# Create Memorystore Redis instance
gcloud redis instances create placeup-cache \
  --size=1 \
  --region=us-central1 \
  --redis-version=redis_7_0 \
  --tier=STANDARD_HA
```

| Cached Key | TTL | Invalidated When |
|------------|-----|------------------|
| `jobs:opt:page:{n}` | 2 hours | After each fetch cycle |
| `jobs:h1b:page:{n}` | 2 hours | After each fetch cycle |
| `categories:counts` | 2 hours | After each fetch cycle |
| `stats:system` | 10 minutes | Every stats request if expired |
| `session:{userId}` | 15 minutes | On logout or password change |

### 10.7 Firestore Security Rules (Client-Side Access)

The React frontend uses the **Firestore client SDK** only for real-time listeners. Security Rules enforce access control at the Firestore level without requiring a backend API call:

```javascript
// firestore.rules
rules_version = '2';
service cloud.firestore {
  match /databases/{database}/documents {

    // Jobs — readable by any authenticated user
    match /jobs/{jobId} {
      allow read: if request.auth != null;
      allow write: if false; // server-side only (Admin SDK bypasses rules)
    }

    // Clients — only own document
    match /clients/{userId} {
      allow read, update: if request.auth != null && request.auth.uid == userId;
      allow create: if false; // registration via server API only
      allow delete: if false;
    }

    // Alert prefs — only own document
    match /alertPrefs/{userId} {
      allow read, write: if request.auth != null && request.auth.uid == userId;
    }

    // Payments — read-only, own records
    match /payments/{paymentId} {
      allow read: if request.auth != null &&
                     resource.data.client_id == request.auth.uid;
      allow write: if false; // Stripe webhook via server only
    }

    // Audit logs — no client access
    match /auditLogs/{logId} {
      allow read, write: if false; // server-side Admin SDK only
    }

    // H1B Sponsors — readable by authenticated users
    match /h1bSponsors/{sponsorId} {
      allow read: if request.auth != null;
      allow write: if false; // import job only
    }
  }
}
```

### 10.8 Full-Text Search with Algolia (Firestore Extension)

Since Firestore lacks native full-text search, use the **Firebase Extension: Search with Algolia**:

```bash
# Install the Algolia Firebase Extension
firebase ext:install algolia/firestore-algolia-search \
  --project placeup-career-prod

# Extension config:
# Collection: jobs
# Fields to index: title, company, location, description, category
# Algolia App ID: your_algolia_app_id
# Algolia API Key: stored in Secret Manager
```

---

## 11. Frontend Integration Points

### 11.1 Firestore Real-Time Listeners (Frontend SDK)

For live dashboard updates without polling:

```typescript
// src/hooks/useJobs.ts — Firestore real-time listener
import { collection, query, where, orderBy, limit, onSnapshot } from 'firebase/firestore';
import { db } from '../lib/firebase';  // client SDK (not admin)
import { useEffect, useState } from 'react';

export function useJobsRealtime(filters: JobFilters) {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let q = query(
      collection(db, 'jobs'),
      where('expiresAt', '>', new Date()),
      orderBy('expiresAt'),
      orderBy('createdAt', 'desc'),
      limit(50)
    );

    if (filters.visaType === 'opt')  q = query(q, where('visa_opt',  '==', true));
    if (filters.visaType === 'h1b')  q = query(q, where('visa_h1b',  '==', true));
    if (filters.category)             q = query(q, where('category', '==', filters.category));

    const unsub = onSnapshot(q, (snap) => {
      setJobs(snap.docs.map(d => ({ id: d.id, ...d.data() } as Job)));
      setLoading(false);
    });

    return unsub; // cleanup
  }, [filters]);

  return { jobs, loading };
}
```

### 11.2 Firebase Client SDK Setup (`src/lib/firebase.ts`)

```typescript
// src/lib/firebase.ts — CLIENT SDK (browser-safe)
import { initializeApp, getApps } from 'firebase/app';
import { getFirestore }           from 'firebase/firestore';
import { getAuth }                from 'firebase/auth';

const firebaseConfig = {
  apiKey:            import.meta.env.VITE_FIREBASE_API_KEY,
  authDomain:        import.meta.env.VITE_FIREBASE_AUTH_DOMAIN,
  projectId:         import.meta.env.VITE_FIREBASE_PROJECT_ID,
  storageBucket:     import.meta.env.VITE_FIREBASE_STORAGE_BUCKET,
  messagingSenderId: import.meta.env.VITE_FIREBASE_MESSAGING_SENDER_ID,
  appId:             import.meta.env.VITE_FIREBASE_APP_ID,
};

const app = getApps().length ? getApps()[0] : initializeApp(firebaseConfig);
export const db   = getFirestore(app);
export const auth = getAuth(app);
```

### 11.3 Dashboard ↔ Backend Data Map

| Dashboard Component | Data Source | Data Used |
|--------------------|-------------|-----------|
| Overview stats cards | REST `GET /api/stats` | Total jobs, last refresh time, OPT count |
| Jobs page list | Firestore real-time listener | Filtered, paginated job docs |
| Job Detail ATS score | Firestore `getDoc('jobs/{id}')` | `visa_score`, keyword arrays |
| Visa Tracker badges | Firestore query with visa filters | `visa_opt`, `visa_stem_opt`, `visa_h1b` |
| Analytics charts | REST `GET /api/admin/stats` | Time-series job counts by category |
| Alert settings | Firestore `alertPrefs/{userId}` | User preference document |
| Billing page | REST `GET /api/payments/portal` | Stripe customer portal URL |
| User Profile | Firestore `clients/{userId}` | Profile fields, plan, sub_status |

---

## 12. Monitoring & Scheduler

### 12.1 Google Cloud Monitoring — Alert Thresholds

| Metric | Warning | Critical | Automated Response |
|--------|---------|----------|--------------------|
| API response time | >500ms | >2000ms | Cloud Run auto-scales |
| Firestore read ops | >80% quota | >95% quota | Alert + review indexing |
| Error rate | >1% | >5% | PagerDuty page on-call |
| Failed auth attempts | >20/min | >50/min | Cloud Armor auto-block IP |
| Job fetch failure | 1 cycle | 3 consecutive | PagerDuty alert |
| Cloud Memorystore memory | >75% | >90% | Alert + review TTLs |
| Payment webhook fail | 1 failure | 3 failures | Alert + manual retry |

### 12.2 Monitoring Stack

| Tool | GCP Service | Purpose |
|------|-------------|---------|
| Metrics & Dashboards | Cloud Monitoring | CPU, Firestore reads/writes, latency, error rates |
| Centralized Logs | Cloud Logging | All service logs — 90-day retention |
| Distributed Tracing | Cloud Trace | Request latency across microservices |
| Error Tracking | Cloud Error Reporting | Automatic error grouping + alerts |
| Uptime Checks | Cloud Monitoring Uptime | 1-minute checks — PagerDuty on down |
| Threat Detection | Security Command Center (SCC) | ML-based anomaly + threat detection |
| On-call Escalation | PagerDuty | P0/P1 escalation |

### 12.3 Cloud Build CI/CD

```yaml
# cloudbuild.yaml
steps:
  - name: 'node:20-alpine'
    id: snyk-scan
    entrypoint: 'sh'
    args: ['-c', 'npm install -g snyk && snyk test --severity-threshold=high']
    secretEnv: ['SNYK_TOKEN']

  - name: 'node:20-alpine'
    id: run-tests
    waitFor: ['snyk-scan']
    entrypoint: 'sh'
    args: ['-c', 'npm ci && npm test']

  - name: 'gcr.io/cloud-builders/docker'
    id: build-image
    waitFor: ['run-tests']
    args: ['build', '-t', 'us-central1-docker.pkg.dev/$PROJECT_ID/placeup/api:$COMMIT_SHA', '.']

  - name: 'gcr.io/cloud-builders/docker'
    id: push-image
    waitFor: ['build-image']
    args: ['push', 'us-central1-docker.pkg.dev/$PROJECT_ID/placeup/api:$COMMIT_SHA']

  - name: 'gcr.io/google.com/cloudsdktool/cloud-sdk'
    id: deploy
    waitFor: ['push-image']
    entrypoint: 'gcloud'
    args: ['run', 'deploy', 'placeup-api',
           '--image=us-central1-docker.pkg.dev/$PROJECT_ID/placeup/api:$COMMIT_SHA',
           '--region=us-central1', '--platform=managed']

availableSecrets:
  secretManager:
    - versionName: projects/$PROJECT_ID/secrets/SNYK_TOKEN/versions/latest
      env: 'SNYK_TOKEN'
options:
  logging: CLOUD_LOGGING_ONLY
```

---

## 13. Environment Variables

> All production secrets stored in **Google Secret Manager** and injected at Cloud Run deploy time.

```shell
# ── Job Data APIs ─────────────────────────────────────
RAPIDAPI_KEY=your_rapidapi_key_here
USAJOBS_API_KEY=your_usajobs_key_here
IDEALIST_API_KEY=your_idealist_key_here

# ── Email Finder ──────────────────────────────────────
APOLLO_API_KEY=your_apollo_api_key_here

# ── Google Cloud ──────────────────────────────────────
GCP_PROJECT_ID=placeup-career-prod
GCP_REGION=us-central1
GOOGLE_SERVICE_ACCOUNT_JSON={"type":"service_account",...}

# ── Firebase (Server-side Admin SDK — Cloud Run) ──────
# Uses Application Default Credentials automatically.
# No explicit key needed when GOOGLE_APPLICATION_CREDENTIALS is set.
FIREBASE_PROJECT_ID=placeup-career-prod

# ── Firebase (Client-side SDK — VITE_ prefix = browser-safe) ──
VITE_FIREBASE_API_KEY=AIzaXXXXXXXXXXXX
VITE_FIREBASE_AUTH_DOMAIN=placeup-career-prod.firebaseapp.com
VITE_FIREBASE_PROJECT_ID=placeup-career-prod
VITE_FIREBASE_STORAGE_BUCKET=placeup-career-prod.appspot.com
VITE_FIREBASE_MESSAGING_SENDER_ID=000000000000
VITE_FIREBASE_APP_ID=1:000000000000:web:xxxxxxxxxxxxxxxx

# ── Cloud Memorystore (Redis) ─────────────────────────
REDIS_HOST=10.x.x.x      # Private IP from Cloud Memorystore
REDIS_PORT=6379

# ── Stripe Payments ───────────────────────────────────
STRIPE_SECRET_KEY=sk_live_xxxxxxxxxxxxx
STRIPE_PUBLISHABLE_KEY=pk_live_xxxxxxxxxxxxx
STRIPE_WEBHOOK_SECRET=whsec_xxxxxxxxxxxxx
STRIPE_STARTER_PRICE_ID=price_xxxxxxxxxxxxx
STRIPE_PRO_PRICE_ID=price_xxxxxxxxxxxxx
STRIPE_ELITE_PRICE_ID=price_xxxxxxxxxxxxx

# ── Authentication ────────────────────────────────────
JWT_PRIVATE_KEY=-----BEGIN RSA PRIVATE KEY-----\n...
JWT_PUBLIC_KEY=-----BEGIN PUBLIC KEY-----\n...
JWT_REFRESH_SECRET=your_random_64_char_string

# ── Email (Google Workspace / Gmail API) ──────────────
FROM_EMAIL=jobs@placeupcareer.com
GOOGLE_WORKSPACE_DOMAIN=placeupcareer.com

# ── Algolia (full-text search for jobs) ───────────────
ALGOLIA_APP_ID=your_algolia_app_id
ALGOLIA_ADMIN_KEY=your_algolia_admin_key
VITE_ALGOLIA_APP_ID=your_algolia_app_id
VITE_ALGOLIA_SEARCH_KEY=your_algolia_search_only_key  # safe to expose

# ── App Config ────────────────────────────────────────
NODE_ENV=production
PORT=8080
FRONTEND_URL=https://app.placeupcareer.com
API_URL=https://api.placeupcareer.com
FETCH_INTERVAL_HOURS=2
JOB_EXPIRY_DAYS=30

# ── Security ──────────────────────────────────────────
ENCRYPTION_KEY=your_32_byte_hex_key_here   # Cloud KMS managed

# ── Google Cloud Monitoring ───────────────────────────
GOOGLE_CLOUD_PROJECT=placeup-career-prod
```

---

## Cost Reference (Google Cloud + Firebase)

| Stage | Monthly Cost | Supported Clients |
|-------|-------------|-------------------|
| MVP / Bootstrap | ~$20/mo | 1–10 clients (Firestore Spark free tier + Cloud Run free tier) |
| Growth Stage | ~$150/mo | 10–500 clients (Firestore Blaze + Memorystore + Cloud Build) |
| Enterprise Scale | ~$600/mo | 500–10,000+ clients (Firestore + GKE + multi-region + Algolia) |

**Firestore free tier (Spark plan):**
- 1 GiB storage
- 50,000 reads/day, 20,000 writes/day, 20,000 deletes/day
- 10 GiB network egress/month
- Sufficient for MVP with <10 clients

---

## Google Cloud DNS Configuration

```bash
# Create a managed DNS zone (domain from Google Domains/Cloud DNS)
gcloud dns managed-zones create placeup-zone \
  --dns-name="placeupcareer.com." \
  --description="PlaceUp Career DNS zone"

# Add A record → Cloud Run Load Balancer
gcloud dns record-sets create api.placeupcareer.com. \
  --zone=placeup-zone --type=A --ttl=300 --rrdatas=LOAD_BALANCER_IP

# Firebase Hosting custom domain (optional — for frontend hosting)
firebase hosting:channel:deploy production --project placeup-career-prod
```

---

*PlaceUp Career — Enterprise Documentation v4.0.0 · March 2026*  
*Google Cloud + Firebase Edition — Confidential — Internal Developer Use Only*
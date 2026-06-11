# PlaceUp Scaling Playbook — handling 300,000 (3L) concurrent users

Last updated: 2026-06-10

## How to think about the number

300k *concurrent users* is not 300k concurrent requests. With a normal
think-time pattern (a user clicks every 10–30 s), 300k concurrent users
produce roughly **10,000–30,000 requests/second** at peak. That is the load
to engineer for. The good news: the stack (Cloud Run + Cloud SQL + Firestore
+ nginx static frontend) scales to that level — but only after the quota and
database steps below. Today the project is capped at **20 vCPU per region**,
which supports roughly 2–4k req/s, not 10–30k.

## Step 0 — what is already done in the codebase

- API deploy script takes `-ApiMinInstances` / `-ApiMaxInstances` flags, so
  scaling up is a deploy flag, not a code edit.
- SQLAlchemy pool is bounded per instance (`DB_POOL_SIZE`=5,
  `DB_MAX_OVERFLOW`=10 → max 15 connections/instance) so instances can't
  stampede Cloud SQL. Sizing rule: `max-instances × 15 < Cloud SQL
  max_connections`.
- Frontend is a static nginx container (trivially scalable) and all API
  reads are rate-limited per IP with cheap in-process counters.
- min-instances=3 keeps cold starts away from the login path.

## Step 1 — raise quotas (do this first; takes 1–2 days)

Request in Google Cloud Console → IAM & Admin → Quotas, for `us-east1`,
project `steel-shine-492401-u6`:

| Quota | Current | Request |
|---|---|---|
| Cloud Run CPU allocation (CpuAllocPerProjectRegion) | 20 vCPU | 600–800 vCPU |
| Cloud Run memory allocation | 40 GiB | 800 GiB |
| Cloud Run instances | (tied to CPU) | 300+ |

Justification text that works: "Production job-search platform expecting
300k concurrent users at launch peaks; ~15k req/s; Cloud Run service at
2 vCPU/instance, concurrency 40."

## Step 2 — scale the API service (after quota approval)

```powershell
cd D:\Development_Projects\PlaceUp\backend
.\deploy\deploy_backend.ps1 `
  -ProjectId steel-shine-492401-u6 -Region us-east1 `
  -DbInstance placeup-backend `
  -UserFirestoreProjectId placeup-firebase-641222668282 `
  -ApiMinInstances 10 -ApiMaxInstances 300
```

300 instances × 40 concurrency = 12,000 in-flight requests. Raise
`WEB_CONCURRENCY` (uvicorn workers) only if CPU sits idle while requests
queue.

## Step 3 — database (the real bottleneck)

1. **Upgrade Cloud SQL tier** to ≥ 8 vCPU / 32 GB with HA
   (`db-custom-8-32768`), and set `max_connections=5000`:
   ```
   gcloud sql instances patch placeup-backend --cpu 8 --memory 32GiB \
     --database-flags max_connections=5000 --availability-type REGIONAL
   ```
2. **Add read replicas** for the jobs feed (read-heavy):
   ```
   gcloud sql instances create placeup-backend-replica-1 \
     --master-instance-name placeup-backend --region us-east1
   ```
   Point a `DATABASE_URL_READ` at the replica later if writes contend.
3. **Connection math:** 300 instances × 15 pool max = 4,500 < 5,000. If you
   go above 300 instances, add PgBouncer or lower `DB_POOL_SIZE`.
4. **Indexes that matter at scale** (run once in Cloud SQL):
   ```sql
   CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_master_jobs_seen_id
     ON master_jobs (last_seen_at DESC, id);
   CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_master_jobs_status_seen
     ON master_jobs (status, last_seen_at DESC);
   CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_master_jobs_title_trgm
     ON master_jobs USING gin (title gin_trgm_ops);
   -- requires: CREATE EXTENSION IF NOT EXISTS pg_trgm;
   ```

## Step 4 — put a CDN + WAF in front (one-time setup)

Create a **global external HTTPS Load Balancer** with two backends:
frontend Cloud Run (placeup-frontend) and API Cloud Run (placeup-api),
then:

- Enable **Cloud CDN** on the frontend backend — static assets
  (`/assets/*`, images, fonts) get served from Google edge, cutting ~80% of
  frontend traffic before it reaches Cloud Run.
- Attach **Cloud Armor** to both backends: managed DDoS protection,
  rate-based ban rules (e.g. >300 req/min/IP on `/api/auth/*`), and OWASP
  preconfigured rules. This is what actually keeps the site up under abuse.
- Point `placeupcareer.com` DNS at the LB IP instead of the Cloud Run
  domain mapping.

## Step 5 — move the rate limiter to Redis (only when >1 instance matters)

The in-process limiter divides its budget by instance count (300 instances
→ each IP effectively gets 300× the limit). Add Memorystore Redis
(1 GB basic tier) and set `RATE_LIMIT_BACKEND=redis` (the middleware was
designed for this swap — see `app/middleware/security.py`).

## Step 6 — load test BEFORE launch day

```bash
# 1k → 15k RPS ramp against the jobs feed + auth, from Cloud Shell:
pip install locust
locust -f loadtest.py --headless -u 30000 -r 500 --host https://placeupcareer.com
```
Watch: Cloud Run instance count, p95 latency, Cloud SQL CPU + connections,
429 rates. Fix whatever saturates first; repeat.

## Quick reference — run the scraper manually

```powershell
gcloud run jobs execute placeup-job-scraper-6h --region us-east1 --project steel-shine-492401-u6 --wait
```

Other one-off jobs: `placeup-external-api-12h` (API connectors),
`placeup-job-description-repair` (thin JDs), `placeup-stale-jobs-sweeper`.

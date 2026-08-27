# PlaceUp — Outstanding Deploy Checklist

Two releases are now sitting in the tree undeployed: the **July 18, 2026
overhaul** (code landed 2026-08-17, commit `8202cf4`) and the **August 24,
2026 dependency audit** (uncommitted at the time of writing). This is the
combined, ordered list of what is left to do.

Steps 1–2 are the only ones that cannot be automated — they need credentials
that only you hold.

---

## 1. Rotate the Ollama Cloud API key — BLOCKING, not yet done

The key was pasted into a chat window, so it must be treated as public. This
is still outstanding from the July release. Nothing else in step 3 should ship
before it.

1. In the Ollama Cloud console, revoke the existing key and issue a new one.
2. Create the secret and add the new value:

```powershell
gcloud.cmd secrets create OLLAMA_API_KEY --project steel-shine-492401-u6 --replication-policy automatic
echo <NEW_KEY> | gcloud.cmd secrets versions add OLLAMA_API_KEY --project steel-shine-492401-u6 --data-file=-
```

**Verified clean:** no Ollama key is hardcoded anywhere in the tracked tree.
The only references are `deploy_openclaw_tailor.ps1` (reads from Secret
Manager), `compose.yaml:241` (the local dummy value `ollama-local`), and the
documentation. The exposure is the chat paste alone.

## 2. Confirm the required env/secrets exist

- `OPENCLAW_TAILOR_ENABLED=true`
- `OPENCLAW_TAILOR_URL=<service url>`
- `OPENCLAW_TAILOR_TOKEN` (existing secret)
- `OLLAMA_API_KEY` (the rotated one from step 1)

Optional, all defaulted: `SCRAPER_RETENTION_DAYS` (60),
`SCRAPER_GAP_BACKFILL_ENABLED` (true), `TAILOR_MAX_CONCURRENCY` (16 per
instance).

---

## 3. Deploy, in this order

The dependency changes carry no migration and no config change — they ride
along with the same image rebuilds the July release already needed.

```powershell
# a) OpenClaw tailoring service — needs the rotated key from step 1
backend\deploy\deploy_openclaw_tailor.ps1 -ProjectId steel-shine-492401-u6 -EnableApiIntegration

# b) API + app server
backend\deploy\deploy_backend.ps1    -ProjectId steel-shine-492401-u6
backend\deploy\deploy_app_server.ps1 -ProjectId steel-shine-492401-u6

# c) Scraper image (retention default + gap backfill)
backend\deploy\deploy_country_scrapers.ps1 -ProjectId steel-shine-492401-u6

# d) Retention job + daily schedule (one-time creation)
gcloud.cmd run jobs create placeup-job-retention --region us-east1 --project steel-shine-492401-u6 `
  --image us-east1-docker.pkg.dev/steel-shine-492401-u6/placeup/backend:latest `
  --command python --args="-m,app.workers.job_retention" `
  --set-secrets DATABASE_URL=DATABASE_URL:latest --max-retries 1 --task-timeout 3600
gcloud.cmd scheduler jobs create http placeup-job-retention-daily --project steel-shine-492401-u6 `
  --location us-east1 --schedule "0 9 * * *" `
  --uri "https://run.googleapis.com/v2/projects/steel-shine-492401-u6/locations/us-east1/jobs/placeup-job-retention:run" `
  --oauth-service-account-email placeup-api-sa@steel-shine-492401-u6.iam.gserviceaccount.com

# e) Frontend
cd frontend
npm ci          # NOT npm install — package-lock.json is the audited artefact
npm run build
.\deploy_frontend.ps1
```

## 4. Backfill the ATS analysis (after the GPU deploy)

```powershell
.\backend\deploy\deploy_ats_model.ps1 -ProjectId steel-shine-492401-u6 -ApiRegion us-east1 -GpuRegion us-east4 -DbInstance placeup-backend -CreateSchedule
```

---

## 5. Post-deploy smoke checks

- `POST /api/apply/{id}/approve` returns **402** for a non-Elite account and
  succeeds for Elite.
- The Jobs page "All open" view returns the full 60-day window, and selecting
  a role filter returns results rather than an empty list.
- Upload a PDF resume — this exercises the `PyPDF2` → `pypdf` swap. A
  freshly built image uses `pypdf`; the `PyPDF2` fallback should never fire.
- Tailor one resume end to end, confirming the OpenClaw service answers with
  the rotated key.
- `/api/analytics/market` still serves the Overview market widget
  (`/api/analytics/dashboard` is deleted by design).

---

## Still unverified, and only you can close it

`make up` has **never been booted for real.** It was written on 2026-08-18 and
has only ever been checked statically — `bash -n` and `shellcheck` clean,
34/34 Makefile targets pass `make -n`, and the compose overlay validates for
core and for the `workers`, `ai` and `ats` profiles. No Docker daemon is
reachable from the assistant sandbox, so the first true boot has to happen on
your machine:

```bash
make up          # then: make up-workers | up-ai | up-ats | up-full
```

`scripts/bootstrap-ubuntu.sh` (251 lines) is also still untracked and has
never been committed or run. It passes `bash -n` and `shellcheck -S warning`.

---

## Housekeeping left in the tree

- `_to_delete/` at the repo root holds 34 files that need removing by hand —
  stranded `.fuse_hidden*` and `.git/index.lock` artifacts from the assistant
  session, plus `s -ExecutionPolicy RemoteSigned) ; (& d:…Activate.ps1)`,
  which was a `git log` capture written under a mangled filename by a bad
  PowerShell paste. Nothing in that folder is referenced by anything.
- 28 files had drifted to CRLF on disk while their committed blobs were LF,
  which is why `git status` was showing a 29-file diff that was almost
  entirely whitespace. They have been converted back to LF; the only real
  content changes left are the six files in this pass plus your own
  `README.md` edit.

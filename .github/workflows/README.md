# GitHub Actions CI/CD

Use **Actions -> Deploy to Cloud Run + Firebase Hosting -> Run workflow** to
deploy from GitHub Actions.

Production deploys are currently safest from the repo root with:

```powershell
.\deploy_separate_cloud_run.ps1 `
  -BackendProjectId steel-shine-492401-u6 `
  -FrontendProjectId placeup-firebase-641222668282 `
  -Region us-east1 `
  -DbInstance placeup-backend
```

That script is the source of truth because it wires Cloud SQL, Secret Manager,
Cloud Scheduler, CORS, Cloud Run services, and Cloud Run jobs together.

The manual GitHub workflow deploys:

1. **Backend** -> Cloud Run (`placeup-api` service + `placeup-job-scraper-6h` and
   `placeup-ats-worker` Cloud Run Jobs) in project `steel-shine-492401-u6`.
2. **Frontend** -> Firebase Hosting in project `placeup-firebase-641222668282`.

Only the parts that changed are rebuilt: backend changes do not rebuild the SPA
and vice versa.

## One-Time Setup

These secrets must exist on the repo (Settings -> Secrets and variables -> Actions):

| Secret | Purpose |
|---|---|
| `GCP_WORKLOAD_IDENTITY_PROVIDER` | `projects/<PROJECT_NUMBER>/locations/global/workloadIdentityPools/github/providers/github` |
| `GCP_DEPLOYER_SERVICE_ACCOUNT` | `ci-deployer@steel-shine-492401-u6.iam.gserviceaccount.com` with `roles/run.admin`, `roles/artifactregistry.writer`, `roles/iam.serviceAccountUser` |
| `FIREBASE_SERVICE_ACCOUNT` | JSON key for a service account in the frontend project with `roles/firebasehosting.admin` |
| `VITE_API_BASE` | Optional override for the frontend API URL. Default is `https://placeup-api-rui2a74muq-ue.a.run.app`. |

### Why Workload Identity Federation?

GCP service-account JSON keys are bearer tokens that do not expire. WIF lets the
workflow mint a short-lived token from its OIDC identity, which avoids storing a
long-lived deploy key in GitHub.

Set it up once with:

```bash
gcloud iam workload-identity-pools create github --location=global
gcloud iam workload-identity-pools providers create-oidc github \
  --location=global --workload-identity-pool=github \
  --issuer-uri=https://token.actions.githubusercontent.com \
  --attribute-mapping=google.subject=assertion.sub,attribute.repository=assertion.repository
gcloud iam service-accounts add-iam-policy-binding ci-deployer@steel-shine-492401-u6.iam.gserviceaccount.com \
  --role=roles/iam.workloadIdentityUser \
  --member="principalSet://iam.googleapis.com/projects/PROJECT_NUMBER/locations/global/workloadIdentityPools/github/attribute.repository/balaprasannagopalvolisetty/placeupcareers"
```

## Manual Trigger

You can skip the backend or frontend half from the workflow input form.

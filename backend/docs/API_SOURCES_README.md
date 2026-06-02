# Official API / ATS Connectors

This package is used by the existing `placeup-job-scraper-6h` Cloud Run Job,
whose schedule is now 8 hours. Do not create a separate 8-hour scraper job.

## Structure

- `app/etl/api_sources/schema.py` - shared `NormalizedJob` model.
- `app/etl/api_sources/http.py` - retry/backoff JSON client.
- `app/etl/api_sources/registry.py` - ATS token registry pattern.
- `app/etl/api_sources/connectors/adzuna.py` - Adzuna API connector.
- `app/etl/api_sources/connectors/greenhouse.py` - Greenhouse public JSON connector.
- `app/etl/api_sources/firestore_sink.py` - Firestore batch upsert by `job_id`.
- `app/etl/api_sources/runner.py` - standalone and scraper-integrated runner.

## Add a Source

1. Create `app/etl/api_sources/connectors/<source>.py`.
2. Implement `fetch(params) -> list[NormalizedJob]`.
3. Add it to `runner.py`.
4. Keep secrets in env vars / Secret Manager only.
5. Log counts, never raw keys.

## Run Locally

```powershell
python -m app.etl.api_sources.runner --sources adzuna --queries "Software Engineer" --countries us --sink postgres
python -m app.etl.api_sources.runner --sources greenhouse --sink firestore
```

## Deploy

Use the existing backend deploy script. It updates the existing
`placeup-job-scraper-6h` job and does not create an 8-hour duplicate.

Required secrets for Adzuna:

- `ADZUNA_APP_ID`
- `ADZUNA_APP_KEY`

Greenhouse uses public board tokens via `GREENHOUSE_BOARD_TOKENS` when set.
If that secret/env var is missing, it falls back to active Greenhouse tokens in
`app.services.h1b_sponsor_boards`.

# PlaceUp Bug Fixes and Cloud-Only Cleanup

## Completed

- Jobs time filters now send `tz_offset` from the frontend and the backend computes `today` / `yesterday` from the user's local midnight.
- Jobs page requests use 3 retry attempts, exponential backoff, 15-second aborts, and keep stale jobs visible on errors.
- Dashboard summary returns `has_resume` and `active_resume_name`, so the overview can show uploaded/scoring state even when score is `0`.
- Job list, top matches, and job detail return baseline ATS scores when no active parsed resume text is available, with `score_type`.
- Job stats/counts continue to read from `master_jobs` when available through `PostgresClient.count_jobs`.
- Added `/api/jobs/pipeline-status` for total/active/inactive job counts and latest scrape/run metadata.
- Jobs page shows a pipeline status strip with active jobs and latest scrape timing when available.
- Apply tracker now records follow-up fields: heard back, position still open, salary info, and notes.
- Firestore user applications persist the additional apply-tracker fields.
- Resume upload no longer deletes previous resumes in the backend, and the frontend appends the uploaded resume instead of replacing the list.
- Analytics frontend no longer uses hardcoded fallback metrics/time-series/scores.
- `JobDetailPage` reads Pro/Elite status from the authenticated user plan instead of hardcoding `isPro = false`.
- SQLite is rejected in config, active app dependencies route to Postgres/Firestore, and legacy script imports were moved away from `SQLiteClient`.
- In-process scheduler startup is absent from `main.py`; scraping remains a Cloud Scheduler / Cloud Run Job concern.

## Notes

- `backend/app/db/local_db.py` is retained as a reference file only and is no longer imported by active app or script entry points.
- Local development now requires Postgres plus Firestore credentials or cloud endpoints.
- If production still shows only 16 jobs, the likely remaining cause is pipeline data volume: verify the Cloud Run scraper job and `ingest_runs` via `/api/jobs/pipeline-status`.

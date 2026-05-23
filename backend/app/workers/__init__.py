"""
Background workers - designed to run as separate Cloud Run Jobs so they
do not consume API request-handling capacity.

Workers:

- `ats_worker`        - recomputes per-user ATS scores out-of-band.
- `companies_export`  - exports unique company/location pairs to email
                         and optional Google Sheets.
- (scraper)           - owned by app.etl.jobs_scraper_6h; runs in its own
                         Cloud Run Job too. See deploy.yml.

Splitting these off the API container keeps the API small, fast, and
CPU-light because heavier NLP and network-bound work happens in a
separate process tree.
"""

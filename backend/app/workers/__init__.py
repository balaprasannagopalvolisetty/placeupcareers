"""
Background workers — designed to run as separate Cloud Run Jobs so they
do not consume API request-handling capacity.

Two workers live here:

- `ats_worker`        — recomputes per-user ATS scores out-of-band.
- (scraper)           — owned by app.etl.jobs_scraper_6h; runs in its own
                         Cloud Run Job too. See deploy.yml.

Splitting these off the API container is what gets us the third Cloud
Run service the user asked for (API + scraper + ATS worker). The API
container can stay small, fast, and CPU-light because the heavy NLP and
network-bound work happens in a separate process tree.
"""

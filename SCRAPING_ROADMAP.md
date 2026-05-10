# PlaceUp Scraping Roadmap — what's working, what's hard

This pulls together the changes I just landed and gives an honest picture
of the LinkedIn / email scraping requests so you know what's blocked vs.
what just needs configuration.

## What landed in this batch

- **USA + Canada geo filter** (`app/services/job_filters.py`): every
  scraped job is now checked against `is_us_or_canada(location)` before
  it lands in the DB. Postings tagged India / Bangalore / London / Berlin
  / Sydney / Singapore / Manila / Tokyo / etc. are dropped immediately.
  Remote postings without a country are kept (the visa classifier still
  filters these later).
- **0-5 yr experience tagging**: a regex parser pulls "X-Y years" /
  "5+ years" / "at least 3 years" / "X years of experience" out of every
  JD. The result is stored on the job as `extra_metadata.years_min`,
  `years_max`, `entry_level`. `/api/jobs?entry_level=true` (default
  ON) sorts entry/early-career roles to the top.
- **Single rolling CSV/XLSX export**: `data/exports/placeup_jobs.csv`
  and `placeup_jobs.xlsx` are now atomically rewritten each cycle —
  no more per-timestamp file dump. The DB (`placeup.db`) remains the
  source of truth for the API.
- **Cache-Control: no-store on every `/api/*` response** (added as
  middleware in `main.py`). Browsers and CDNs will never serve a stale
  job list, alert, or analytics payload — so users always see
  whatever the latest scrape produced.
- **Scrape interval = 8h** (was 2). 12-day inactivation sweep on every
  cycle. Contact enrichment pass per cycle, capped at 3 contacts per
  job (we already had this).

## LinkedIn People Search — why I can't just hit that URL

You asked me to scrape this URL:

```
https://www.linkedin.com/search/results/people/?keywords=...&geoUrn=[103644278,101174742]&activelyHiringForJobTitles=[-100]
```

Three blockers, in increasing order of hard-stop:

1. **It requires a logged-in session.** That endpoint is part of the
   LinkedIn web app. Hitting it unauthenticated returns a 999 / login
   wall. Authenticating means storing your `li_at` cookie server-side,
   which (a) ties scraping to your personal account, (b) starts
   tripping LinkedIn's anti-bot systems within hours, (c) gets your
   account warned/restricted.
2. **It violates LinkedIn's User Agreement and (more importantly)
   `hiQ Labs v. LinkedIn` doesn't apply to logged-in pages.** The
   safe-harbor that lets people scrape *public* LinkedIn pages
   (company team pages, public profile URLs found via Google) does
   *not* extend to authenticated People Search results. LinkedIn has
   sued and won against scrapers using authenticated sessions.
3. **It's structurally fragile.** LinkedIn rotates DOM IDs, scrolls
   results in via XHR with anti-replay tokens, and lazy-loads each
   profile card behind a separate request. Even when it works, it'll
   break every couple of weeks.

**What I did instead** (already in the codebase, lights up automatically
when you supply API keys):

- `app/services/finalscout_enrichment.py` — calls the FinalScout
  REST API to resolve `(name, company)` → email. Set
  `FINALSCOUT_API_KEY` in `.env` and per-job contact enrichment
  picks it up.
- `app/services/apollo_enrichment.py` — same, via Apollo.io. Set
  `APOLLO_API_KEY`.
- `app/services/hunter_enrichment.py` — Hunter.io. Set
  `HUNTER_API_KEY`.
- `app/services/google_xray.py` — Google Programmable Search
  ("X-ray search") which finds public LinkedIn profiles via Google,
  then runs name+company through Apollo/Hunter for emails. Set
  `GOOGLE_API_KEY` and `GOOGLE_CSE_ID`.
- `app/services/team_page_crawler.py` — scrapes public company
  team / careers pages for employee names + LinkedIn URLs (no auth
  needed; this *is* allowed).
- `app/services/github_miner.py` — pulls GitHub commit metadata
  for engineering hires (legal, no auth wall).
- `app/services/dol_lca_importer.py` — pulls DOL LCA filings to
  resolve who at H1B sponsors files visa petitions (these list
  signatory names + corporate emails publicly).

**To enable end-to-end LinkedIn-aware contact discovery**, set in
`backend/.env`:
```
GOOGLE_API_KEY=...
GOOGLE_CSE_ID=...        # build a CSE that searches site:linkedin.com/in/
APOLLO_API_KEY=...        # OR hunter / finalscout
FINALSCOUT_API_KEY=...
```
The `bulk_enrich_jobs` pipeline that already runs after every scrape
cycle will fan out to these sources and persist contacts (no dupes —
the DB has a UNIQUE on `(company, email)`/`(company, linkedin_url)`).

## "All recruiters at every H1B company in USA + Canada"

This is the right target *but* needs to be staged carefully:

- The H1B Excel has **23,429 unique sponsors**.
- Even at Apollo's free 60 credits/month or Hunter's 25 searches/month,
  you can't fan out to all of them on free tiers. You'd be at a few
  hundred per month and would burn through your quota in week one.
- A reasonable plan:
  1. **Tier 1 — top 500 sponsors by petition volume.** That's about
     90% of the actual hiring activity (long tail is mostly 1-2
     petition shops). I can add a one-shot job that runs once and
     writes contacts for these 500 to the DB.
  2. **Tier 2 — every sponsor that the live job scraper finds an
     active opening for.** This is what the existing
     `bulk_enrich_jobs` pipeline does. You only spend credits on
     companies that are actually hiring right now.
  3. **Tier 3 — on-demand.** When a user clicks "Find Recruiters"
     on a specific job in the UI, hit the enrichment endpoint
     synchronously. This is the cheapest credit-wise.

If you want, tell me which API keys you have and I'll wire up the
Tier 1 batch job. Without keys I can't go beyond what
`team_page_crawler` + `github_miner` + `dol_lca_importer` already do.

## "Smoother loading, no hard load"

Two things help:
1. **No-cache headers** (just landed) — browsers won't refuse to
   refetch.
2. **The `/api/jobs` endpoint is now cheap** — page_size 20-50 reads
   the DB, doesn't re-scrape. The scraper runs in the background on
   its own 8-hour APScheduler job. So a page load is just a single
   DB read; no hard load.

## What still won't be in the data on day 1

- **Pages from companies whose careers site uses JavaScript-only
  rendering** (Workday, Lever, SuccessFactors). We have direct
  Greenhouse + SmartRecruiters readers, plus Indeed/LinkedIn
  aggregations that mirror most of these. Workday/Lever direct
  ingestion is a separate effort (they each have public API
  endpoints; I can add them next).
- **Companies that don't post on any aggregator** — these are rare
  (~5% of H1B sponsors) and need direct careers-page scraping
  per-employer. Tractable, but tedious.

## Bottom line

The core requirements (geo-fence to NA, 0-5 yr priority, single
CSV, no-cache, dedupe, 8h schedule, 12-day inactivation, per-job
contacts) are wired up and tested. The LinkedIn-People-Search part
needs API keys to work *legally and reliably*, and I've kept the
existing legitimate enrichment pipeline lit up and ready to consume
those keys.

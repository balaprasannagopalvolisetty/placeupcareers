# PlaceUp — Global Job Coverage Plan (ingestion addendum)

**Status:** Proposal / architecture spec (no code yet — implement after review)
**Companion to:** `GLOBAL_VISA_UPGRADE_PLAN.md` (that doc = visa *data*; this doc = job *ingestion*)
**Goal:** Stop limiting positions to US/Canada. Collect roles **only from companies that actually sponsor visas in their own country**, across all ~25 target countries.

> **REVISION (per your clarification, 2026-05-30):** The collection model is **sponsor-verified-companies-only**. PlaceUp does **not** ingest every visa-friendly-sounding role; it ingests jobs **from companies on each country's verified visa-sponsor list**, crawling those companies' career boards. This is exactly what your US H1B pipeline already does (`h1b_sponsor_pipeline.py` → "pulls every curated sponsor's ATS board") — generalized to every country. Geography is a scope filter; **the company being a verified sponsor is the gate.**

---

## 0. Honest framing of "without missing anything"

Under the sponsor-only model, "everything" = **every job posted by every verified visa-sponsor company in each of the 25 countries** — not every job on Earth. That's the right target for a visa-seeker product, and it's far cleaner (every result is sponsor-backed). The honest limits:

- We can only collect from sponsors we can **identify** (official registers) and whose **career board we can resolve** (domain → ATS). A sponsor with no public register entry or an unscrapable bespoke careers page is a gap.
- Countries with **no central sponsor register** (UAE, Japan, Switzerland, Gulf — see companion plan §2) have no authoritative "verified sponsor" list, so for those we fall back to "companies that explicitly state sponsorship in the posting" and label them *indicated, not register-verified*.
- LinkedIn authenticated search remains off-limits (`SCRAPING_ROADMAP.md`).

So the target is **every role from every resolvable verified sponsor, per country**, with the pipeline built so adding a country or sponsor source is config, not code. Where a sponsor or country can't be reached, the system says so rather than pretending.

---

## 1. Why PlaceUp is US/Canada-only today (two chokepoints)

The sources can already go global — the code throws the jobs away. Two precise gates:

### Chokepoint 1 — the geo filter (the hard wall)
`backend/app/services/job_filters.py` → `is_us_or_canada(location)` is called on **every** scraped job before it lands in the DB. It:
- **Hard-rejects** anything matching `EXCLUDE_KEYWORDS` — which literally lists `"united kingdom"`, `"london"`, `"germany"`, `"berlin"`, `"australia"`, `"singapore"`, `"india"`, etc.
- Only accepts US state codes, Canadian provinces, and US/CA remote phrasing.

This single function is the reason no UK/EU/AU/APAC role ever survives.

### Chokepoint 2 — North-America-locked API ingest
`backend/app/etl/external_api_ingest.py` → `run(..., locations="North_America")` hardcodes the region. Yet the JSearch / LinkedIn-jobs RapidAPI you already use supports multi-country filters directly:
```
location_filter="United States" OR "United Kingdom"   # (from JSearch_API_info.txt)
```
So the upstream API can return global jobs the moment we ask for them.

### Secondary: source list is sponsor-US-centric
The H1B-sponsor ATS pipeline (`h1b_sponsor_pipeline.py`, `h1b_sponsor_boards.py`) only knows US H-1B employers. Tier-1 ATS sources (`etl/sources/tier1_ats.py`) and `scrapegraph_targets.py` are US-skewed.

---

## 2. The model: collect from verified sponsor companies, per country

The gate is the **company**, not the role text. A job is collected **iff its company is on the verified visa-sponsor list for the country the role sits in**.

```
for each target country:
    sponsors = verified_visa_sponsors(country)        # from official register (visa plan §B)
    for each sponsor:
        board = resolve_career_board(sponsor)          # domain -> ATS token
        jobs  = scrape_board(board)                    # Greenhouse/Lever/Ashby/Workday/SmartRecruiters
        keep every job, stamped sponsor_verified=True, visa_country=<iso2>
```

This is the **generalization of the existing US pipeline**. Today `h1b_sponsor_pipeline.py` does steps 2–4 for US H-1B sponsors only (curated catalog in `h1b_sponsor_boards.py`, ATS dispatch in `careers_ats.py`, name→domain in `sponsor_domains.py`). We lift that into a country-parameterized pipeline.

```python
# backend/app/etl/sponsor_pipeline.py  (generalized from h1b_sponsor_pipeline.py)
async def scrape_sponsor_boards(country_code: str, *, tiers=None, max_jobs_per_sponsor=500):
    sponsors = await get_visa_sponsors(country_code, tiers)   # visa_sponsors table (visa plan §3.3)
    boards   = [resolve_board(s) for s in sponsors]           # sponsor -> {ats, token}
    results  = await gather(scrape_ats(b) for b in boards if b)
    for job in results:
        job.visa_country     = country_code
        job.sponsor_verified = True
        job.sponsor_source   = sponsor_source_for(country_code)   # uscis / uk_register / ind_nl ...
    return dedupe(results)
```

**Geography's role shrinks to scope, not gate.** `is_us_or_canada()` is removed; the new check only confirms a crawled job's location actually falls in the sponsor's country (a US sponsor's board may also list a London role — we keep it under GB only if GB is a target country and the company is also a GB-verified sponsor, otherwise it's tagged by the role's country and kept only if that country is in scope).

```python
# backend/app/services/job_filters.py  (rewrite — now a light scope check, not the gate)
def in_scope(location: str, country_code: str | None) -> tuple[bool, str | None]:
    iso2 = country_code or resolve_country(location)     # geo.py helper
    return (iso2 in settings.TARGET_COUNTRIES, iso2)
```

- `EXCLUDE_KEYWORDS` is **deleted**.
- `resolve_country()` = new `geo.py` helper (extends the US-state/CA-province logic to all 25 countries).
- The country-aware classifier still runs, but as a **secondary safety net** — if a verified sponsor's specific posting says "this role: citizens only / no sponsorship," the classifier can demote that single job. Sponsor-verified is the default; the classifier only subtracts.

### The hard part this puts front-and-center: building the per-country sponsor catalogs

Sponsor-only collection is only as good as the sponsor lists. Per country:

| Country | Verified sponsor source | Build method |
|---|---|---|
| US | USCIS H-1B (have it) | exists → `visa_sponsors` US rows |
| UK | Register of Licensed Sponsors (public CSV, weekly) | `import_uk_sponsors.py` → resolve domains → ATS |
| Netherlands | IND recognised sponsors (public list) | `import_nl_sponsors.py` |
| Ireland | Employment-permit holders / Trusted Partner | `import_ie_sponsors.py` |
| New Zealand | Accredited employers (public) | `import_nz_sponsors.py` |
| Australia | Approved sponsors | `import_au_sponsors.py` |
| Germany / others (no register) | No authoritative list | fall back: companies whose postings state sponsorship → tagged *indicated, not verified* |

Each importer fills `visa_sponsors(country_code, employer_name, source)`; then a shared **domain→ATS resolver** (generalize `sponsor_domains.py` + `careers_ats.py`) turns each sponsor into a crawlable board. **This sponsor-catalog build is now the critical path of the whole project** — it's what makes "sponsor-only" possible.

---

## 3. Global source matrix — under the sponsor-only model

Primary source is the **verified sponsors' own career boards (layers B + C)** — that's where every kept job comes from. The broad job APIs (layer A) are **demoted to discovery**: we use them to find *which sponsors are hiring right now* and to surface *candidate new sponsors* (companies repeatedly posting "visa sponsorship available"), which then get vetted into `visa_sponsors`. A job from a job-API is only kept if its company is already verified. Everything dedupes into `master_jobs`.

| Layer | Source | Global reach | Status |
|---|---|---|---|
| **A. Job APIs** | JSearch / LinkedIn-jobs RapidAPI (`external_api_ingest.py`) | Any country via `location_filter` | **flip config** — already paid for |
| | USAJobs API | US federal only | keep for US |
| | Adzuna API | 20+ countries (UK, DE, AU, FR, NL, SG…) — official, cheap | **add** |
| | Jooble / Careerjet / Arbeitnow (EU) | multi-country | optional add |
| **B. Global ATS boards** | Greenhouse, Lever, Ashby, Workday, SmartRecruiters, Recruitee, Personio (EU), Teamtailor (EU) | These host jobs for employers worldwide; board JSON is country-agnostic | **extend** `tier1_ats.py` with EU/APAC-heavy ATSes (Personio, Teamtailor, SmartRecruiters) |
| **C. Curated visa-sponsor career pages** | Per-country sponsor registers from the visa plan → their career-page ATS | UK register, IND NL, NZ accredited, Ireland permit holders | **add** importers (Workstream B of companion plan) feed `visa_sponsors`, then crawl their boards |
| **D. Country job portals (official)** | Make-it-in-Germany, EURES (EU-wide), Workforce Australia, MyCareersFuture SG, Job Bank Canada | Government, visa-friendly by design | **add** where APIs/feeds exist |

**Keep logic (sponsor-only):** keep a job **iff `company ∈ visa_sponsors[country]`**. Layers B/C *are* verified sponsors, so everything they yield is kept. Layer A/D results are kept **only after** matching the company to a verified sponsor (fuzzy match via `rapidfuzz`, already used in `everify`/contact code); unmatched companies become *sponsor candidates* for review, not live jobs. Dedup on normalized `(company, title, location)` already exists in `utils/deduplication.py` — extend the key with `visa_country`.

---

## 4. Config-driven countries (add a country = no code)

```python
# backend/app/config.py
TARGET_COUNTRIES: set[str] = {
  "US","CA","GB","IE","DE","NL","AU","NZ","SG","AE","JP","PT",   # Tier 1
  "FR","ES","SE","DK","NO","CH","FI","BE","AT","PL","EE","QA","SA"  # Tier 2
}
# Per-country search terms for the job APIs (so JSearch/Adzuna query each one)
COUNTRY_QUERY = {
  "GB": {"location": "United Kingdom", "adzuna_cc": "gb"},
  "DE": {"location": "Germany",        "adzuna_cc": "de"},
  # ...
}
```

The 8h cycle (per `SCRAPING_ROADMAP.md`) fans out over **`visa_sponsors` per country → their ATS boards** (the `sponsor_pipeline`), reusing the existing `h1b_sponsor_max_jobs` / `h1b_sponsor_concurrency` caps so volume stays bounded. `external_api_ingest.run()` runs alongside in **discovery mode** — per-country `COUNTRY_QUERY` is used to spot which verified sponsors are hiring and to nominate candidate sponsors, not to admit jobs directly.

---

## 5. What changes, file by file

**Backend**
```
app/etl/sponsor_pipeline.py     NEW      country-parameterized; generalizes h1b_sponsor_pipeline.py (the new core)
app/etl/import_uk_sponsors.py   NEW      + nl, ie, nz, au — register -> visa_sponsors rows
app/services/sponsor_domains.py CHANGED  generalize name->domain beyond US curated map
app/services/careers_ats.py     CHANGED  add Personio, Teamtailor (EU ATSes) to raise resolve rate
app/services/job_filters.py     REWRITE  is_us_or_canada -> in_scope (light country check, not gate)
app/services/geo.py             NEW      resolve_country(location)->ISO2 for all 25 countries
app/config.py                   CHANGED  TARGET_COUNTRIES (scope set)
app/etl/external_api_ingest.py  CHANGED  demote to discovery: find hiring sponsors / candidate sponsors
app/utils/deduplication.py      CHANGED  dedup key includes visa_country
app/services/visa_classifier.py CHANGED  country-aware; now a per-posting safety net, not the gate
app/db/schema.py / models       CHANGED  visa_sponsors table + sponsor_verified/visa_country (companion plan §3)
```

**Data / config**
```
backend/.env / config            Adzuna app_id+key; reuse existing RapidAPI key
```

No frontend changes are strictly required for ingestion — but the visa plan's country filter on `JobsPage` (target-country preference) is what lets users *browse* the new global volume sensibly.

---

## 6. Rollout phases (safe, reversible)

| Phase | Deliverable | Risk control |
|---|---|---|
| **G1** | Generalize `h1b_sponsor_pipeline.py` → `sponsor_pipeline.py(country_code)`; feed from `visa_sponsors`; default scope **US only** (uses existing USCIS list) | Pure refactor of the US pipeline — prove identical output |
| **G2** | Build **UK + NL** sponsor importers (public registers) → resolve domains → ATS; add GB, NL to scope | First non-US sponsor coverage; registers are clean CSVs |
| **G3** | Domain→ATS resolver coverage push (Personio, Teamtailor, SmartRecruiters added to `careers_ats.py`) so more EU sponsors resolve to a crawlable board | Raises % of sponsors we can actually crawl |
| **G4** | Add IE, NZ, AU sponsor importers + scope | Registers exist for all three |
| **G5** | **Discovery mode:** wire job APIs (JSearch/Adzuna) as sponsor-candidate finders + "is this verified sponsor hiring now"; keep only company-matched jobs | API spend bounded; no unverified jobs go live |
| **G6** | No-register countries (DE, UAE, JP, Gulf…): posting-stated-sponsorship fallback, labeled *indicated, not verified* | Clearly badged; never mixed with register-verified |

G1 is a no-op refactor (US-only, same output as today). Every later phase adds a country only once its **sponsor catalog** exists — so the system never shows a country with no verified sponsors behind it. Fully reversible — shrink scope to roll back.

---

## 7. Coverage ceiling — what we still won't have (be honest with users)

- **LinkedIn authenticated search** — out (legal + anti-bot; see `SCRAPING_ROADMAP.md`). We get LinkedIn jobs only via the RapidAPI job feed, not people/everything.
- **Tiny local employers** that never post to any aggregator or ATS — unreachable by definition.
- **Countries with no official register** (UAE, Japan, Gulf, Switzerland) — we get their jobs via APIs/ATS, but **can't independently verify** sponsorship, so those roles show "sponsorship indicated, not verified."
- **Non-English postings** — ingestible, but the classifier needs per-language keyword packs (English + a few majors: German, French, Spanish, Dutch) to score them; until then non-English roles are kept but scored conservatively.

Recommend a one-line UI disclaimer: *"PlaceUp aggregates visa-friendly roles from public job APIs, ATS boards, and official portals across 25 countries. Coverage is broad but not exhaustive — always confirm sponsorship on the listing."*

---

## 8. Decisions for you

1. **No-register countries** (Germany, UAE, Japan, Gulf) have **no authoritative visa-sponsor list.** Under a strict sponsor-only rule we'd show *zero* jobs there. Acceptable, or do you want the "posting-stated-sponsorship, labeled *indicated*" fallback (Phase G6) so those countries aren't empty?
2. **Sponsor catalog order** — after US, which registers first? UK + Netherlands are the cleanest public CSVs; Ireland/NZ/Australia next.
3. **Per-country volume cap** — sane max jobs/sponsor/cycle (existing US default is 500/sponsor)? Same worldwide, or tighter per country?

---

*Implements the ingestion half of going global, under the sponsor-verified-companies-only model. Pair with `GLOBAL_VISA_UPGRADE_PLAN.md` for the visa-data/classifier half. Recommended first slice: Phase G1 (generalize the US sponsor pipeline, no behavior change) + G2 (UK & Netherlands sponsor catalogs).*
> 2026-05-31 update: the old US/Canada filtering wall has been replaced by the
> 25-country target-country rule engine. The remaining work is adding
> official/free country source importers and sponsor-registry importers.

---

# Appendix A — Source catalog (2026) by feasibility tier

Your full website list, sorted by **how we can legally and reliably ingest it.** This is the honest answer to "all websites without limitations, no 404/500": we don't raw-scrape sites that block bots — we reach their jobs through APIs/feeds instead. Each tier has a different connector.

### Tier 1 — Official government portals & registers (highest trust, scrape/feed-friendly)
Jobs come straight from employers/government; most tolerate polite scraping or offer a feed.

| Country | Portal(s) | Access |
|---|---|---|
| 🇺🇸 USA | USAJobs | **API** (have key) |
| 🇬🇧 UK | Find a Job (gov.uk), NHS Jobs; **Register of Licensed Sponsors** | feed / CSV register |
| 🇨🇦 Canada | Job Bank Canada | feed/scrape |
| 🇦🇺 Australia | Workforce Australia, APS Jobs; **approved sponsor list** | scrape/register |
| 🇳🇿 NZ | Jobs.govt.nz; **Green List / accredited employers** | scrape/register |
| 🇩🇪 Germany | Make it in Germany, BA Jobsuche | **BA has API** |
| 🇫🇷 France | France Travail | **API** |
| 🇳🇱 Netherlands | Werk.nl; **IND recognised sponsors** | scrape/register |
| 🇸🇪 Sweden | Platsbanken | **API (JobTech)** |
| 🇩🇰 Denmark | Workindenmark, Jobindex(gov feed) | scrape |
| 🇫🇮 Finland | Työmarkkinatori | **API** |
| 🇳🇴 Norway | NAV Arbeidsplassen | **API** |
| 🇮🇪 Ireland | JobsIreland; **employment-permit holders** | scrape/register |
| 🇵🇹 Portugal | IEFP NetEmprego | scrape |
| 🇪🇸 Spain | SEPE | scrape |
| 🇮🇹 Italy | Cliclavoro | scrape |
| 🇧🇪 Belgium | VDAB, Forem, Actiris | VDAB API |
| 🇱🇺 Luxembourg | ADEM | scrape |
| 🇸🇬 Singapore | MyCareersFuture | **API** |
| 🇯🇵 Japan | Hello Work | scrape |
| 🇰🇷 Korea | Work24 | scrape |
| 🇹🇼 Taiwan | TaiwanJobs | scrape |
| 🇭🇰 Hong Kong | Labour Dept IES | scrape |
| 🇦🇪/🇸🇦/🇶🇦 Gulf | MOHRE, Jadarat/TAQAT, Qatar Careers | scrape (no register) |
| 🇪🇺 EU-wide | **EURES** | **API** |

### Tier 2 — ATS boards (cleanest of all; this is how we crawl verified sponsors)
Greenhouse, Lever, Ashby, Workday, SmartRecruiters, **Personio** (EU), **Teamtailor** (EU), Recruitee, Workable. Public JSON endpoints, country-agnostic, no blocking. **Primary collection layer** under the sponsor-only model.

### Tier 3 — Niche / tech / startup / graduate boards (mostly scrapable or have feeds)
Landing.jobs, ITJobs.pt, Just Join IT, No Fluff Jobs, Wellfound, Y Combinator Jobs, Otta, Welcome to the Jungle, EU-Startups Jobs, Relocate.me, **Europe Language Jobs**, Fantastic.jobs, Glints, CakeResume, Graduateland, Gradcracker, Prospects, Bright Network, GaijinPot/japan-dev/Daijob, Work in Estonia, Jobs in Finland, Duunitori, CV.ee. Many expose RSS/JSON; the rest are low-volume and bot-tolerant. Good for the "English-friendly / relocation / startup / graduate" angles you listed.

### Tier 4 — Major aggregators that BLOCK scraping → **OUT OF SCOPE (decided 2026-05-31)**
> **Decision:** PlaceUp will use **official portals + ATS boards + bot-tolerant niche boards only.** No raw-scraping and no paid aggregator APIs for the sites below. They are listed only to document what is intentionally excluded. (The existing JSearch key may stay wired but disabled/optional — not a primary source.) This guarantees no 404/429/500 from blocked sites and zero legal exposure; the trade-off is we miss jobs posted *exclusively* on these aggregators.

LinkedIn, Indeed, Glassdoor, Monster, ZipRecruiter, CareerBuilder, SEEK, Bayt, GulfTalent, Naukrigulf, JobStreet, Saramin, JobKorea, Wanted, 104/1111, Reed, TotalJobs, CV-Library, StepStone, XING, FINN, InfoJobs, Pracuj.pl, Jora, TradeMe, Workopolis, Eluta, SimplyHired, Jooble, Talent.com.
**These cause the 404/429/500/legal problems.** Reach them only through:
- **JSearch RapidAPI** (have key) — already aggregates LinkedIn/Indeed/Glassdoor/ZipRecruiter-style postings, any country via `location_filter`.
- **Adzuna API** — aggregates Reed/TotalJobs/CV-Library/many EU boards across 20+ countries (cheap official key).
- **Apify actors** — managed scrapers for Indeed/LinkedIn/SEEK/Bayt that handle anti-bot for you (paid per run).
- Otherwise **skip** — do not raw-scrape.

> Net (per 2026-05-31 decision): **Tiers 1–3 only** — scrape/feed directly. Tier 4 excluded. Full, clean coverage of every reachable visa-sponsor job **without** hitting blocked sites or paying for aggregators.

---

# Appendix B — Your 12 requirements → implementation

| # | Requirement | How / where | Feasible? |
|---|---|---|---|
| **B1** | Only positions posted in **last 8h** | Filter on `posted_at >= now-8h` at ingest + `/api/jobs?since=8h`; cycle already runs ~8h | ✅ |
| **B2** | Collect from **all 25 listed countries** | `TARGET_COUNTRIES` scope (already in place per repo note) + Tier-1/2/3 source importers per country | ✅ staged |
| **B3** | **Label each position by country + visa** | `visa_country` + `visa_programs` columns (visa plan §3.2); render as two badges on each job card | ✅ |
| **B4** | From **non-English countries, keep only English-friendly** roles | New `english_friendly` flag: keep if posting language=English OR JD says "English-speaking/working language English"; drop local-language-only roles in DE/FR/ES/JP/KR/etc. (classifier rule) | ✅ |
| **B5** | **Download company lists per country** into Visa Tracker, **separate table per country** | **DECIDED:** one `visa_sponsors` table keyed by `country_code`, exposed as per-country views/tabs (`/api/visa/sponsors/{cc}`). Looks like separate lists in the UI; one schema to maintain. | ✅ |
| **B6** | Collect from **all websites, no 404/500** | **DECIDED: Tiers 1–3 only** (official portals + ATS + niche boards); Tier-4 aggregators excluded. Robust retry/backoff + per-source circuit-breaker so a flaky source is skipped, not retried into errors | ✅ (within Tier 1–3) |
| **B7** | **No duplication** | Extend `utils/deduplication.py` key to `(normalized_company, normalized_title, visa_country)` + canonical job URL hash | ✅ |
| **B8** | **Remove US/Canada-only rules** | `is_us_or_canada` / `EXCLUDE_KEYWORDS` removed (repo note says done); verify none remain | ✅ |
| **B9** | **Clean data to frontend, no issues** | Stable `/api/jobs` contract; null-safe normalizers (already present in `JobsPage`); typed badges | ✅ |
| **B10** | **Remove unwanted scripts on the page** | Delete deprecated bg components named in `context.md`: `CareerNetworkBackground`, `DNAHelixBackground`, `ParticleBackground` (+ unused imports) — lighter page, faster load | ✅ |
| **F1** | **All countries + all visas in filters** | Filter dropdowns sourced from `/api/visa-guides` (countries) + visa-program enum; multi-select | ✅ |
| **F2** | **Data fetch < 15s** | Server-side pagination + indexed `posted_at`/`visa_country` (indexes exist) + Redis cache of hot queries + the existing `Cache-Control: no-store` stays; target <2s typical | ✅ |

---

# Appendix C — Decisions (locked 2026-05-31)

1. **Tier-4 aggregators** → ❌ **Excluded.** Official portals + ATS boards + bot-tolerant niche boards only. No raw-scraping, no paid aggregator APIs.
2. **B5 sponsor storage** → ✅ **One `visa_sponsors` table keyed by `country_code`**, surfaced as per-country views/tabs in the Visa Tracker.
3. **Implementation** → ⏸ **Plan-only for now.** No code until you approve the build. When approved, recommended first slice: B8 verify → B1 (8h) → B3 (country/visa labels) → B10 (remove dead scripts) → F1 (filters), then source importers per country (Tier 1 official portals first, then ATS-based sponsor crawl).

---

# Appendix D — Build order when you say go (Tier 1–3, plan-only until approved)

1. **Frontend quick wins (visible, low-risk):** confirm US/CA rules gone (B8), 8h-only filter (B1), country + visa badges on each card (B3), all-countries + all-visas filters (F1), remove dead background scripts `CareerNetworkBackground`/`DNAHelixBackground`/`ParticleBackground` (B10), pagination + caching for <15s loads (F2).
2. **Official-portal importers (Tier 1), country by country:** start with API-backed ones (USAJobs ✓, France Travail, Sweden JobTech, Finland, Norway NAV, Singapore MyCareersFuture, EURES), then scrape-based (UK Find a Job/NHS, Job Bank Canada, Werk.nl, Workforce Australia, Jobs.govt.nz, BA Jobsuche, JobsIreland, etc.).
3. **Sponsor registers → `visa_sponsors`:** UK Licensed Sponsors, IND NL, Ireland permits, NZ accredited, AU approved → resolve domain → crawl their ATS boards (Tier 2).
4. **Niche/English-friendly boards (Tier 3):** Relocate.me, Europe Language Jobs, Landing.jobs, Work in Estonia, etc. — strong for the English-friendly-in-non-English-countries requirement (B4).
5. **Cross-cutting:** dedup (B7), English-friendly classifier rule (B4), per-source circuit-breaker so no 404/500 storms (B6), clean API contract to frontend (B9).

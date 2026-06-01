# PlaceUp — Global Visa Upgrade Plan

**Status:** Proposal / architecture spec (no code yet — implement after review)
**Author:** Planning pass, 2026-05-30
**Scope chosen:** ~25 countries · curated structured dataset · plan before implementation

---

## 1. What we're building and why

Today PlaceUp is **US/H1B-centric**. The whole visa layer assumes one country:

| Area | Current state | Limitation |
|---|---|---|
| Classifier | `visa_classifier.py` keyword matrix (OPT / STEM-OPT / H-1B / GC) | US-only signals; "no sponsorship" tuned to US phrasing |
| Sponsor data | USCIS H-1B Excel → `h1b_sponsors` table | One country, one program |
| Verification | `uscis_match` cross-reference | No equivalent for UK / Germany / Canada registers |
| Frontend | `VisaTrackerPage` = H-1B employer table | No concept of "which country / which visa" |
| Job model | `visa_h1b`, `visa_opt`, `visa_stem_opt` boolean flags | Hard-coded US visa types |

The upgrade has **four workstreams**:

- **A. Global classifier** — detect visa-friendliness for *any* destination country, mapped to that country's actual visa programs.
- **B. Global sponsor data** — go beyond USCIS to per-country licensed-sponsor registers (UK, etc.) plus a generic "known sponsor" model.
- **C. Country Visa Guide page (NEW)** — a curated, per-country reference: visa types, requirements, processing time, cost, official links. ~25 countries seeded.
- **D. Improve the current system** — fix the US-specific assumptions, generalize the data model, harden accuracy/freshness.

The guiding insight from research: **visa rules change every year.** UK general threshold is £41,700 in 2026; Germany's EU Blue Card rose to €50,700 on 1 Jan 2026; Australia's Core Skills threshold rises to AUD 79,499 on 1 Jul 2026. So the curated dataset must be **dated, versioned, and always linked to the official government portal** — we present curated facts *plus* the authoritative link so the user verifies current rules.

---

## 2. Target country set (~25)

Grouped by data confidence. Each ships with: country code, visa programs, official portal, and "supports English-speaking / international hires" notes.

**Tier 1 — proven sponsor markets (seed fully first):**
United States, Canada, United Kingdom, Ireland, Germany, Netherlands, Australia, New Zealand, Singapore, United Arab Emirates, Japan, Portugal.

**Tier 2 — strong secondary markets:**
France, Spain, Sweden, Denmark, Norway, Switzerland, Finland, Belgium, Austria, Poland, Estonia, Qatar, Saudi Arabia.

> The data model supports *any* ISO country; Tier 1/2 are just the seed order. A country with no curated record still renders ("Data coming soon" + official portal link) so the page never 404s.

### Reference table (anchor programs + official portal)

| Country | Primary work visa(s) | Official portal | Verifiable sponsor list? |
|---|---|---|---|
| United States | H-1B, O-1, L-1, F-1 OPT/STEM-OPT, EB-2/3 | uscis.gov | ✅ USCIS data (have it) |
| Canada | Express Entry, LMIA, Global Talent Stream | canada.ca | ⚠️ employer-specific (LMIA) |
| United Kingdom | Skilled Worker, Global Talent, Health & Care | gov.uk | ✅ Register of licensed sponsors |
| Ireland | Critical Skills Employment Permit, General | enterprise.gov.ie | ✅ Trusted Partner / permit list |
| Germany | EU Blue Card, Skilled Worker, Opportunity Card | make-it-in-germany.com | ⚠️ no central register |
| Netherlands | Highly Skilled Migrant, EU Blue Card | ind.nl | ✅ IND recognised sponsors |
| Australia | Skills in Demand (482), 186, 189/190 | immi.homeaffairs.gov.au | ✅ approved sponsor concept |
| New Zealand | Accredited Employer Work Visa (AEWV) | immigration.govt.nz | ✅ accredited employers |
| Singapore | Employment Pass, Tech.Pass | mom.gov.sg | ⚠️ self-assessment (SAT) |
| UAE | Standard Work Permit, Golden Visa | mohre.gov.ae / icp.gov.ae | ❌ employer-handled |
| Japan | Engineer/Specialist in Humanities, HSP | isa.go.jp | ❌ |
| Portugal | D3 Highly Qualified, Tech Visa | imigrante.sef.pt / iapmei.pt | ✅ Tech Visa certified cos |
| France | Talent Passport | france-visas.gouv.fr | ⚠️ |
| Spain | Highly Qualified Professional, Digital Nomad | extranjeros.inclusion.gob.es | ⚠️ |
| Sweden | Work permit | migrationsverket.se | ⚠️ certified operators |
| Denmark | Pay Limit, Positive List, Fast-track | nyidanmark.dk | ✅ fast-track certified |
| Norway | Skilled worker permit | udi.no | ⚠️ |
| Switzerland | L/B work permit (quota) | sem.admin.ch | ❌ quota-based |
| Finland | Specialist / EU Blue Card | migri.fi | ⚠️ |
| Belgium | Single Permit, EU Blue Card | works in regions | ⚠️ |
| Austria | Red-White-Red Card | migration.gv.at | ✅ points-based |
| Poland | Work permit / Blue Card | gov.pl | ⚠️ |
| Estonia | Work / Digital Nomad / Startup | politsei.ee | ⚠️ |
| Qatar | Work residence permit | moi.gov.qa | ❌ |
| Saudi Arabia | Work visa, Premium Residency | visa.mofa.gov.sa | ❌ |

> "Verifiable sponsor list?" drives Workstream B: where ✅, we can cross-reference like we do USCIS today; where ❌, we rely on the classifier + job-posting signals only.

---

## 3. Data model design

### 3.1 Country visa dataset (the core new asset)

Curated, version-controlled JSON, one file per country, loaded into a DB table. Keeping it as JSON-in-repo means edits are reviewable in git and the "last verified" date is explicit.

**Location:** `backend/app/data/visa_guides/{iso2}.json`
**Loader:** `backend/app/etl/import_visa_guides.py` → `country_visa_guides` table.

```jsonc
// backend/app/data/visa_guides/gb.json
{
  "country_code": "GB",
  "country_name": "United Kingdom",
  "region": "Europe",
  "english_speaking": true,            // official/business language is English
  "hires_internationally": true,
  "summary": "Skilled Worker visa is the main employer-sponsored route; employer must hold a sponsor licence.",
  "official_portal": "https://www.gov.uk/skilled-worker-visa",
  "sponsor_register_url": "https://www.gov.uk/government/publications/register-of-licensed-sponsors-workers",
  "last_verified": "2026-05-30",
  "currency": "GBP",
  "visa_types": [
    {
      "code": "skilled_worker",
      "name": "Skilled Worker Visa",
      "category": "employer_sponsored",
      "min_salary": { "amount": 41700, "currency": "GBP", "period": "year", "as_of": "2026" },
      "min_salary_notes": "Higher of general threshold or SOC going rate. Lower floors for new entrants (£33,400) and health/care (£25,000).",
      "english_requirement": "B1 (CEFR)",
      "processing_time": "3 weeks (outside UK)",
      "validity": "Up to 5 years, renewable; route to settlement (ILR) after 5 years",
      "cost": "Visa fee + Immigration Health Surcharge + Certificate of Sponsorship",
      "requirements": [
        "Job offer from a licensed sponsor (A-rated)",
        "Certificate of Sponsorship (CoS)",
        "Eligible occupation code",
        "Meet salary threshold / going rate",
        "English at B1"
      ],
      "good_for": ["software", "engineering", "healthcare", "data"],
      "pr_pathway": true
    }
    // ... Global Talent, Health & Care Worker, etc.
  ],
  "tips": [
    "Search the official Register of Licensed Sponsors before applying.",
    "Shortage / Immigration Salary List roles get a discount on the going rate."
  ],
  "sources": [
    { "label": "gov.uk Skilled Worker", "url": "https://www.gov.uk/skilled-worker-visa" }
  ]
}
```

**DB table** (`backend/app/db/schema.py`):

```python
class CountryVisaGuide(Base):
    __tablename__ = "country_visa_guides"
    country_code   = mapped_column(String(2), primary_key=True)   # ISO 3166-1 alpha-2
    country_name   = mapped_column(String(80), nullable=False)
    region         = mapped_column(String(40))
    english_speaking      = mapped_column(Boolean, default=False)
    hires_internationally = mapped_column(Boolean, default=True)
    official_portal       = mapped_column(String(300))
    sponsor_register_url  = mapped_column(String(300))
    summary        = mapped_column(Text)
    data_json      = mapped_column(JSON)     # full visa_types[] + tips + sources
    last_verified  = mapped_column(Date)
    updated_at     = mapped_column(DateTime, server_default=func.now())
```

### 3.2 Generalize the visa flags on jobs

The boolean columns (`visa_h1b`, `visa_opt`, `visa_stem_opt`, `h1b_verified`) are US-only. Keep them for backward compatibility but add a country-agnostic layer:

```python
# additive columns on jobs + master_jobs (non-breaking)
visa_country      = mapped_column(String(2))     # destination country of the role (ISO2)
visa_programs     = mapped_column(JSON)          # ["skilled_worker"] / ["h1b","opt"] etc.
sponsor_verified  = mapped_column(Boolean, default=False)  # generalization of h1b_verified
sponsor_source    = mapped_column(String(40))    # "uscis" | "uk_register" | "ind_nl" | ...
```

`visa_score` (0–100) and `no_sponsorship` stay as-is. The US flags become a *projection* of `visa_programs` for that country, so existing frontend keeps working during migration.

### 3.3 Generalize the sponsor table

Rename conceptually from "H-1B sponsors" to **"visa sponsors, by country."** Non-breaking path: keep `h1b_sponsors`, add a new `visa_sponsors` table that USCIS data also flows into.

```python
class VisaSponsor(Base):
    __tablename__ = "visa_sponsors"
    id            = mapped_column(String, primary_key=True)
    employer_name = mapped_column(String(300), index=True)
    country_code  = mapped_column(String(2), index=True)   # GB, US, NL...
    program       = mapped_column(String(40))              # skilled_worker / h1b / hsm ...
    source        = mapped_column(String(40))              # uk_register / uscis / ind_nl
    city          = mapped_column(String(120))
    region        = mapped_column(String(120))
    metrics_json  = mapped_column(JSON)   # approvals, route rating, etc. (source-specific)
    last_seen     = mapped_column(Date)
    __table_args__ = (Index("ix_visa_sponsor_country_name", "country_code", "employer_name"),)
```

USCIS importer writes `country_code="US", source="uscis"`. New importers (UK register, IND NL list, NZ accredited, etc.) write their own rows. Fuzzy matching (already using `rapidfuzz` in `everify`/contact code) is reused for verification.

---

## 4. Workstream A — Global classifier

`visa_classifier.py` becomes country-aware. Two-stage design:

1. **Country detection.** From the job's `location` / `country` field (schema already has `country`), resolve destination ISO2. Fall back to company HQ or posting domain TLD.
2. **Country-specific keyword pack.** Replace the single global keyword dict with a registry:

```python
# backend/app/services/visa_keywords/{iso2}.py  (or one dict keyed by country)
VISA_KEYWORDS = {
  "US": { "positive": {...h1b/opt/stem...}, "negative": {"us citizen only": -80, ...} },
  "GB": { "positive": {"skilled worker visa": 50, "tier 2": 45, "sponsorship licence": 50,
                       "certificate of sponsorship": 50, "right to work in the uk": 15},
          "negative": {"must have right to work in the uk": -40, "no visa sponsorship": -60} },
  "DE": { "positive": {"blue card": 50, "eu blue card": 50, "visa sponsorship": 45,
                       "relocation support": 25, "opportunity card": 30}, "negative": {...} },
  # ... per country
}
GLOBAL_POSITIVE = { "visa sponsorship": 45, "relocation": 20, "work permit": 25,
                    "international candidates": 25, "sponsorship available": 50 }
GLOBAL_NEGATIVE = { "no sponsorship": -60, "only local candidates": -50,
                    "must be authorized to work": -30 }
```

3. **Scoring** = country pack + global pack, then cross-reference the **right register** for that country (USCIS for US, UK register for GB, IND list for NL, ...). Output extends `VisaScore`:

```python
class VisaScore(BaseModel):
    score: int
    country_code: str | None = None
    matched_programs: list[str] = []     # ["skilled_worker"]
    sponsor_verified: bool = False
    sponsor_source: str | None = None
    confidence: str = "low"
    # legacy US fields kept as computed projections
    visa_h1b: bool = False; visa_opt: bool = False; visa_stem_opt: bool = False
```

**English-friendliness signal** (new requirement): a role is flagged "international/English-friendly" when `english_speaking` country **or** the posting language is English **and** visa_score is positive. Stored as `english_friendly: bool` on the job.

---

## 5. Workstream B — Global sponsor data pipeline

Mirror the existing USCIS importer pattern (`import_h1b_sponsors.py`, `h1b_sponsor_pipeline.py`) per country where an official register exists:

| Source | Importer (new) | Notes |
|---|---|---|
| USCIS H-1B Excel | *exists* → also write `visa_sponsors` US rows | reuse |
| UK Register of Licensed Sponsors (CSV, weekly) | `import_uk_sponsors.py` | 124k+ employers, public download |
| IND NL recognised sponsors | `import_nl_sponsors.py` | public list |
| NZ accredited employers | `import_nz_sponsors.py` | public |
| Ireland employment permits / Trusted Partner | `import_ie_sponsors.py` | public stats |

Where no register exists (UAE, Japan, Switzerland, Gulf) → no importer; rely on classifier + job-posting signals + the curated country guide. The `sponsor_verified` flag is simply `false` with `sponsor_source=null` in those countries, and the UI shows "Sponsorship indicated in posting (not independently verified)."

All importers conform to one interface so the scheduler treats them uniformly:

```python
def run(country_code: str) -> int:   # returns rows upserted into visa_sponsors
```

Scheduling: extend the existing ETL run manager / 6h scraper rather than inventing a new scheduler.

---

## 6. Workstream C — Country Visa Guide page (NEW)

### 6.1 Backend API

New router `backend/app/api/visa_guides.py`, mounted in `main.py` (`app.include_router(visa_guides_router, prefix="/api")`):

```
GET /api/visa-guides                      -> list (code, name, region, english_speaking, n_visa_types)
GET /api/visa-guides/{country_code}       -> full curated record + verified sponsor count
GET /api/visa-guides/search?q=&region=&english_only=true
```

### 6.2 Frontend page

Follows the existing lazy-route + dashboard-sidebar pattern exactly:

1. **New page:** `frontend/src/app/components/dashboard/VisaGuidePage.tsx`
   - Index view: searchable/filterable country grid (region filter, "English-speaking only" toggle, "verifiable sponsor list" badge).
   - Detail view: `VisaGuideDetailPage.tsx` — country header, visa-type cards (salary, processing time, requirements, PR pathway), "Verify on official portal →" button, count of known sponsors in our DB with a link into the (renamed) sponsor explorer.
2. **Route** in `frontend/src/app/routes.ts`:
   ```ts
   const VisaGuidePage = lazy(() => import("./components/dashboard/VisaGuidePage").then(m => ({default: m.VisaGuidePage})));
   const VisaGuideDetailPage = lazy(() => import("./components/dashboard/VisaGuidePage").then(m => ({default: m.VisaGuideDetailPage})));
   // children of /dashboard:
   { path: "visa-guide", Component: authedGuarded(VisaGuidePage) },
   { path: "visa-guide/:country", Component: authedGuarded(VisaGuideDetailPage) },
   ```
3. **Sidebar nav** in `frontend/src/app/pages/Dashboard.tsx` `NAV_ITEMS` — add under the existing "Visa Tracker" entry:
   ```ts
   { icon: BookOpen, label: "Visa Guide", to: "/dashboard/visa-guide" },
   ```
   (Rename "Visa Tracker" → "Sponsors" for clarity, since it's now multi-country.)
4. **API client** `frontend/src/app/lib/api.ts` — add `getVisaGuides()`, `getVisaGuide(code)`.

Styling reuses the existing dark theme tokens (`theme.css`, `GlowCard`, Motion transitions) — no new design system.

---

## 7. Workstream D — Improvements to the current system

Independent of globalization, fix what's brittle today:

- **Decouple US assumptions.** `JobsPage` "Visa-friendly" filter and `VisaBadges` currently key off US flags; switch to `visa_programs` + `visa_country` so the filter means "friendly *for the user's target country*."
- **User target-country preference.** `SettingsPage` already has "Current Visa Status"; add **"Target countries"** (multi-select) to `user` profile, and let job matching + the guide default to it.
- **Freshness guardrails.** Every guide record shows `last_verified`; add an admin view (extend `AdminPage`) listing guides whose `last_verified` is >180 days old, and a scheduled monthly reminder task.
- **Confidence honesty.** Anywhere we show a visa badge, show the source ("Verified: UK Register" vs "Indicated in posting") — avoids over-promising sponsorship, the #1 risk with this kind of product.
- **Dedup across countries.** Same multinational employer appears in multiple registers; key `visa_sponsors` on (country_code, normalized_name) and surface a merged company view.

---

## 8. Migration & rollout phases

| Phase | Deliverable | Breaking? |
|---|---|---|
| **0** | This plan reviewed & approved | — |
| **1** | DB migration: add `country_visa_guides`, `visa_sponsors`, additive job columns (`visa_country`, `visa_programs`, `sponsor_verified`, `sponsor_source`) | No (additive) |
| **2** | Curate + load Tier-1 (12 countries) JSON dataset; build `import_visa_guides.py` | No |
| **3** | `visa_guides` API router + frontend Visa Guide page + nav | No |
| **4** | Country-aware classifier (keyword packs); backfill `visa_country`/`visa_programs` on existing jobs | Behavior change — feature-flag it |
| **5** | UK + NL + NZ sponsor importers → `visa_sponsors`; generalize verification | No |
| **6** | Curate Tier-2 (13 countries); user target-country preference; admin freshness view | No |
| **7** | Rename "Visa Tracker" → "Sponsors" (multi-country); deprecate US-only code paths | UI change |

Each phase is shippable on its own. Phases 1–3 deliver the visible new page fast; 4–5 deepen accuracy.

---

## 9. Accuracy, legal & maintenance

- **Never assert eligibility.** The product presents *curated reference + official link*; it does not give immigration advice. Add a standing disclaimer on every guide page ("Verify current rules on the official portal; this is not legal advice").
- **Dated facts.** Every salary/threshold carries an `as_of` year (rules change yearly — confirmed for UK/DE/AU in 2026). Stale records (>180 days) flagged in admin.
- **Single source of truth = the JSON files in git.** Edits are reviewed; the loader is idempotent.
- **Sponsor registers refresh on their own cadence** (UK weekly, USCIS annual); each importer records `last_seen`.

---

## 10. New / changed files at a glance

**Backend**
```
backend/app/data/visa_guides/{us,ca,gb,ie,de,nl,au,nz,sg,ae,jp,pt,...}.json   NEW (curated)
backend/app/etl/import_visa_guides.py                                          NEW
backend/app/etl/import_uk_sponsors.py  (+ nl, nz, ie)                           NEW
backend/app/api/visa_guides.py                                                  NEW
backend/app/services/visa_classifier.py                                         CHANGED (country-aware)
backend/app/services/visa_keywords/                                             NEW (per-country packs)
backend/app/models/visa.py                                                      CHANGED (CountryVisaGuide, extended VisaScore)
backend/app/db/schema.py                                                        CHANGED (3 tables/cols)
backend/migrations/<new>_global_visa.py                                         NEW (alembic)
backend/app/main.py                                                             CHANGED (mount router)
```

**Frontend**
```
frontend/src/app/components/dashboard/VisaGuidePage.tsx        NEW (index + detail)
frontend/src/app/routes.ts                                     CHANGED (2 routes)
frontend/src/app/pages/Dashboard.tsx                           CHANGED (nav item)
frontend/src/app/lib/api.ts                                    CHANGED (2 calls)
frontend/src/app/components/dashboard/SettingsPage.tsx         CHANGED (target countries)
```

---

## 11. Open questions for you

1. **Verification depth** — for Phase 5, which sponsor registers matter most to your users first (UK and Netherlands are the easiest public CSVs after USCIS)?
2. **Curation labor** — I can draft all 25 country JSON records from official sources during implementation; do you want all fields (salary, processing time, cost) or a lean v1 (visa types + requirements + official link) to ship faster?
3. **"Visa Tracker" rename** — OK to relabel the existing page "Sponsors," or keep the name and just add "Visa Guide" alongside?

---

*This is a planning document. On approval, Phase 1 (migration) and Phase 2–3 (dataset + page) are the recommended first implementation slice.*
> 2026-05-31 update: the classifier/API/UI foundation is implemented. The next
> workstream is adding the country sponsor-registry importers and official/free
> source importers that feed full global volume.

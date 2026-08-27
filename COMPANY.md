# Company Context — PlaceUp Career

_Last updated: 2026-08-26. Refresh Cash, Priorities, Metrics and Team at least quarterly._
_Provenance: `[company]` = stated or taken from repo docs · `[benchmark]` = external market data · `[estimate]` = planning assumption, not observed._

## The business

- **What we sell** `[company]` — a job-search platform for international and visa-sponsorship-seeking candidates. Crawls first-party and official ATS endpoints, scores CV-to-JD fit deterministically, layers visa-sponsorship signals from official sponsor registries, tailors resumes with an LLM layer, and prepares applications behind a mandatory human review gate before submission.
- **To whom** `[company]` — international students and visa-dependent candidates. In the US alone ~1.18m international students, 240,000+ entering OPT annually, 336,000 H-1B registrations for 85,000 spots; ~45% of international graduates land jobs vs ~62% of domestic peers. India (30.8%) and China (22.6%) dominate the source mix. `[benchmark]`
- **How we make money** `[company]` — subscription. Free / Starter $9.99 / **Pro $24.99 (flagship)** / Elite $49.99, with ~33% off annual.
- **Stage** `[company]` — pre-launch / early. No observed revenue data yet.
- **Domain** `[company]` — placeupcareer.com
- **Countries targeted** `[company]` — 32 destination countries.
- **Headcount** `[company]` — one operator (Bala). This is the company's largest single risk.

## Right now

- **Priority 1** — prove the funnel: free-to-paid conversion at or above 3%.
- **Priority 2** — get the compounding organic engine live: programmatic SEO pages and the free Visa Sponsor Checker.
- **Priority 3** — close the P0 legal and compliance items before public launch.
- **Binding constraint** — operator time, then cash. Infrastructure is cheap and not the constraint.
- **90-day win condition** `[company]` — a working funnel, not profit.

## Customers and economics

- **Structural constraint** `[company]` — customers churn when they get hired. Short lifetimes make paid acquisition hard to recoup. This single fact drives the entire growth strategy.
- **Blended net ARPU** `[estimate]` — ~$16 / paying user / month after annual discounts and ~3% payment fees.
- **Free-to-paid conversion** `[estimate]` — 3% assumed (industry range 2–5%).
- **Average paid lifetime** `[estimate]` — ~5 months.
- **LTV** `[estimate]` — ~$80 gross per paying user.
- **CAC ceiling** `[estimate]` — under ~$27 per paying user for 3:1 LTV:CAC. Organic ~$5–20; paid ads ~$60–150, frequently above LTV.
- **Break-even paying users** `[estimate]` — ~35 (bootstrap) / ~95 (lean) / ~235 (growth) / ~485 (aggressive).
- **12-month target** `[estimate]` — lean-to-growth band: ~40,000–65,000 sign-ups, ~700–1,300 paying subscribers, ~$135k–$250k ARR run-rate, organic-led.
- **All of the above are planning assumptions, not observed data.** Replace each with real numbers the moment any exist.

## Money

- **Infrastructure cost** `[estimate]` — ~$250/month at launch (<2k users), ~$670 at ~10k, ~$2,240 at ~50k. Annualised ~$3k / ~$8k / ~$27k.
- **Other fixed** `[estimate]` — Stripe ~2.9% + $0.30 per charge, compliance ~$200/yr (LLC + registered agent), DMCA agent $6/3yrs, Termly subscription.
- **Marketing budget stance** `[company]` — start Bootstrap ($0–500/mo) to Lean ($500–2,000/mo). Only scale to Growth or Aggressive once organic CAC under ~$27 is demonstrated.
- **Cash position** — Unknown. **Fill this in — it is the single most limiting gap for the CFO and financial-risk agents.**
- **Funding status** — Unknown.
- **Spending authority** — single operator, no thresholds set.

## Technology

- **Production** `[company]` — Google Cloud + Firebase. Public API: Cloud Run `placeup-api` (project `steel-shine-492401-u6`). Internal app server: Cloud Run `placeup-app`. Jobs database: Cloud SQL Postgres `placeup-backend`. User data: Firestore (project `placeup-firebase-641222668282`). Secrets: Secret Manager. Scheduled work: Cloud Run Jobs + Cloud Scheduler. Apply queue: Cloud Tasks, one queue per ATS, paced per platform.
- **Browser automation** `[company]` — Playwright on Cloud Run Jobs (batch) and a Cloud Run service (interactive handoff), with a managed-browser fallback (Steel.dev / Browserbase) once concurrency exceeds Cloud Run.
- **Cross-cloud dependency** `[company]` — AWS SES inbound (MX on `mail.placeupcareer.com`) → S3 → Lambda → FastAPI webhook. Deliberate; chosen over Gmail restricted-scope OAuth.
- **Trust model** `[company]` — zero-trust split: the public web server verifies user JWT/session, then calls the internal app server only via `app.services.internal_client` with a Google-signed ID token plus a short-lived `X-Service-Token`. `ServiceOnlyGateMiddleware` refuses every non-health request without it. Key files: `backend/app/zero_trust.py`, `backend/app/middleware/security.py`, `backend/app/services/internal_client.py`. Required secrets: `DATABASE_URL`, `JWT_SECRET`, `SERVICE_TOKEN_SECRET`.
- **Stack** `[company]` — Python 3.12 / FastAPI / SQLAlchemy / Alembic backend; Vite → Nginx frontend; Redis (Upstash) caching. Local stack via Docker Compose, `make up`.
- **Design system** `[company]` — dark-mode-first with light variant, IL-SUD-Giardino palette, Plus Jakarta Sans and JetBrains Mono.
- **Not to be used** `[company]` — Supabase, for production infrastructure.
- **Hard product constraints** `[company]` — never bypass a platform's security controls, never solve CAPTCHAs (hand off to the user), and every application passes a non-optional human review before submission.

## Data supply chain

- **Sources** `[company]` — Greenhouse, Lever, Ashby, SmartRecruiters, Workday, Adzuna, RemoteOK, Remotive, Jobicy and other first-party or official ATS endpoints; visa-sponsor registries for the UK, US and Netherlands.
- **Provenance fields carried on every job** `[company]` — `source_name`, `source_url`, first seen, last seen, `extra_metadata`. These are the product's trust surface and its legal defence.
- **Quality controls** `[company]` — stale-job sweeper, dedup, last-seen tracking, "may have closed" labelling.
- **Known migration** `[company]` — planned shift away from republishing full job-description text toward licensed feeds plus links and short excerpts. This is a P0 compliance item with a procurement dependency.

## Risk and regulation

- **Regimes that apply** `[company]` — GDPR, UK GDPR, CCPA/CPRA, PIPEDA (global user base); CAN-SPAM / CASL / ePrivacy on alerts; California Automatic Renewal Law on subscriptions; ADA Title III and EAA (WCAG 2.1 AA); NYC LL144 and EU AI Act monitored (currently low — candidate-facing, not an employer decision tool; **reassess immediately if PlaceUp ever sells to employers**).
- **Sensitive data held** `[company]` — resume PII, work-authorisation and visa status, account credentials. The audience is visa-dependent and vulnerable; reliance on our signals is real.
- **The core compliance strategy** `[company]` — reduce liability by being *more* accurate, not less: show source and date on every data point, use calibrated language ("likely sponsors (heuristic)", never "sponsors"), make every signal verifiable by linking to the authoritative posting, expire and label stale data, and let users report inaccuracy.
- **Known single points of failure** — one operator; one cloud provider; ATS endpoints controlled by third parties; Stripe as sole payment processor; the operator's Google account as the effective master key.
- **History** `[company]` — a credential has previously been exposed in shared content and required rotation. Secret hygiene is a live concern, not a theoretical one.

## Treasury

- `[company]` The company runs a trading desk on **its own cash** to generate income. Not client or investor money — outside money would make the activity regulated in the US.
- `[company]` Desired mode: automated execution, with the agent producing strategy profiles, allocation profiles and investment theses.
- **Runway floor** — Not yet set. **Must be defined before any live capital.** See `company/treasury-mandate.md`.
- **Standing rule** — trading income is never budgeted revenue. Runway is runway.

## Decision rules for agents

- **Always escalate to the operator** — anything irreversible, anything committing money beyond routine infrastructure, anything touching the zero-trust boundary, any live-capital trading decision, and any suspected credential exposure.
- **You may assume** — pricing is settled; growth is organic-led; GCP is the platform; Supabase is out; the human review gate before application submission is non-negotiable.
- **Already decided, do not relitigate** — the pricing ladder, the zero-trust architecture split, the AWS SES inbound path, dark-mode-first design, and the no-CAPTCHA-bypass constraint.

## Gaps that most limit the agents

1. Cash position and runway — blocks meaningful CFO and treasury work.
2. Any observed funnel data (sign-ups, conversion, actual churn) — every economic figure above is currently a planning estimate.
3. Whether the P0 compliance items are closed or still open.

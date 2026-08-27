# Risk Register — PlaceUp Career

_Owner: COO agent. Reviewed monthly. Seeded 2026-08-26 from the pre-launch legal and compliance checklist and the operating model._

| # | Risk | Owner (role) | Likelihood | Impact | Early-warning signal | Mitigation | Next review |
|---|------|--------------|-----------|--------|----------------------|------------|-------------|
| 1 | Bus factor of one — a single operator holds product, infra, security and commercial | coo | H | H | Any period of unavailability; undocumented systems accumulating | Runbooks, documented recovery, tested access recovery | 2026-09-26 |
| 2 | Treasury drawdown consumes runway | financial-risk-manager | M | H | Trading capital exceeding the at-risk cap; approach to daily loss limit | Ring-fence with runway floor, hard limits at the order layer, tested kill switch | Before first live trade |
| 3 | Scraping/republishing full JD text — IP and takedown exposure (P0) | market-access-compliance-analyst | M | H | Takedown notice; source terms change | Shift to licensed feeds; links plus short excerpts only | Before public launch |
| 4 | Resume PII sent to third-party LLM without consent/DPA (P0) | market-access-compliance-analyst | M | H | Any LLM vendor without a signed DPA in use | Disclosure and consent, no-training/zero-retention, signed DPA | Before public launch |
| 5 | Data privacy obligations unmet — GDPR/UK GDPR/CCPA/PIPEDA (P0) | market-access-compliance-analyst | M | H | User data request that cannot be fulfilled | Privacy policy, export and delete, retention limits, transfer terms | Before public launch |
| 6 | Visa-sponsorship signal misrepresented to a visa-dependent user (P0) | market-access-compliance-analyst | M | H | Uncalibrated copy shipping; user complaint about reliance | Heuristic labelling, source and date shown, no guarantees, verifiable links | Continuous |
| 7 | Breach of resume PII | sr-security-engineer | L | H | Anomalous bulk access; Secret Manager access outside deploys | Zero-trust boundary, least privilege, secret rotation, tested restore | 2026-09-26 |
| 8 | Credential exposure in shared content (has occurred before) | security-engineer | M | H | Secret appearing in chat, logs, screenshots or docs | Blocking secret scanning, automated rotation | 2026-09-26 |
| 9 | ATS source concentration — a source family blocks or closes endpoints | supply-chain-logistics-manager | M | H | Coverage drop in a country; rising rate-limit rejections | Source diversity per country, licensed-feed fallback, coverage alerting | 2026-09-26 |
| 10 | Paid acquisition CAC exceeds LTV | cmo | M | M | CAC per paying user trending above ~$27 | Stay organic-led until CAC proven; capped test budgets with stop dates | Monthly |
| 11 | Churn shorter than the 5-month planning assumption | sr-financial-analyst | M | H | First observed cohort retention below plan | Annual plans, re-engagement, reposition for ongoing career use | On first cohort data |
| 12 | Operator Google account compromise — effective master key | security-engineer | L | H | Unexpected MFA prompt; new auth method added | Phishing-resistant MFA, monitored, recovery codes secured offline | 2026-09-26 |
| 13 | Stale or closed listings shown to users (P1) | supply-chain-logistics-manager | M | M | Rising user reports; sweeper defect rate | Stale sweeper, last-verified labelling, report-inaccuracy control | Monthly |
| 14 | Prompt injection via scraped job-description text into the LLM layer | appsec-engineer | M | M | Anomalous model output; unexpected tool or action attempts | Treat scraped text as hostile input; constrain model authority; no unreviewed privileged actions | 2026-09-26 |
| 15 | Single payment processor dependency (Stripe) | cfo | L | M | Dispute rate rising; account review notice | Monitor dispute rate; know the alternative processor path | Quarterly |

## Accepted risks

| Risk | Why accepted | Accepted by | Review date |
|------|--------------|-------------|-------------|
| AWS SES inbound as a deliberate cross-cloud dependency | Chosen over Gmail restricted-scope OAuth for documented reasons | Operator | 2026-11-26 |

## Closed risks

| Risk | How closed | Date |
|------|-----------|------|

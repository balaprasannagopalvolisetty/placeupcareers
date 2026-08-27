# Secret and Static-Analysis Sweep — 2026-08-26

Run by the PlaceUp agent team in the connected workspace. Every finding below was
triaged against the source, not taken from the scanner label.

## Commands run

```
detect-secrets scan backend/app scripts frontend/src     # v1.5.0
ruff check backend/app --statistics                      # v0.16.4
```

Toolchain installed to `~/.agentvenv` (pytest 9.1.1, ruff 0.16.4, bandit 1.9.4,
pip-audit, detect-secrets 1.5.0).

## Secret scan — 4 candidates, 3 files

| File:line | Type | Verdict |
|---|---|---|
| `backend/app/api/auth.py:41` | Secret Keyword | **Real, correctly gated — see below** |
| `backend/app/config.py:280` | Basic Auth Credentials | Not a leak — `CHANGE_ME` placeholder in the default DSN |
| `backend/app/config.py:365` | Secret Keyword | Not a leak — this is the guard that *rejects* the dev JWT default in production. Working as intended. |
| `backend/app/services/dice_scraper.py:49` | Base64 High Entropy | Third-party key, annotated as public and embedded in dice.com's own JS. Accept and baseline. |

**No leaked company credential was found in the scanned paths.**

## Finding 1 — demo account bypass rests on a single boolean (Medium)

`backend/app/api/auth.py` defines `DEMO_EMAIL = "demo@placeup.dev"` and
`DEMO_PASSWORD = "Password123!"`, and provides two paths that use them:

- line 227 — `GET /demo` returns the credentials and seeds the account
- line 241 — login accepts that email/password pair directly, bypassing normal auth

**Both are correctly guarded by `settings.is_production`.** The control works.

The risk is structural rather than present: a publicly known password on a seeded
account, where the only thing between it and the internet is one boolean being
derived correctly in every environment. A wrong `ENVIRONMENT` value on one Cloud Run
revision opens it.

Recommended defence in depth:

1. Compile the demo path out rather than branching on it, or additionally require an
   explicit `ALLOW_DEMO_LOGIN` flag that is absent from production configuration.
2. Add a test asserting that with production settings, `GET /demo` returns 404 and the
   demo credentials fail authentication. That test is what stops this regressing.
3. Log any attempted demo login in production as a security event.

Owner: `sr-security-engineer` / `appsec-engineer`.

## Finding 2 — lint baseline, 1,600+ issues (Low, but two categories matter)

`ruff check backend/app --statistics`, top categories:

| Count | Rule | Note |
|---|---|---|
| 652 | `UP045` non-pep604-annotation-optional | cosmetic, auto-fixable |
| 276 | `BLE001` blind-except | **worth attention** — bare excepts hide real failures |
| 179 | `EXE002` shebang-missing-executable-file | cosmetic |
| 107 | `I001` unsorted-imports | auto-fixable |
| 90 | `B008` function-call-in-default-argument | FastAPI `Depends()` — mostly false positives here |
| 56 | `DTZ003` call-datetime-utcnow | **worth attention** — naive UTC in a 32-country product |
| 28 + 9 | `S110`/`S112` try-except-pass / -continue | **worth attention** — silent swallowing in scraper paths |

The three flagged categories bear directly on a known risk: a scraper that fails
silently is indistinguishable from a source with no jobs. `BLE001`, `S110` and `S112`
in `backend/app/services/` and `backend/app/etl/` should be reviewed individually and
converted to logged, typed handling.

Recommend: adopt a ruff configuration that enforces the rules that matter, auto-fix the
cosmetic ones in a single isolated commit, and leave the rest as a tracked baseline.

## Not done

- `bandit` and `pip-audit` full runs — queued, not yet executed this session.
- Backend test suite — requires `backend/requirements.txt` installed into the agent
  virtualenv (`scripts/agent-workspace-setup.sh`). Docker is unavailable in this
  workspace, so `make test` cannot run at all.
- Anything in production — Google Cloud is unreachable from this workspace at the
  network layer.

## Next

1. Fix Finding 1 with the regression test.
2. Triage the ~313 silent-exception sites in scraper and ETL paths.
3. Run the setup script so the test suite becomes a real verification gate.

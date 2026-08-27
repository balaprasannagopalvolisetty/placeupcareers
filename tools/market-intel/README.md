# PlaceUp Market Intelligence

An unattended loop that watches the market for PlaceUp Career and keeps three questions
answered without anyone asking: **what are competitors doing, where do we need to be
better to stand out, and how should we market this.**

It runs on Ubuntu under systemd, spends tokens only on material that actually changed,
and reschedules itself automatically when Claude reports a usage limit.

## Install

```bash
git clone <your repo> ~/PlaceUp                 # if not already there
cp -r ~/PlaceUp/tools/market-intel ~/placeup-intel
cd ~/placeup-intel && ./install.sh
```

One human step, once: install and authenticate the Claude CLI.

```bash
curl -fsSL https://claude.ai/install.sh | bash
claude          # log in interactively, once
```

After that it is unattended. `install.sh` enables a systemd **user** timer and turns on
lingering so it keeps running when you are logged out.

## What it does, and when

| Pass | Cadence | Work |
|---|---|---|
| `watch` | daily | Fetch fast-tier pages, hash them, extract facts **only from pages that changed** |
| `analyze` | weekly | Compare what changed against the fact store; write a competitive analysis |
| `strategy` | monthly | Refresh positioning, product differentiation and marketing plays |

The timer fires every 30 minutes. **A run with nothing due exits in milliseconds and
spends zero tokens** — that is what makes a frequent timer safe, and it is what makes
resume-after-limit prompt rather than waiting for tomorrow.

Reports land in your repo at `company/intel/`:

- `LATEST-analysis.md` and dated competitive analyses
- `LATEST-strategy.md` and dated positioning + marketing plans

## How it stays cheap

Token discipline is structural, not a request in a prompt:

1. **Deterministic code does the bulk of the work.** Fetching, HTML stripping, price
   extraction, change detection and deduplication are plain Python. The model is never
   asked to do something `re` can do.
2. **Content hashing gates every model call.** An unchanged page costs zero tokens.
   In steady state most days find nothing and cost nothing.
3. **Model tiering.** Haiku extracts facts (the high-volume work); Sonnet only runs the
   weekly comparison and monthly strategy.
4. **Hard caps, enforced in code.** Per-document characters, documents per call, output
   tokens per run, output tokens per rolling 24 hours. A run that would breach a cap
   stops early and queues the rest instead of overrunning.
5. **Facts are stored, not re-derived.** SQLite keeps the knowledge base, and a fact
   identical to the last observation is not written — so the store records changes, not
   churn, and prompts stay small as coverage grows.

Tune all of it in `config/settings.yml`. Defaults: 8,000 output tokens per run,
40,000 per day.

## Auto-restart on limits

When the CLI reports a usage limit, `intel/claude.py` parses the reset time out of the
message (unix timestamp or a "resets at 5pm" clock time), falls back to a 90-minute
backoff if there is none, writes it to the store, and exits **75** — the conventional
soft-failure code. systemd treats 75 as success so the unit is not marked failed, the
timer keeps firing every 30 minutes, and each firing checks the hold time and returns
immediately at zero cost until the window reopens. Work resumes exactly where it
stopped, because progress is checkpointed per document rather than per run.

It respects the limit. It cannot and does not bypass it.

## Commands

```bash
.venv/bin/python -m intel.run status     # health, budget, hold state - free
.venv/bin/python -m intel.run watch      # force a fetch pass
.venv/bin/python -m intel.run analyze    # force an analysis
.venv/bin/python -m intel.run strategy   # force a strategy refresh
tail -f state/intel.log                  # what it has been doing
systemctl --user list-timers placeup-intel.timer
systemctl --user disable --now placeup-intel.timer   # stop it
```

## What to edit

`config/targets.yml` is the only file you normally touch — competitors, their URLs, the
community sources, and the discovery queries. Seeded with Jobright, Simplify, Teal and
Careerflow (the four named in your pricing benchmark), plus Interstride and MyVisaJobs,
plus the r/h1b, r/f1visa and r/internationalstudents feeds.

`prompts/` holds the three prompts. They are deliberately terse and forbid invented
facts — if a page does not support a claim, the model is told to omit it rather than
fill the gap.

## Honest limits

- **Some sites will block it.** Cloudflare and bot protection will return 403 on certain
  competitor pages. Those are recorded as errors with their status, not silently
  skipped, so you can see coverage rather than assume it.
- **It reads public pages only.** No accounts, no logins, no scraping behind auth.
- **It reports, it does not act.** Nothing publishes, emails, posts or spends. The
  strategy pass proposes marketing plays; a human runs them.
- **Facts decay.** Every stored fact carries its source URL and observation time. Treat
  anything old as a hypothesis.

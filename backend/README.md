# PlaceUp Career Backend

AI-powered career platform backend built with **Python FastAPI**.

## Features

| Feature | Description | Endpoints |
|---------|-------------|-----------|
| **Job Scraping** | JobSpy (LinkedIn, Indeed, Glassdoor, ZipRecruiter, Google) + Dice + USAJobs + 11 ATS providers (Greenhouse, Lever, Ashby, Workday, SmartRecruiters, Recruitee, Personio, Teamtailor, JazzHR, Rippling, BambooHR) | `GET /api/jobs`, `POST /api/jobs/scrape` |
| **H1B Sponsor Pipeline** | Curated catalog of 130+ active H1B sponsors → auto-routes each to its public ATS board, stamps every role as `h1b_verified=True` | Source `h1b_sponsor` in `ScrapeRequest`, or `python scripts/full_scrape.py` |
| **H1B Data** | USCIS CSV (2009→present) + h1bdata.info + myVisaJobs + flcdatacenter + h1bgrader + h1data leaderboards (best-effort fallbacks) | `GET /api/visa/h1b/{employer}`, `POST /api/visa/classify` |
| **ATS Scoring** | AI-powered resume analysis with keyword matching and structured scoring | `POST /api/resume/parse`, `POST /api/resume/score` |
| **Match Engine** | Hybrid TF-IDF + keyword + LLM scoring for resume-job compatibility | `POST /api/match/score`, `POST /api/match/batch` |

## One-shot full scrape

Run a single end-to-end scrape that hits every JobSpy portal + Dice + USAJobs +
all curated H1B-sponsor ATS boards, deduplicates across sources, and writes the
result to `data/exports/jobs_<timestamp>.csv` and `.xlsx`:

```bash
# Default: ~14 queries × all enabled portals × top-500 H1B sponsors
python scripts/full_scrape.py

# Smaller test (faster, fewer rows)
python scripts/full_scrape.py --max-per-source 30 --tiers T1 --queries "software engineer,data scientist"

# Only H1B sponsor pipeline (no portal scraping)
python scripts/full_scrape.py --no-jobspy --no-dice
```

The H1B sponsor catalog lives in `app/services/h1b_sponsor_boards.py` —
add new entries there as you find more company ATS boards.

## Quick Start

### 1. Setup Environment

```bash
cd backend
cp .env.example .env
# Edit .env with your API keys (GROQ_API_KEY is required for ATS scoring)
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Run the Server

```bash
uvicorn app.main:app --reload --port 8000
```

### 4. Open API Docs

Navigate to **http://localhost:8000/docs** for interactive Swagger UI.

## Project Structure

```
backend/
├── app/
│   ├── main.py              # FastAPI entry point
│   ├── config.py             # Environment config
│   ├── dependencies.py       # Dependency injection
│   ├── api/                  # API route modules
│   │   ├── health.py         # Health check
│   │   ├── jobs.py           # Job listing & scraping
│   │   ├── resume.py         # Resume parsing & ATS
│   │   ├── match.py          # Match scoring
│   │   └── visa.py           # H1B & visa data
│   ├── models/               # Pydantic schemas
│   │   ├── job.py            # Job data models
│   │   ├── resume.py         # Resume & ATS models
│   │   ├── match.py          # Match scoring models
│   │   └── visa.py           # Visa & H1B models
│   ├── services/             # Business logic
│   │   ├── job_scraper.py    # Multi-source scraping
│   │   ├── resume_parser.py  # PDF/DOCX extraction
│   │   ├── ats_scorer.py     # LLM-powered ATS scoring
│   │   ├── match_engine.py   # Hybrid matching
│   │   ├── visa_classifier.py# Visa keyword scoring
│   │   └── h1b_data.py       # H1B data aggregation
│   ├── db/                   # Database layer
│   │   ├── firebase.py       # Firestore (production)
│   │   └── local_db.py       # SQLite (development)
│   └── utils/                # Shared utilities
│       ├── deduplication.py  # Content hashing
│       └── text_processing.py# NLP utilities
├── data/                     # Local database & data files
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
└── .env.example
```

## API Keys Required

| Key | Required | Source |
|-----|----------|--------|
| `GROQ_API_KEY` | Yes (for ATS) | [console.groq.com](https://console.groq.com) |
| `RAPIDAPI_KEY` | Optional | RapidAPI LinkedIn Job Search |
| `USAJOBS_API_KEY` | Optional | [developer.usajobs.gov](https://developer.usajobs.gov) |
| `GREENHOUSE_BOARD_TOKENS` | Optional | Comma-separated public board IDs (same token as careers URL), e.g. `duolingo,airbnb` |
| `SCRAPE_MAX_CONCURRENCY` | Optional | Cap parallel scrapers (default `28`; raise carefully to avoid bans) |
| `FIREBASE_CREDENTIALS_PATH` | Production only | GCP Service Account |

### Scraping notes (honest limits)

Aggregators (**JobSpy**, **USAJobs**, **Greenhouse**) can return a lot of rows, but no single codebase can scrape “every careers site on the Internet” uniformly: HR sites use different ATS vendors (Lever, Ashby, Workday, BambooHR, bespoke pages), geo blocks, robots rules, CAPTCHAs, and unstable HTML. Structured feeds we support today:

- JobSpy aggregates the sites it exposes and now **pages with offsets** plus richer field capture (skills, logos, salaries when provided, ATS metadata blobs).
- **Greenhouse boards** ingest directly from Greenhouse JSON when you configure `GREENHOUSE_BOARD_TOKENS` (or send `greenhouse_board_tokens` in the scrape body).
- **Proxying:** set `PROXY_URL` if you see empty results regionally.

Tune volume via `/api/jobs/scrape` JSON (`results_per_source`, `jobspy_max_pages`, narrower `sources`, narrower `locations`, etc.).

## Docker

```bash
# Build and run
docker-compose up --build

# Or with Docker directly
docker build -t placeup-backend .
docker run -p 8000:8000 --env-file .env placeup-backend
```

## CSV / SQLite extras

SQLite stores non-column enrichment under `jobs.data_json`. New rows embed everything outside core SQL columns (`is_remote`, `skills`, ATS metadata, nested `extra_metadata`, …); exports surface these fields.

## Terminal Table Formatter

If you're getting raw JSON in terminal output, convert it to a neatly aligned table:

```bash
# From a JSON file
python scripts/json_to_table.py --file data/sample.json

# From command output / stdin
curl http://localhost:8000/api/jobs | python scripts/json_to_table.py

# Force a column order
curl http://localhost:8000/api/jobs | python scripts/json_to_table.py --columns id,title,company,location
```

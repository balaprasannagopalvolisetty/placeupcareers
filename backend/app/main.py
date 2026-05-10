"""
PlaceUp Career Backend — FastAPI Application Entry Point
"""
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timedelta

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings


logging.basicConfig(
    level=logging.DEBUG if settings.is_development else logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("placeup")

API_DESCRIPTION = "PlaceUp Career API: jobs, ATS scoring, H1B sponsorship, recruiter contacts."


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("PlaceUp Career Backend starting up...")
    logger.info(f"   Environment: {settings.app_env}")
    logger.info(f"   Database: {settings.database_backend}")

    if settings.database_backend == "sqlite":
        from app.db.local_db import SQLiteClient
        SQLiteClient()
        logger.info("SQLite database initialized")
    else:
        try:
            from app.db.firebase import get_firestore_db
            get_firestore_db()
            logger.info("Firestore database connected")
        except Exception as e:
            logger.warning(f"Firestore connection failed: {e} - falling back to SQLite")

    try:
        _seed_demo_user()
    except Exception as e:
        logger.warning(f"Demo seed skipped: {e}")

    try:
        from app.db.local_db import SQLiteClient
        from app.services.h1b_excel_importer import import_h1b_excel
        await import_h1b_excel(SQLiteClient(), force=False)
    except Exception as e:
        logger.warning(f"H1B Excel import skipped: {e}")

    try:
        _start_scheduler()
    except Exception as e:
        logger.warning(f"Scheduler not started: {e}")

    yield
    logger.info("PlaceUp Career Backend shutting down...")


def _seed_demo_user():
    if settings.is_production:
        return
    from app.db import user_store
    from app.security import hash_password

    email = "demo@placeup.dev"
    if user_store.get_user_by_email(email):
        logger.info(f"Demo user already present: {email}")
        return

    user = user_store.create_user(
        email=email,
        password_hash=hash_password("Password123!"),
        first_name="Demo",
        last_name="Candidate",
        visa_status="F1-OPT",
        experience_years="3-5 years",
    )
    user_store.update_user_profile(user["id"], {
        "phone": "+1 (555) 012-3456",
        "location": "San Francisco, CA",
        "current_role": "Senior Software Engineer",
        "summary": "Experienced full-stack engineer focused on growth-stage delivery.",
        "linkedin_url": "https://linkedin.com/in/demo-candidate",
        "github_url": "https://github.com/demo-candidate",
        "portfolio_url": "https://demo.placeup.dev",
    })
    user_store.update_preferences(user["id"], {
        "job_preferences": "Senior Frontend / Full Stack roles at mid-to-large tech companies.",
        "notification_new_jobs": True,
        "notification_daily_digest": True,
        "notification_ats_updates": True,
    })
    user_store.create_alert(user["id"], {
        "title": "Senior Frontend Engineer", "company": "Stripe",
        "location": "San Francisco, CA", "salary": "$180K+",
        "match": 96, "visa": "H-1B",
    })
    user_store.create_alert(user["id"], {
        "title": "Full Stack Developer", "company": "Vercel",
        "location": "Remote", "salary": "$160K+",
        "match": 92, "visa": "H-1B",
    })
    user_store.create_resume(user["id"], name="Demo_Candidate_Resume.pdf",
                             score=87, size_bytes=145000, active=True)
    logger.info(f"Seeded demo user: {email} (password: Password123!)")


def _start_scheduler():
    if not settings.is_development:
        return
    try:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        from app.services.job_scraper import run_scrape_cycle
        from app.services.job_exporter import export_jobs
        from app.models.job import ScrapeRequest
        from app.db.local_db import SQLiteClient

        async def background_scrape():
            try:
                db = SQLiteClient()
                existing_hashes = await db.get_existing_hashes()
                result, jobs = await run_scrape_cycle(
                    request=ScrapeRequest(),
                    existing_hashes=existing_hashes,
                )
                if jobs:
                    job_dicts = [job.model_dump(mode="json") for job in jobs]
                    stored = await db.upsert_jobs_batch(job_dicts)
                    logger.info(f"Background Scrape: Stored {stored} new jobs")
                    artifacts = export_jobs(job_dicts)
                    if artifacts:
                        logger.info(f"Background Scrape: Exported {artifacts}")
                try:
                    deactivated = await db.deactivate_old_jobs(
                        days_old=settings.job_inactive_after_days,
                    )
                    if deactivated:
                        logger.info(f"Background Scrape: Deactivated {deactivated} stale jobs")
                except Exception as e:
                    logger.warning(f"Stale-job sweep failed: {e}")
                if jobs:
                    try:
                        from app.services.contact_finder import bulk_enrich_jobs
                        results = await bulk_enrich_jobs(
                            jobs[:50], db=db,
                            max_per_job=3, concurrency=4,
                        )
                        contacts_added = sum(len(r.contacts) for r in results.values())
                        logger.info(f"Background Scrape: Persisted {contacts_added} contacts across {len(results)} jobs")
                    except Exception as e:
                        logger.warning(f"Contact enrichment skipped: {e}")
            except Exception as e:
                logger.error(f"Background Scrape Error: {e}")

        # Persist last-run timestamp so we don't re-scrape on every uvicorn
        # restart. Only kick an immediate run if the last scrape was longer
        # ago than the configured interval.
        from pathlib import Path as _Path
        marker_path = _Path("data") / ".last_scrape_at"
        next_run = datetime.now()
        try:
            if marker_path.exists():
                last_run = datetime.fromisoformat(marker_path.read_text().strip())
                age_hours = (datetime.now() - last_run).total_seconds() / 3600.0
                if age_hours < settings.scrape_interval_hours:
                    remaining = settings.scrape_interval_hours - age_hours
                    next_run = datetime.now() + timedelta(hours=remaining)
                    logger.info(
                        f"Last scrape was {age_hours:.1f}h ago; next run in {remaining:.1f}h"
                    )
        except Exception as e:
            logger.debug(f"Last-scrape marker unreadable: {e}")

        async def _wrapped_scrape():
            try:
                await background_scrape()
            finally:
                try:
                    marker_path.parent.mkdir(parents=True, exist_ok=True)
                    marker_path.write_text(datetime.now().isoformat())
                except Exception:
                    pass

        scheduler = AsyncIOScheduler()
        scheduler.add_job(
            _wrapped_scrape, "interval",
            hours=settings.scrape_interval_hours,
            id="job_scrape_cycle",
            name="Automated Job Scraping",
            next_run_time=next_run,
        )
        scheduler.start()
        logger.info(
            f"Scheduler configured (interval: {settings.scrape_interval_hours}h, next run: {next_run:%Y-%m-%d %H:%M})"
        )
    except ImportError:
        logger.debug("APScheduler not installed, skipping scheduler setup")


app = FastAPI(
    title="PlaceUp Career API",
    description=API_DESCRIPTION,
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# No-cache headers on every API response so users always see fresh jobs.
@app.middleware("http")
async def no_cache_for_api(request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response


from app.api.health import router as health_router
from app.api.jobs import router as jobs_router
from app.api.resume import router as resume_router
from app.api.match import router as match_router
from app.api.visa import router as visa_router
from app.api.contacts import router as contacts_router
from app.api.auth import router as auth_router
from app.api.user import router as user_router
from app.api.alerts import router as alerts_router
from app.api.analytics import router as analytics_router

app.include_router(health_router, prefix="/api")
app.include_router(jobs_router, prefix="/api")
app.include_router(resume_router, prefix="/api")
app.include_router(match_router, prefix="/api")
app.include_router(visa_router, prefix="/api")
app.include_router(contacts_router, prefix="/api")
app.include_router(auth_router, prefix="/api")
app.include_router(user_router, prefix="/api")
app.include_router(alerts_router, prefix="/api")
app.include_router(analytics_router, prefix="/api")


@app.get("/", tags=["Root"])
async def root():
    return {
        "name": "PlaceUp Career API",
        "version": "1.0.0",
        "status": "running",
        "docs": "/docs",
        "demo_credentials": "/api/auth/demo",
    }

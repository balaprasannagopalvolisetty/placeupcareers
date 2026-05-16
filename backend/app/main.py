"""
PlaceUp Career Backend — FastAPI Application Entry Point
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.middleware import RateLimitMiddleware, SecurityHeadersMiddleware


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
    logger.info(f"   Jobs database: {settings.database_backend}")
    logger.info(f"   User database: {settings.user_database_backend}")
    settings.validate_production()

    # --- Jobs database (Postgres / Cloud SQL) ---
    if settings.database_backend == "postgres":
        try:
            from app.db.postgres import PostgresClient
            PostgresClient()
            logger.info("PostgreSQL database configured")
        except Exception as e:
            logger.error(f"PostgreSQL configuration FAILED: {e}")
    else:
        logger.warning(f"Unsupported DATABASE_BACKEND={settings.database_backend!r}")

    # --- User database (Firestore) ---
    if settings.user_database_backend == "firestore":
        logger.info(
            "Firestore user store configured "
            f"(project={settings.user_firestore_project_id}, "
            f"database={settings.user_firestore_database})"
        )
    else:
        logger.warning(f"Unsupported USER_DATABASE_BACKEND={settings.user_database_backend!r}")

    # No in-process scheduler — Cloud Scheduler + Cloud Run Jobs handle
    # scraping, silver loading, and stale-job sweeps in production.

    yield
    logger.info("PlaceUp Career Backend shutting down...")


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
# Order matters: rate limiter runs first so abusive callers never reach
# the route handlers, then security headers are stamped on whatever
# response comes back (including 429s).
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RateLimitMiddleware)


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
    }

"""
PlaceUp Career Backend — FastAPI Application Entry Point
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.config import settings
from app.middleware import AuditLogMiddleware, RateLimitMiddleware, RequestSizeLimitMiddleware, RouteAccessMiddleware, SecurityHeadersMiddleware
from app.middleware.logging import (
    AccessLogMiddleware,
    RequestIdMiddleware,
    configure_json_logging,
)


# Plain text in development (easier to scan in your terminal),
# structured JSON in production so Cloud Logging can pivot on user_id /
# request_id / status / duration_ms — and so alert policies actually
# work on the access log.
if settings.is_development:
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
else:
    configure_json_logging("INFO")
logger = logging.getLogger("placeup")

# Sentry has to be initialised BEFORE FastAPI is constructed so the
# FastApiIntegration patches the right symbols. The init function is a
# safe no-op when SENTRY_DSN is unset.
try:
    from app.observability import init_observability
    init_observability()
except Exception as _exc:  # pragma: no cover - never block app boot on telemetry
    logger.warning("observability init failed: %s", _exc)

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
            if settings.is_production:
                raise
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


# Lock down OpenAPI docs in production. The schemas leak endpoint paths,
# request shapes, and (depending on how routes are annotated) sometimes
# example payloads — a free recon target for anyone scraping the API.
# Keep them enabled in dev / staging so engineers can poke at /docs.
_docs_url = "/docs" if not settings.is_production else None
_redoc_url = "/redoc" if not settings.is_production else None
_openapi_url = "/openapi.json" if not settings.is_production else None

app = FastAPI(
    title="PlaceUp Career API",
    description=API_DESCRIPTION,
    version="1.0.0",
    docs_url=_docs_url,
    redoc_url=_redoc_url,
    openapi_url=_openapi_url,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    # Enumerate instead of "*": wildcard methods/headers with credentialed
    # CORS is wider than the API needs and flags every security scanner.
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-API-Key", "X-Requested-With"],
)
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=[
        "placeupcareer.com",
        "www.placeupcareer.com",
        "placeup-api-rui2a74muq-ue.a.run.app",
        "*.run.app",
        "testserver",
    ],
)
# Middleware order matters. Starlette runs them in reverse-registration
# order, so the LAST add_middleware below is the outermost layer.
# Reading from request → handler:
#   RequestId     → tag the request with a correlation id first.
#   AccessLog     → measure duration / status (sees the final status).
#   RateLimit     → reject abusive callers before any real work.
#   RequestSize   → reject oversized bodies before they're parsed.
#   RouteAccess   → coarse auth gate.
#   AuditLog      → record sensitive-route access.
#   Security      → stamp hardened headers on whatever comes back.
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(AuditLogMiddleware)
app.add_middleware(RouteAccessMiddleware)
app.add_middleware(RequestSizeLimitMiddleware)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(AccessLogMiddleware)
app.add_middleware(RequestIdMiddleware)


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
from app.api.password_reset import router as password_reset_router
from app.api.billing import router as billing_router
from app.api.user import router as user_router
from app.api.alerts import router as alerts_router
from app.api.analytics import router as analytics_router
from app.api.payments import router as payments_router
from app.api.admin import router as admin_router

app.include_router(health_router, prefix="/api")
app.include_router(jobs_router, prefix="/api")
app.include_router(resume_router, prefix="/api")
app.include_router(match_router, prefix="/api")
app.include_router(visa_router, prefix="/api")
app.include_router(contacts_router, prefix="/api")
app.include_router(auth_router, prefix="/api")
app.include_router(password_reset_router, prefix="/api")
app.include_router(billing_router, prefix="/api")
app.include_router(user_router, prefix="/api")
app.include_router(alerts_router, prefix="/api")
app.include_router(analytics_router, prefix="/api")
app.include_router(payments_router, prefix="/api")
app.include_router(admin_router, prefix="/api")


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    logger.info("validation failed path=%s errors=%s", request.url.path, exc.errors())
    return JSONResponse(status_code=422, content={"detail": "Invalid request payload"})


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("unhandled error path=%s", request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


@app.get("/", tags=["Root"])
async def root():
    return {
        "name": "PlaceUp Career API",
        "version": "1.0.0",
        "status": "running",
        "docs": "/docs",
    }

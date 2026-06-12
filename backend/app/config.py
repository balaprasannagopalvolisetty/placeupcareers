"""
PlaceUp Career Backend — Configuration
Loads all settings from environment variables via Pydantic Settings.
"""

from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Optional


class Settings(BaseSettings):
    """Application configuration loaded from .env file."""

    # --- Server ---
    app_env: str = Field(default="production")
    app_port: int = Field(default=8080)
    frontend_url: str = Field(default="https://placeup-frontend-76tybrmgya-ue.a.run.app")

    # --- Auth (JWT + password hashing) ---
    jwt_secret: str = Field(
        default="dev-only-change-me-jwt-secret-key-32-chars-min",
        description="HS256 signing key for access tokens. Must be set in production.",
    )
    jwt_algorithm: str = Field(default="HS256")
    jwt_expires_minutes: int = Field(default=15)
    refresh_token_expires_days: int = Field(default=30)
    # Email OTP / MFA. Off by default so enabling it is a deliberate, tested
    # rollout (never silently locks users out). When True: signup requires an
    # emailed code before activation, and every login requires a fresh code.
    otp_mfa_enabled: bool = Field(default=False)
    otp_code_ttl_minutes: int = Field(default=10)
    internal_api_key: str = Field(
        default="",
        description="Optional shared secret for internal/admin-only API operations.",
    )
    admin_emails: str = Field(
        default="",
        description="Comma-separated emails allowed to access admin-only APIs.",
    )

    # --- OAuth2 / OIDC (Google) ---
    oidc_google_client_id: str = Field(default="")
    oidc_google_client_secret: str = Field(default="")
    oidc_google_redirect_uri: str = Field(default="")

    # --- LLM Provider ---
    groq_api_key: str = Field(default="")
    openai_api_key: str = Field(default="")
    llm_provider: str = Field(default="groq")
    llm_model: str = Field(default="llama-3.3-70b-versatile")

    # --- OpenRouter (unified LLM gateway used by ScrapeGraphAI discovery) ---
    # OpenRouter exposes an OpenAI-compatible API at https://openrouter.ai/api/v1,
    # so we point any "openai/..."-prefixed ScrapeGraphAI model at it via
    # base_url. Picking a cheap model keeps daily scrapes affordable —
    # claude-3.5-haiku and gemini-2.0-flash both extract well from job pages
    # at < $0.001 per scrape.
    openrouter_api_key: str = Field(default="", description="OpenRouter API key — primary LLM for scrapegraph discovery.")
    openrouter_model: str = Field(
        default="anthropic/claude-3.5-haiku",
        description="OpenRouter model slug (e.g. anthropic/claude-3.5-haiku, google/gemini-2.0-flash-001).",
    )
    openrouter_base_url: str = Field(
        default="https://openrouter.ai/api/v1",
        description="OpenAI-compatible endpoint for OpenRouter.",
    )
    openrouter_referer: str = Field(
        default="https://placeupcareer.com",
        description="HTTP-Referer header — OpenRouter uses it for app attribution.",
    )

    # --- ScrapeGraphAI discovery (separate from enrichment) ---
    scrapegraph_discovery_enabled: bool = Field(default=False)
    scrapegraph_discovery_max_urls: int = Field(default=30, ge=0, le=500, description="Hard cap on URLs scraped per run — protects spend.")
    scrapegraph_discovery_concurrency: int = Field(default=3, ge=1, le=10, description="Concurrent SmartScraperGraph runs.")
    scrapegraph_career_pages: str = Field(
        default="",
        description="Optional comma-separated extra career page URLs to scrape (beyond the curated list).",
    )
    scrapling_discovery_enabled: bool = Field(default=True)
    scrapling_discovery_max_targets: int = Field(default=1400, ge=0, le=5000)
    scrapling_discovery_concurrency: int = Field(default=6, ge=1, le=30)
    scrapling_h1b_excel_company_limit: int = Field(
        default=1000,
        ge=0,
        le=5000,
        description="Top H1B Excel employers to convert into Scrapling company/Google Jobs discovery targets.",
    )

    # --- Job Scraping APIs ---
    rapidapi_key: str = Field(default="")
    usajobs_api_key: str = Field(default="")
    usajobs_email: str = Field(default="")
    greenhouse_board_tokens: str = Field(default="")
    adzuna_app_id: str = Field(default="")
    adzuna_app_key: str = Field(default="")
    adzuna_countries: str = Field(
        default=(
            "us,gb,de,nl,fr,ca,au,it,es,pl,in,ie,nz,sg,pt,se,dk,no,ch,fi,"
            "be,at,qa,sa,lu,kr,tw,hk,cz"
        )
    )

    # --- Contact / Recruiter Enrichment APIs ---
    apollo_api_key: str = Field(default="", description="Apollo.io API key (free: 60 credits/mo)")
    hunter_api_key: str = Field(default="", description="Hunter.io API key (free: 25 searches/mo)")
    serpapi_key: str = Field(default="", description="SerpAPI key for Google X-ray ($50/mo for 5K)")
    google_api_key: str = Field(default="", description="Google API key (Programmable Search free fallback)")
    google_cse_id: str = Field(default="", description="Google Programmable Search Engine ID (cx)")
    finalscout_api_key: str = Field(default="", description="FinalScout API key")
    finalscout_api_keys: str = Field(default="", description="Comma-separated FinalScout keys for multi-key batch enrichment")

    # --- Stripe billing ---
    # Test mode: use sk_test_* keys + test price IDs.
    # Production: sk_live_* + the corresponding live prices.
    # Set up once in Stripe dashboard, then put the IDs into Secret Manager.
    stripe_api_key: str = Field(default="", description="Stripe secret API key (sk_test_… or sk_live_…)")
    stripe_webhook_secret: str = Field(default="", description="Stripe webhook signing secret (whsec_…)")
    stripe_price_basic: str = Field(default="", description="Stripe price ID for the $9.99/mo Basic plan")
    stripe_price_pro: str = Field(default="", description="Stripe price ID for the $15.99/mo Pro plan")
    stripe_price_elite: str = Field(default="", description="Stripe price ID for the $45/mo Elite plan")

    # --- Payments ---
    payment_basic_checkout_url: str = Field(default="", description="Hosted checkout URL for Basic plan")
    payment_pro_checkout_url: str = Field(default="", description="Hosted checkout URL for Pro plan")
    payment_elite_checkout_url: str = Field(default="", description="Hosted checkout URL for Elite plan")

    # --- Email Digest (optional SMTP; scheduled from Cloud Scheduler/Run) ---
    smtp_host: str = Field(default="")
    smtp_port: int = Field(default=587)
    smtp_user: str = Field(default="")
    smtp_password: str = Field(default="")
    email_from: str = Field(default="jobs@placeupcareer.com")

    # --- Database / Firebase / GCP ---
    database_backend: str = Field(default="postgres")
    database_url: str = Field(
        default="postgresql+psycopg://placeup:CHANGE_ME@/jobssilverdb?host=/cloudsql/steel-shine-492401-u6:us-east1:placeup-backend",
        description="SQLAlchemy URL used when DATABASE_BACKEND=postgres.",
    )
    db_pool_size: int = Field(default=5, description="SQLAlchemy connections kept open per instance.")
    db_max_overflow: int = Field(default=10, description="Extra burst connections per instance under load.")
    db_statement_timeout_ms: int = Field(
        default=0,
        description="Per-statement timeout in ms (0 = off). Set on the API service so user "
                    "queries fail fast into the stale-page cache instead of hanging while "
                    "the scraper has the database busy. Leave 0 on ETL jobs.",
    )
    firebase_credentials_path: str = Field(default="./service-account.json")
    gcp_project_id: Optional[str] = Field(default=None)
    user_database_backend: str = Field(
        default="firestore",
        description="User/profile store backend. Use firestore in production.",
    )
    user_firestore_project_id: Optional[str] = Field(
        default=None,
        description="Firebase/GCP project id for user/profile Firestore data.",
    )
    user_firestore_database: str = Field(
        default="(default)",
        description="Firestore database id for user/profile data.",
    )

    # --- Scraping Config ---
    scrape_interval_hours: int = Field(default=6)
    scrape_max_concurrency: int = Field(default=28, ge=4, le=200)
    scrape_source_timeout_seconds: int = Field(
        default=300,
        ge=30,
        le=1800,
        description="Per-source scrape task timeout so one blocked provider cannot stall a whole scheduled run.",
    )
    scrape_ziprecruiter_jobspy_enabled: bool = Field(
        default=False,
        description="ZipRecruiter blocks Cloud Run/anonymous JobSpy with Cloudflare 403; use Scrapling fallback unless a proxy is configured.",
    )
    scrape_glassdoor_jobspy_enabled: bool = Field(
        default=False,
        description="Glassdoor frequently rejects broad automated JobSpy searches; use Scrapling fallback unless a proxy is configured.",
    )
    job_inactive_after_days: int = Field(default=14, description="Mark active jobs as inactive after N days without re-scrape (2-week window, sweeper in app/workers/stale_jobs_sweeper.py)")
    job_retention_days: int = Field(default=30, ge=1, description="Hard-delete jobs not seen within this many days from cloud job tables.")
    proxy_url: Optional[str] = Field(default=None)
    scrapegraph_enabled: bool = Field(default=False)
    scrapegraph_max_enrich_per_run: int = Field(default=40, ge=0, le=500)
    scrapegraph_min_description_chars: int = Field(default=450, ge=50, le=5000)

    # --- Redis (optional) ---
    redis_url: Optional[str] = Field(default=None)

    @property
    def is_development(self) -> bool:
        return self.app_env == "development"

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def cors_origins(self) -> list[str]:
        origins = [origin.strip() for origin in self.frontend_url.split(",") if origin.strip()]
        origins.extend([
            "https://placeupcareer.com",
            "https://www.placeupcareer.com",
            "https://placeup-frontend-76tybrmgya-ue.a.run.app",
        ])
        return list(set(origins))

    def validate_production(self) -> None:
        if self.database_backend == "sqlite":
            raise RuntimeError(
                "DATABASE_BACKEND=sqlite is no longer supported. "
                "Use postgres (jobs) + firestore (users) for all environments."
            )
        if self.user_database_backend == "sqlite":
            raise RuntimeError(
                "USER_DATABASE_BACKEND=sqlite is no longer supported. "
                "Use firestore for user data in all environments."
            )
        if not self.is_production:
            return
        if not self.jwt_secret or self.jwt_secret == "dev-only-change-me-jwt-secret-key-32-chars-min":
            raise RuntimeError("JWT_SECRET must be set to a production secret.")
        if len(self.jwt_secret) < 32:
            raise RuntimeError("JWT_SECRET must be at least 32 characters.")
        # Auth-config consistency guard: if OTP/MFA is on, an email provider
        # MUST be configured or every signup/login would dead-end at the OTP
        # step. Failing here (at boot) makes Cloud Run reject the bad revision
        # and keep the previous healthy one serving — sign-in stays up even if
        # a deploy script or manual env change strips the email settings.
        if self.otp_mfa_enabled:
            import os
            has_email_provider = bool(
                os.getenv("EMAIL_PROVIDER", "").strip()
                or os.getenv("RESEND_API_KEY", "").strip()
                or os.getenv("SENDGRID_API_KEY", "").strip()
                or self.smtp_host.strip()
            )
            if not has_email_provider:
                raise RuntimeError(
                    "OTP_MFA_ENABLED=true but no email provider is configured "
                    "(EMAIL_PROVIDER / RESEND_API_KEY / SENDGRID_API_KEY / SMTP_HOST). "
                    "Either configure email or set OTP_MFA_ENABLED=false. "
                    "Refusing to start so the previous revision keeps serving sign-in."
                )

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
        "extra": "ignore",
    }


settings = Settings()

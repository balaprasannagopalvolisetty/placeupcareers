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
    internal_api_key: str = Field(
        default="",
        description="Optional shared secret for internal/admin-only API operations.",
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

    # --- Job Scraping APIs ---
    rapidapi_key: str = Field(default="")
    usajobs_api_key: str = Field(default="")
    usajobs_email: str = Field(default="")
    greenhouse_board_tokens: str = Field(default="")

    # --- Contact / Recruiter Enrichment APIs ---
    apollo_api_key: str = Field(default="", description="Apollo.io API key (free: 60 credits/mo)")
    hunter_api_key: str = Field(default="", description="Hunter.io API key (free: 25 searches/mo)")
    serpapi_key: str = Field(default="", description="SerpAPI key for Google X-ray ($50/mo for 5K)")
    google_api_key: str = Field(default="", description="Google API key (Programmable Search free fallback)")
    google_cse_id: str = Field(default="", description="Google Programmable Search Engine ID (cx)")
    finalscout_api_key: str = Field(default="", description="FinalScout API key")

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
    job_inactive_after_days: int = Field(default=12, description="Mark active jobs as inactive after N days without re-scrape")
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

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
        "extra": "ignore",
    }


settings = Settings()

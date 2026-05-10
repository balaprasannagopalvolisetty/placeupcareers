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
    app_env: str = Field(default="development")
    app_port: int = Field(default=8000)
    frontend_url: str = Field(default="http://localhost:5173")

    # --- Auth (JWT + password hashing) ---
    jwt_secret: str = Field(
        default="dev-only-change-me-jwt-secret-key-32-chars-min",
        description="HS256 signing key for access tokens. Must be set in production.",
    )
    jwt_algorithm: str = Field(default="HS256")
    jwt_expires_minutes: int = Field(default=60 * 24 * 7)  # 7 days

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

    # --- Database / Firebase / GCP ---
    database_backend: str = Field(default="sqlite")
    database_url: str = Field(
        default="postgresql+psycopg://placeup:placeup_dev@localhost:5432/placeup",
        description="SQLAlchemy URL used when DATABASE_BACKEND=postgres.",
    )
    firebase_credentials_path: str = Field(default="./service-account.json")
    gcp_project_id: Optional[str] = Field(default=None)

    # --- Scraping Config ---
    scrape_interval_hours: int = Field(default=8)
    scrape_max_concurrency: int = Field(default=28, ge=4, le=200)
    job_inactive_after_days: int = Field(default=12, description="Mark active jobs as inactive after N days without re-scrape")
    proxy_url: Optional[str] = Field(default=None)

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
        origins = [self.frontend_url]
        if self.is_development:
            origins.extend([
                "http://localhost:5173",
                "http://localhost:3000",
                "http://127.0.0.1:5173",
                "http://127.0.0.1:8000",
            ])
        return list(set(origins))

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
        "extra": "ignore",
    }


settings = Settings()

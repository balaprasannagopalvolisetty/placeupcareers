"""
PlaceUp Career — Health Check API
"""

from datetime import datetime
from fastapi import APIRouter

from app.config import settings

router = APIRouter(tags=["Health"])


@router.get("/health")
async def health_check():
    """Health check endpoint for monitoring and load balancers.

    Returns server status, version, environment, and uptime info.
    """
    return {
        "status": "healthy",
        "version": "1.0.0",
        "environment": settings.app_env,
        "timestamp": datetime.utcnow().isoformat(),
        "services": {
            "database": settings.database_backend,
            "llm_provider": settings.llm_provider,
            "llm_model": settings.llm_model,
        },
    }

"""PlaceUp Career - Health Check API."""

from datetime import datetime

from fastapi import APIRouter

router = APIRouter(tags=["Health"])


@router.get("/health")
async def health_check():
    """Minimal public health response for uptime checks."""
    return {
        "status": "ok",
        "timestamp": datetime.utcnow().isoformat(),
    }

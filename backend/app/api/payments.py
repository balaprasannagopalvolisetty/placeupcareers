"""Payment plan endpoints.

The API only returns hosted checkout links. Raw card data must go directly to
the payment processor, never through PlaceUp servers.
"""
from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel

from app.config import settings
from app.security import current_user_id

router = APIRouter(prefix="/payments", tags=["Payments"])


PLANS = {
    "basic": {
        "id": "basic",
        "name": "Basic",
        "price": 9.99,
        "interval": "month",
        "features": ["Job matching", "Resume ATS score", "Saved jobs"],
    },
    "pro": {
        "id": "pro",
        "name": "Pro",
        "price": 15.99,
        "interval": "month",
        "features": ["Everything in Basic", "Recruiter contacts", "Application tracking", "Priority job alerts"],
    },
    "elite": {
        "id": "elite",
        "name": "Elite",
        "price": 45.00,
        "interval": "month",
        "features": ["Everything in Pro", "Premium enrichment", "Visa sponsor insights", "Concierge support"],
    },
}


class CheckoutRequest(BaseModel):
    plan_id: str


def _checkout_url(plan_id: str) -> str:
    return {
        "basic": settings.payment_basic_checkout_url,
        "pro": settings.payment_pro_checkout_url,
        "elite": settings.payment_elite_checkout_url,
    }.get(plan_id, "")


@router.get("/plans")
async def list_plans():
    return {"plans": list(PLANS.values())}


@router.post("/checkout")
async def create_checkout_session(payload: CheckoutRequest = Body(...), user_id: str = Depends(current_user_id)):
    plan_id = payload.plan_id.strip().lower()
    if plan_id not in PLANS:
        raise HTTPException(status_code=400, detail="Unknown plan")
    url = _checkout_url(plan_id)
    if not url:
        raise HTTPException(
            status_code=503,
            detail="Hosted checkout is not configured for this plan yet.",
        )
    return {
        "plan": PLANS[plan_id],
        "checkout_url": url,
        "user_id": user_id,
        "processor": "hosted_checkout",
    }

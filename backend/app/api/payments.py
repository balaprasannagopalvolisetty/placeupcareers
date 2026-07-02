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
        "price": 0.00 if settings.free_access_enabled else 9.99,
        "interval": "preview" if settings.free_access_enabled else "month",
        "features": ["Job matching", "Resume ATS score", "Saved jobs"],
    },
    "pro": {
        "id": "pro",
        "name": "Pro",
        "price": 0.00 if settings.free_access_enabled else 15.99,
        "interval": "preview" if settings.free_access_enabled else "month",
        "features": ["Everything in Basic", "Recruiter contacts", "Application tracking", "Priority job alerts"],
    },
    "elite": {
        "id": "elite",
        "name": "Elite",
        "price": 0.00 if settings.free_access_enabled else 45.00,
        "interval": "preview" if settings.free_access_enabled else "month",
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
    return {
        "plans": list(PLANS.values()),
        "free_access_enabled": settings.free_access_enabled,
        "message": "Complete application access is currently free." if settings.free_access_enabled else "",
    }


@router.get("/checkout-link/{plan_id}")
async def public_checkout_link(plan_id: str):
    """Public hosted-checkout link for a plan.

    Used by the signup wizard, where payment happens BEFORE the account
    exists (so the authenticated /checkout endpoint can't be used yet). Only
    returns the static hosted link; no user data is involved.
    """
    plan_id = plan_id.strip().lower()
    if plan_id not in PLANS:
        raise HTTPException(status_code=400, detail="Unknown plan")
    if settings.free_access_enabled:
        return {
            "plan": PLANS[plan_id],
            "checkout_url": "",
            "configured": False,
            "processor": "free_access",
            "message": "Payments are temporarily disabled. Complete access is free right now.",
        }
    url = _checkout_url(plan_id)
    return {
        "plan": PLANS[plan_id],
        "checkout_url": url,
        "configured": bool(url),
        "processor": "hosted_checkout",
    }


@router.post("/checkout")
async def create_checkout_session(payload: CheckoutRequest = Body(...), user_id: str = Depends(current_user_id)):
    plan_id = payload.plan_id.strip().lower()
    if plan_id not in PLANS:
        raise HTTPException(status_code=400, detail="Unknown plan")
    if settings.free_access_enabled:
        return {
            "plan": PLANS[plan_id],
            "checkout_url": "",
            "user_id": user_id,
            "processor": "free_access",
            "message": "Payments are temporarily disabled. Complete access is free right now.",
        }
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

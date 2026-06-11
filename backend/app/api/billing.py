"""
Stripe billing endpoints.

Three subscription tiers (matching the product requirement):
    Basic   $9.99 / month   — basic features + 50 ATS scores / month
    Pro    $15.99 / month   — Pro features + unlimited ATS + email enrichment
    Elite     $45 / month   — Pro + admin tools + LinkedIn CSV bulk enrichment

Endpoints
---------
    GET  /api/billing/plans               — returns the public plan catalog
    POST /api/billing/checkout            — creates a Stripe Checkout session
    GET  /api/billing/portal              — opens the customer billing portal
    POST /api/billing/webhook             — Stripe webhook handler (signature-verified)
    GET  /api/billing/me                  — returns the user's current plan + status

Operational setup
-----------------
1. Create three products + recurring prices in Stripe (one-time):
       stripe products create --name "PlaceUp Basic"
       stripe prices create --product=<id> --unit-amount=999 --currency=usd \
           --recurring="interval=month"
   ...repeat for Pro ($1599) and Elite ($4500).

2. Put the resulting price IDs into env vars:
       STRIPE_PRICE_BASIC=price_xxx
       STRIPE_PRICE_PRO=price_xxx
       STRIPE_PRICE_ELITE=price_xxx
       STRIPE_API_KEY=sk_live_xxx (or sk_test_xxx for staging)
       STRIPE_WEBHOOK_SECRET=whsec_xxx

3. Point Stripe at `https://api.placeupcareer.com/api/billing/webhook` and
   subscribe to: checkout.session.completed, customer.subscription.updated,
   customer.subscription.deleted, invoice.payment_failed.

The Stripe SDK is a soft import — the module loads without it, so dev
machines without `pip install stripe` can still boot the API. Any actual
checkout call without the SDK 503s with a clear "Billing not configured"
message.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from pydantic import BaseModel

from app.config import settings
from app.db import user_store
from app.security import current_user_id

log = logging.getLogger(__name__)
router = APIRouter(prefix="/billing", tags=["Billing"])


# ─── Plan catalog (public) ────────────────────────────────────────────

class PlanFeature(BaseModel):
    label: str
    included: bool = True


class PlanCard(BaseModel):
    slug: str
    name: str
    price_cents: int
    currency: str = "usd"
    interval: str = "month"
    description: str
    features: list[PlanFeature]
    stripe_price_id: Optional[str] = None
    recommended: bool = False


def _price_id(env_var: str) -> Optional[str]:
    """Read a Stripe price id from env. Returns None when unset so the
    /plans endpoint can render the catalog even before Stripe is set up."""
    val = os.getenv(env_var, "").strip()
    return val or None


PLANS: list[PlanCard] = [
    PlanCard(
        slug="basic",
        name="Basic",
        price_cents=999,
        description="Daily job alerts + 50 ATS scores per month.",
        stripe_price_id=_price_id("STRIPE_PRICE_BASIC"),
        features=[
            PlanFeature(label="Daily job alerts"),
            PlanFeature(label="50 ATS match scores / month"),
            PlanFeature(label="Application tracker"),
            PlanFeature(label="Unlimited resume uploads", included=False),
            PlanFeature(label="Email enrichment (FinalScout)", included=False),
        ],
    ),
    PlanCard(
        slug="pro",
        name="Pro",
        price_cents=1599,
        recommended=True,
        description="Unlimited ATS scoring + recruiter email lookup.",
        stripe_price_id=_price_id("STRIPE_PRICE_PRO"),
        features=[
            PlanFeature(label="Everything in Basic"),
            PlanFeature(label="Unlimited ATS match scores"),
            PlanFeature(label="Unlimited resume uploads"),
            PlanFeature(label="Recruiter email lookup (FinalScout)"),
            PlanFeature(label="Priority support"),
        ],
    ),
    PlanCard(
        slug="elite",
        name="Elite",
        price_cents=4500,
        description="Everything in Pro + bulk LinkedIn CSV processing + early access.",
        stripe_price_id=_price_id("STRIPE_PRICE_ELITE"),
        features=[
            PlanFeature(label="Everything in Pro"),
            PlanFeature(label="LinkedIn CSV bulk enrichment"),
            PlanFeature(label="Custom job-alert rules"),
            PlanFeature(label="Dedicated success manager"),
            PlanFeature(label="Early access to new features"),
        ],
    ),
]


@router.get("/plans", response_model=list[PlanCard])
async def list_plans():
    """Public — used by /pricing and the upgrade-prompt modal."""
    return PLANS


@router.get("/me")
async def my_billing(user_id: str = Depends(current_user_id)):
    user = user_store.get_user_by_id(user_id) or {}
    return {
        "plan": user.get("plan") or "free",
        "stripe_customer_id": user.get("stripe_customer_id"),
        "stripe_subscription_id": user.get("stripe_subscription_id"),
        "subscription_status": user.get("subscription_status"),
        "current_period_end": user.get("current_period_end"),
        "cancel_at_period_end": bool(user.get("cancel_at_period_end")),
    }


# ─── Checkout + portal ────────────────────────────────────────────────

class CheckoutRequest(BaseModel):
    plan: str       # one of "basic", "pro", "elite"
    success_url: Optional[str] = None
    cancel_url: Optional[str] = None


def _stripe_or_503():
    """Import the Stripe SDK lazily; raise a 503 with a clear message
    when it isn't installed or the API key isn't configured."""
    api_key = os.getenv("STRIPE_API_KEY", "").strip() or getattr(settings, "stripe_api_key", "")
    if not api_key:
        raise HTTPException(status_code=503, detail="Billing not configured: STRIPE_API_KEY missing.")
    try:
        import stripe  # type: ignore
    except ImportError:
        raise HTTPException(
            status_code=503,
            detail="Billing SDK not installed. `pip install stripe` and redeploy.",
        )
    stripe.api_key = api_key
    return stripe


def _resolve_plan(plan_slug: str) -> PlanCard:
    for p in PLANS:
        if p.slug == plan_slug.lower():
            return p
    raise HTTPException(status_code=400, detail=f"Unknown plan: {plan_slug}")


def _frontend_base() -> str:
    return os.getenv("FRONTEND_URL", "https://placeupcareer.com").rstrip("/")


@router.post("/checkout")
async def create_checkout_session(
    payload: CheckoutRequest = Body(...),
    user_id: str = Depends(current_user_id),
):
    """Create a Stripe Checkout session for the chosen plan.

    Returns `{url}` — the frontend redirects the user there. On
    success Stripe sends the user to `success_url`; on cancel,
    `cancel_url`. The actual subscription record is created via the
    `customer.subscription.created` webhook (see below).
    """
    stripe = _stripe_or_503()
    plan = _resolve_plan(payload.plan)
    if not plan.stripe_price_id:
        raise HTTPException(
            status_code=503,
            detail=f"Plan {plan.slug} has no STRIPE_PRICE_{plan.slug.upper()} configured.",
        )

    user = user_store.get_user_by_id(user_id) or {}
    customer_id = user.get("stripe_customer_id")
    if not customer_id:
        customer = stripe.Customer.create(
            email=user.get("email"),
            metadata={"placeup_user_id": user_id},
        )
        customer_id = customer["id"]
        user_store.update_user_profile(user_id, {"stripe_customer_id": customer_id})

    base = _frontend_base()
    session = stripe.checkout.Session.create(
        mode="subscription",
        customer=customer_id,
        line_items=[{"price": plan.stripe_price_id, "quantity": 1}],
        success_url=(payload.success_url or f"{base}/dashboard/billing?status=success&session_id={{CHECKOUT_SESSION_ID}}"),
        cancel_url=(payload.cancel_url or f"{base}/dashboard/billing?status=canceled"),
        allow_promotion_codes=True,
        client_reference_id=user_id,
        metadata={"placeup_user_id": user_id, "placeup_plan": plan.slug},
    )
    return {"url": session.url, "session_id": session.id}


@router.get("/portal")
async def open_portal(user_id: str = Depends(current_user_id)):
    """Redirect URL to the Stripe-hosted customer portal — where the user
    manages payment method, cancels, downloads invoices."""
    stripe = _stripe_or_503()
    user = user_store.get_user_by_id(user_id) or {}
    customer_id = user.get("stripe_customer_id")
    if not customer_id:
        raise HTTPException(status_code=400, detail="No Stripe customer on file — sign up for a plan first.")
    session = stripe.billing_portal.Session.create(
        customer=customer_id,
        return_url=f"{_frontend_base()}/dashboard/billing",
    )
    return {"url": session.url}


# ─── Webhook ──────────────────────────────────────────────────────────

@router.post("/webhook")
async def stripe_webhook(request: Request):
    """Stripe → us. Signature-verified per the docs at
    https://stripe.com/docs/webhooks/signatures.

    Subscribed events (configured in Stripe dashboard):
      - checkout.session.completed       → activate plan
      - customer.subscription.updated    → reflect plan/status change
      - customer.subscription.deleted    → downgrade to free
      - invoice.payment_failed           → flag past_due (optionally email)
    """
    stripe = _stripe_or_503()
    secret = os.getenv("STRIPE_WEBHOOK_SECRET", "").strip() or getattr(settings, "stripe_webhook_secret", "")
    if not secret:
        raise HTTPException(status_code=503, detail="STRIPE_WEBHOOK_SECRET missing.")

    sig = request.headers.get("stripe-signature") or ""
    body = await request.body()
    try:
        event = stripe.Webhook.construct_event(body, sig, secret)
    except Exception as exc:
        log.warning("Stripe webhook signature failed: %s", exc)
        raise HTTPException(status_code=400, detail="Invalid signature")

    etype = event["type"]
    data = event["data"]["object"]
    user_id = (data.get("metadata") or {}).get("placeup_user_id")
    log.info("Stripe webhook: %s user=%s", etype, user_id)

    if etype == "checkout.session.completed":
        # Subscription was just created — pull the plan slug back from
        # the metadata we stamped at checkout time.
        plan = (data.get("metadata") or {}).get("placeup_plan") or "pro"
        sub_id = data.get("subscription")
        if user_id:
            user_store.update_user_profile(user_id, {
                "plan": plan,
                "stripe_subscription_id": sub_id,
                "subscription_status": "active",
            })
    elif etype == "customer.subscription.updated":
        # Sent on any change — plan switch, period renewal, cancel-at-period-end toggle.
        items = ((data.get("items") or {}).get("data") or [{}])
        price_id = (items[0].get("price") or {}).get("id") if items else None
        plan = _plan_from_price_id(price_id) or "pro"
        if user_id:
            user_store.update_user_profile(user_id, {
                "plan": plan,
                "stripe_subscription_id": data.get("id"),
                "subscription_status": data.get("status"),
                "current_period_end": data.get("current_period_end"),
                "cancel_at_period_end": bool(data.get("cancel_at_period_end")),
            })
    elif etype == "customer.subscription.deleted":
        if user_id:
            user_store.update_user_profile(user_id, {
                "plan": "free",
                "stripe_subscription_id": None,
                "subscription_status": "canceled",
            })
    elif etype == "invoice.payment_failed":
        if user_id:
            user_store.update_user_profile(user_id, {"subscription_status": "past_due"})

    return {"received": True}


def _plan_from_price_id(price_id: Optional[str]) -> Optional[str]:
    if not price_id:
        return None
    for p in PLANS:
        if p.stripe_price_id == price_id:
            return p.slug
    return None


# ─── Plan-gating helper (used by other routes) ───────────────────────

PLAN_RANK = {"free": 0, "basic": 1, "pro": 2, "elite": 3}


def user_plan_atleast(user_id: str, required: str) -> bool:
    """Return True if the user's current plan meets or exceeds the requirement.

    Use as a dependency in feature-gated routes:

        @router.post("/some-pro-feature", dependencies=[Depends(require_pro)])

    where `require_pro = lambda uid=Depends(current_user_id): _gate(uid, "pro")`.
    """
    user = user_store.get_user_by_id(user_id) or {}
    plan = (user.get("plan") or "free").lower()
    return PLAN_RANK.get(plan, 0) >= PLAN_RANK.get(required.lower(), 0)


def require_plan(min_plan: str):
    """FastAPI dependency factory. Raises 402 if the user is on a lower tier."""
    async def _dep(user_id: str = Depends(current_user_id)):
        if not user_plan_atleast(user_id, min_plan):
            raise HTTPException(
                status_code=402,
                detail=f"This feature requires the {min_plan.title()} plan or higher.",
            )
        return user_id
    return _dep

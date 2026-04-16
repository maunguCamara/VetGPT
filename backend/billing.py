"""
vetgpt/backend/billing.py

Stripe subscription management.

Routes:
  POST /api/billing/checkout         — create Stripe checkout session
  POST /api/billing/portal           — customer portal (manage subscription)
  POST /api/billing/webhook          — Stripe webhook handler
  GET  /api/billing/subscription     — get current subscription status

Tiers:
  free    → premium  : $9.99/month   (STRIPE_PRICE_PREMIUM_MONTHLY)
  free    → clinic   : $49.99/month  (STRIPE_PRICE_CLINIC_MONTHLY)

Setup:
  pip install stripe
  Set STRIPE_SECRET_KEY, STRIPE_WEBHOOK_SECRET, STRIPE_PRICE_PREMIUM_MONTHLY,
  STRIPE_PRICE_CLINIC_MONTHLY in .env
  stripe listen --forward-to localhost:8000/api/billing/webhook (dev)
"""

import os
from fastapi import APIRouter, Depends, HTTPException, Request, Header
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .auth import get_current_user
from .database import User, Subscription, SubscriptionTier, get_db
from .config import get_settings

settings  = get_settings()
billing_router = APIRouter(prefix="/api/billing", tags=["billing"])

TIER_PRICES = {
    "premium": os.getenv("STRIPE_PRICE_PREMIUM_MONTHLY", ""),
    "clinic":  os.getenv("STRIPE_PRICE_CLINIC_MONTHLY",  ""),
}

SUCCESS_URL = os.getenv("STRIPE_SUCCESS_URL", "vetgpt://billing/success")
CANCEL_URL  = os.getenv("STRIPE_CANCEL_URL",  "vetgpt://billing/cancel")


def get_stripe():
    """Lazy import stripe — only needed when billing routes are called."""
    try:
        import stripe
        stripe.api_key = os.getenv("STRIPE_SECRET_KEY", "")
        if not stripe.api_key:
            raise HTTPException(
                status_code=503,
                detail="Billing not configured. Set STRIPE_SECRET_KEY in .env"
            )
        return stripe
    except ImportError:
        raise HTTPException(
            status_code=503,
            detail="Stripe not installed. Run: pip install stripe"
        )


class CheckoutRequest(BaseModel):
    tier: str   # "premium" | "clinic"


# ─── Checkout session ─────────────────────────────────────────────────────────

@billing_router.post("/checkout")
async def create_checkout(
    body: CheckoutRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Create a Stripe Checkout session for upgrading to premium or clinic.
    Returns a checkout_url — redirect the user there.
    """
    if body.tier not in TIER_PRICES:
        raise HTTPException(status_code=422, detail=f"Invalid tier '{body.tier}'")

    price_id = TIER_PRICES[body.tier]
    if not price_id:
        raise HTTPException(
            status_code=503,
            detail=f"STRIPE_PRICE_{body.tier.upper()}_MONTHLY not set in .env"
        )

    stripe = get_stripe()

    # Get or create Stripe customer
    result = await db.execute(
        select(Subscription).where(Subscription.user_id == user.id)
    )
    existing_sub = result.scalar_one_or_none()

    customer_id = existing_sub.stripe_customer_id if existing_sub else None

    if not customer_id:
        customer = stripe.Customer.create(
            email=user.email,
            name=user.full_name,
            metadata={"user_id": user.id},
        )
        customer_id = customer.id

    session = stripe.checkout.Session.create(
        customer=customer_id,
        payment_method_types=["card"],
        line_items=[{"price": price_id, "quantity": 1}],
        mode="subscription",
        success_url=SUCCESS_URL + "?session_id={CHECKOUT_SESSION_ID}",
        cancel_url=CANCEL_URL,
        metadata={"user_id": user.id, "tier": body.tier},
    )

    return {"checkout_url": session.url, "session_id": session.id}


# ─── Customer portal ──────────────────────────────────────────────────────────

@billing_router.post("/portal")
async def customer_portal(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Create a Stripe Customer Portal session.
    User can manage/cancel their subscription there.
    """
    stripe = get_stripe()

    result = await db.execute(
        select(Subscription).where(Subscription.user_id == user.id)
    )
    sub = result.scalar_one_or_none()

    if not sub or not sub.stripe_customer_id:
        raise HTTPException(
            status_code=404,
            detail="No active subscription found for this account."
        )

    session = stripe.billing_portal.Session.create(
        customer=sub.stripe_customer_id,
        return_url=os.getenv("STRIPE_PORTAL_RETURN_URL", "vetgpt://profile"),
    )

    return {"portal_url": session.url}


# ─── Subscription status ──────────────────────────────────────────────────────

@billing_router.get("/subscription")
async def get_subscription(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get the current user's subscription status."""
    result = await db.execute(
        select(Subscription).where(Subscription.user_id == user.id)
    )
    sub = result.scalar_one_or_none()

    return {
        "tier":               user.tier.value,
        "has_subscription":   sub is not None,
        "status":             sub.status if sub else "none",
        "current_period_end": sub.current_period_end.isoformat() if sub and sub.current_period_end else None,
    }


# ─── Webhook ──────────────────────────────────────────────────────────────────

@billing_router.post("/webhook")
async def stripe_webhook(
    request: Request,
    stripe_signature: str = Header(None, alias="stripe-signature"),
    db: AsyncSession = Depends(get_db),
):
    """
    Stripe webhook endpoint.
    Handles: checkout.session.completed, customer.subscription.updated,
             customer.subscription.deleted
    """
    stripe          = get_stripe()
    webhook_secret  = os.getenv("STRIPE_WEBHOOK_SECRET", "")
    payload         = await request.body()

    try:
        event = stripe.Webhook.construct_event(
            payload, stripe_signature, webhook_secret
        )
    except stripe.error.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid webhook signature")

    event_type = event["type"]
    data       = event["data"]["object"]

    if event_type == "checkout.session.completed":
        await _handle_checkout_completed(db, stripe, data)

    elif event_type == "customer.subscription.updated":
        await _handle_subscription_updated(db, data)

    elif event_type == "customer.subscription.deleted":
        await _handle_subscription_deleted(db, data)

    return {"received": True}


async def _handle_checkout_completed(db, stripe, session):
    """Upgrade user tier after successful checkout."""
    user_id   = session["metadata"].get("user_id")
    tier_name = session["metadata"].get("tier", "premium")
    sub_id    = session.get("subscription")

    if not user_id:
        return

    result = await db.execute(select(User).where(User.id == user_id))
    user   = result.scalar_one_or_none()
    if not user:
        return

    # Upgrade tier
    user.tier = SubscriptionTier(tier_name)

    # Store subscription record
    stripe_sub = stripe.Subscription.retrieve(sub_id) if sub_id else None

    from datetime import datetime
    result2 = await db.execute(select(Subscription).where(Subscription.user_id == user_id))
    sub     = result2.scalar_one_or_none()

    if sub:
        sub.stripe_sub_id       = sub_id or ""
        sub.tier                = SubscriptionTier(tier_name)
        sub.status              = "active"
        sub.current_period_end  = (
            datetime.fromtimestamp(stripe_sub["current_period_end"])
            if stripe_sub else None
        )
    else:
        sub = Subscription(
            user_id            = user_id,
            stripe_customer_id = session.get("customer", ""),
            stripe_sub_id      = sub_id or "",
            tier               = SubscriptionTier(tier_name),
            status             = "active",
            current_period_end = (
                datetime.fromtimestamp(stripe_sub["current_period_end"])
                if stripe_sub else None
            ),
        )
        db.add(sub)

    await db.flush()


async def _handle_subscription_updated(db, stripe_sub):
    """Update subscription status on renewal or change."""
    from datetime import datetime
    result = await db.execute(
        select(Subscription).where(
            Subscription.stripe_sub_id == stripe_sub["id"]
        )
    )
    sub = result.scalar_one_or_none()
    if sub:
        sub.status             = stripe_sub["status"]
        sub.current_period_end = datetime.fromtimestamp(
            stripe_sub["current_period_end"]
        )
        await db.flush()


async def _handle_subscription_deleted(db, stripe_sub):
    """Downgrade user to free when subscription is cancelled."""
    result = await db.execute(
        select(Subscription).where(
            Subscription.stripe_sub_id == stripe_sub["id"]
        )
    )
    sub = result.scalar_one_or_none()
    if not sub:
        return

    sub.status = "cancelled"

    # Downgrade user
    user_result = await db.execute(
        select(User).where(User.id == sub.user_id)
    )
    user = user_result.scalar_one_or_none()
    if user:
        user.tier = SubscriptionTier.FREE

    await db.flush()

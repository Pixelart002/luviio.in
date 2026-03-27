"""
Payments Router
===============
Handles Stripe payment intents, confirmation, and webhooks.

Flow:
  1. POST /payments/create-intent  → Create Stripe PaymentIntent
  2. Frontend: stripe.confirmCardPayment()
  3. POST /payments/confirm         → Mark order as paid (verified via Stripe)
  4. POST /payments/webhook         → Stripe-side backup (optional)
"""
import json
import logging
from decimal import Decimal, ROUND_HALF_UP
from typing import Any
from uuid import UUID

import stripe
from fastapi import APIRouter, Depends, HTTPException, Request, Header, status
from pydantic import BaseModel

from app.config import settings
from app.dependencies import get_current_user
from app.supabase_client import get_admin_supabase
from app.utils.stock import restore_stock

stripe.api_key = settings.STRIPE_SECRET_KEY
logger = logging.getLogger(__name__)
router = APIRouter(prefix="/payments", tags=["Payments"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class PaymentIntentRequest(BaseModel):
    order_id: UUID


class PaymentIntentResponse(BaseModel):
    client_secret: str
    payment_intent_id: str


class ConfirmPaymentRequest(BaseModel):
    order_id: UUID
    payment_intent_id: str


# ── Helpers ───────────────────────────────────────────────────────────────────

def _amount_to_paise(amount: Any) -> int:
    """Convert INR amount (Decimal/float/str) to paise (smallest unit)."""
    return int(
        (Decimal(str(amount)) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    )


def _create_stripe_intent(amount_paise: int, order_id: str, user_id: str) -> stripe.PaymentIntent:
    return stripe.PaymentIntent.create(
        amount=amount_paise,
        currency="inr",
        metadata={"order_id": order_id, "user_id": user_id},
        automatic_payment_methods={"enabled": True},
        description=f"Luviio Order #{order_id[:8].upper()}",
    )


# ── POST /payments/create-intent ──────────────────────────────────────────────

@router.post("/create-intent", response_model=PaymentIntentResponse)
def create_payment_intent(
    payload: PaymentIntentRequest,
    current: dict[str, Any] = Depends(get_current_user),
) -> dict[str, str]:
    """
    Create (or reuse) a Stripe PaymentIntent for a pending order.
    Reuses existing intent unless it was cancelled or already succeeded.
    """
    sb = get_admin_supabase()
    user_id: str = current["profile"]["id"]
    order_id: str = str(payload.order_id)

    order_res = (
        sb.table("orders")
        .select("*")
        .eq("id", order_id)
        .eq("customer_id", user_id)
        .maybe_single()
        .execute()
    )
    if not order_res.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")

    order = order_res.data
    if order["status"] != "pending":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Order is not payable (status: {order['status']})"
        )

    amount_paise = _amount_to_paise(order["total_amount"])
    existing_pi_id: str | None = order.get("stripe_payment_intent")

    try:
        if existing_pi_id:
            intent = stripe.PaymentIntent.retrieve(existing_pi_id)
            if intent.status in ("canceled", "succeeded"):
                logger.info(
                    "PaymentIntent %s is %s — creating new one for order %s",
                    existing_pi_id, intent.status, order_id[:8]
                )
                intent = _create_stripe_intent(amount_paise, order_id, user_id)
                sb.table("orders").update({"stripe_payment_intent": intent.id}).eq("id", order_id).execute()
            else:
                logger.info("Reusing existing PaymentIntent %s for order %s", existing_pi_id, order_id[:8])
        else:
            intent = _create_stripe_intent(amount_paise, order_id, user_id)
            sb.table("orders").update({"stripe_payment_intent": intent.id}).eq("id", order_id).execute()
            logger.info("Created PaymentIntent %s for order %s", intent.id, order_id[:8])

    except stripe.error.StripeError as e:
        logger.error("Stripe error for order %s: %s", order_id[:8], e)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Payment provider error: {e.user_message}"
        )

    return {
        "client_secret": intent.client_secret,
        "payment_intent_id": intent.id,
    }


# ── POST /payments/confirm ────────────────────────────────────────────────────

@router.post("/confirm")
def confirm_payment(
    payload: ConfirmPaymentRequest,
    current: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """
    Called by frontend after stripe.confirmCardPayment() succeeds.
    Verifies the PaymentIntent with Stripe, then marks the order as paid.
    Idempotent — returns 200 if already paid.
    """
    sb = get_admin_supabase()
    user_id: str = current["profile"]["id"]
    order_id: str = str(payload.order_id)

    order_res = (
        sb.table("orders")
        .select("id, status, total_amount, stripe_payment_intent, customer_id")
        .eq("id", order_id)
        .eq("customer_id", user_id)
        .maybe_single()
        .execute()
    )
    if not order_res.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")

    order = order_res.data

    # Idempotency — already paid
    if order["status"] == "paid":
        logger.info("Order %s already paid — duplicate confirm call ignored", order["id"][:8])
        return {"status": "paid", "order_id": order["id"], "message": "Order already paid"}

    if order["status"] != "pending":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot confirm payment for order with status '{order['status']}'"
        )

    # Demo / test mode — no real Stripe key
    if not settings.STRIPE_SECRET_KEY or settings.STRIPE_SECRET_KEY.startswith("sk_test_REPLACE"):
        logger.warning("STRIPE_SECRET_KEY not configured — marking order %s paid in demo mode", order["id"][:8])
        sb.table("orders").update({"status": "paid"}).eq("id", order["id"]).execute()
        return {"status": "paid", "order_id": order["id"], "message": "Order confirmed (demo mode)"}

    # Verify PaymentIntent with Stripe
    try:
        intent = stripe.PaymentIntent.retrieve(payload.payment_intent_id)
    except stripe.error.StripeError as e:
        logger.error("Failed to retrieve PaymentIntent %s for order %s: %s", payload.payment_intent_id, order["id"][:8], e)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Could not verify payment: {e.user_message}"
        )

    if intent.status != "succeeded":
        logger.warning(
            "PaymentIntent %s status='%s' (expected 'succeeded') for order %s",
            payload.payment_intent_id, intent.status, order["id"][:8]
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Payment not completed. Stripe status: {intent.status}"
        )

    # Amount mismatch check (fraud prevention — 50 paise tolerance)
    order_amount = float(order["total_amount"])
    stripe_amount = intent.amount / 100
    if abs(stripe_amount - order_amount) > 0.50:
        logger.error(
            "Amount mismatch for order %s | expected=%.2f | stripe=%.2f",
            order["id"][:8], order_amount, stripe_amount
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Payment amount mismatch — please contact support"
        )

    # PaymentIntent ID must match what we stored
    stored_pi = order.get("stripe_payment_intent")
    if stored_pi and stored_pi != payload.payment_intent_id:
        logger.error(
            "PaymentIntent mismatch for order %s | stored=%s | received=%s",
            order["id"][:8], stored_pi, payload.payment_intent_id
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Payment intent mismatch"
        )

    # All checks passed — mark order paid
    sb.table("orders").update({"status": "paid"}).eq("id", order["id"]).execute()
    logger.info("Order %s marked PAID | pi=%s | amount=%.2f INR", order["id"][:8], payload.payment_intent_id, stripe_amount)

    # Save payment record (non-fatal if duplicate)
    try:
        sb.table("payments").insert({
            "order_id": order["id"],
            "stripe_payment_intent_id": payload.payment_intent_id,
            "amount": stripe_amount,
            "currency": intent.currency.upper(),
            "status": "completed",
            "payment_method": "stripe",
        }).execute()
    except Exception as e:
        logger.info("Payment record insert skipped (likely duplicate): %s", e)

    return {"status": "paid", "order_id": order["id"], "message": "Payment confirmed successfully"}


# ── POST /payments/webhook ────────────────────────────────────────────────────
# Configure in Stripe Dashboard → Developers → Webhooks
# URL: https://<your-app>.koyeb.app/api/v1/payments/webhook
# Events: payment_intent.succeeded, payment_intent.payment_failed, payment_intent.canceled

@router.post("/webhook")
async def stripe_webhook(
    request: Request,
    stripe_signature: str | None = Header(None, alias="stripe-signature"),
) -> dict[str, str]:
    """
    Stripe webhook handler. Serves as a reliable backup to /confirm.
    Verifies signature when STRIPE_WEBHOOK_SECRET is set.
    """
    body: bytes = await request.body()
    sb = get_admin_supabase()

    if settings.STRIPE_WEBHOOK_SECRET and stripe_signature:
        try:
            event = stripe.Webhook.construct_event(body, stripe_signature, settings.STRIPE_WEBHOOK_SECRET)
        except (stripe.error.SignatureVerificationError, ValueError) as e:
            logger.warning("Invalid webhook signature: %s", e)
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid webhook signature")
    else:
        # No secret configured — parse raw (development only, insecure)
        try:
            event = json.loads(body)
        except Exception:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid webhook payload")

    event_type: str = event["type"]
    pi_id: str = event["data"]["object"]["id"]
    logger.info("Webhook received | type=%s | pi=%s", event_type, pi_id)

    if event_type == "payment_intent.succeeded":
        order_res = (
            sb.table("orders")
            .select("id, status, total_amount")
            .eq("stripe_payment_intent", pi_id)
            .maybe_single()
            .execute()
        )
        if not order_res.data:
            logger.warning("No order found for PaymentIntent %s", pi_id)
            return {"message": "OK"}

        order = order_res.data

        if order["status"] == "paid":
            logger.info("Order %s already paid — webhook duplicate ignored", order["id"][:8])
            return {"message": "OK"}

        if order["status"] != "pending":
            logger.warning("Order %s has unexpected status '%s' on webhook", order["id"][:8], order["status"])
            return {"message": "OK"}

        sb.table("orders").update({"status": "paid"}).eq("id", order["id"]).execute()
        logger.info("Order %s marked PAID via webhook", order["id"][:8])

        try:
            stripe_amount = event["data"]["object"]["amount"] / 100
            sb.table("payments").insert({
                "order_id": order["id"],
                "stripe_payment_intent_id": pi_id,
                "amount": stripe_amount,
                "currency": event["data"]["object"]["currency"].upper(),
                "status": "completed",
                "payment_method": "stripe",
            }).execute()
        except Exception as e:
            logger.info("Webhook payment record skipped (likely duplicate): %s", e)

    elif event_type in ("payment_intent.payment_failed", "payment_intent.canceled"):
        order_res = (
            sb.table("orders")
            .select("id, status, order_items(*)")
            .eq("stripe_payment_intent", pi_id)
            .maybe_single()
            .execute()
        )
        if not order_res.data or order_res.data["status"] != "pending":
            return {"message": "OK"}

        order = order_res.data

        for item in order.get("order_items", []):
            if item.get("product_id"):
                restore_stock(sb, item["product_id"], item["quantity"], f"webhook_{event_type}")

        sb.table("orders").update({"status": "cancelled"}).eq("id", order["id"]).execute()
        logger.info("Order %s cancelled via webhook | event=%s", order["id"][:8], event_type)

    else:
        logger.debug("Unhandled webhook event type: %s", event_type)

    return {"message": "OK"}
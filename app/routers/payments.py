import logging
from typing import Any
from uuid import UUID

import stripe
from fastapi import APIRouter, Depends, HTTPException, status, Request, Header
from pydantic import BaseModel

from app.config import settings
from app.dependencies import get_current_user
from app.supabase_client import get_admin_supabase

stripe.api_key = settings.STRIPE_SECRET_KEY
logger = logging.getLogger(__name__)
router = APIRouter(prefix="/payments", tags=["Payments"])


# ── Request models ─────────────────────────────────────────────────────────────

class PaymentIntentRequest(BaseModel):
    order_id: UUID


class PaymentIntentResponse(BaseModel):
    client_secret: str
    payment_intent_id: str


# ── Create payment intent ─────────────────────────────────────────────────────

@router.post("/create-intent", response_model=PaymentIntentResponse)
def create_payment_intent(
    payload: PaymentIntentRequest,
    current: dict[str, Any] = Depends(get_current_user),
) -> dict[str, str]:
    sb = get_admin_supabase()
    order_res = (
        sb.table("orders")
        .select("*")
        .eq("id", str(payload.order_id))
        .eq("customer_id", current["profile"]["id"])
        .single()
        .execute()
    )
    if not order_res.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")

    order = order_res.data
    if order["status"] != "pending":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Order is no longer payable",
        )

    amount_cents: int = int(float(order["total_amount"]) * 100)

    try:
        existing_pi_id: str | None = order.get("stripe_payment_intent")

        if existing_pi_id:
            intent = stripe.PaymentIntent.retrieve(existing_pi_id)

            # SECURITY: Cancelled/succeeded intents reuse mat karo
            if intent.status in ("canceled", "succeeded"):
                logger.info(
                    "Existing intent %s is %s — creating new one for order %s",
                    existing_pi_id, intent.status, order["id"],
                )
                intent = stripe.PaymentIntent.create(
                    amount=amount_cents,
                    currency=order.get("currency", "usd").lower(),
                    metadata={
                        "order_id": order["id"],
                        "user_id": current["profile"]["id"],
                    },
                    automatic_payment_methods={"enabled": True},
                )
                sb.table("orders").update(
                    {"stripe_payment_intent": intent.id}
                ).eq("id", str(payload.order_id)).execute()
        else:
            intent = stripe.PaymentIntent.create(
                amount=amount_cents,
                currency=order.get("currency", "usd").lower(),
                metadata={
                    "order_id": order["id"],
                    "user_id": current["profile"]["id"],
                },
                automatic_payment_methods={"enabled": True},
            )
            sb.table("orders").update(
                {"stripe_payment_intent": intent.id}
            ).eq("id", str(payload.order_id)).execute()

    except stripe.error.StripeError as e:
        logger.error("Stripe error for order %s: %s", order["id"], e)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Payment provider error: {e.user_message}",
        )

    return {
        "client_secret": intent.client_secret,
        "payment_intent_id": intent.id,
    }


# ── Stripe webhook ────────────────────────────────────────────────────────────

@router.post("/webhook")
async def stripe_webhook(
    request: Request,
    stripe_signature: str | None = Header(None, alias="stripe-signature"),
) -> dict[str, str]:
    """
    SECURITY NOTE: payments table mein stripe_payment_intent_id pe UNIQUE constraint lagao:
    ALTER TABLE payments ADD CONSTRAINT payments_pi_unique UNIQUE (stripe_payment_intent_id);
    Ye replay attacks aur duplicate webhook inserts se protect karta hai.
    """
    body: bytes = await request.body()

    try:
        event = stripe.Webhook.construct_event(
            body, stripe_signature, settings.STRIPE_WEBHOOK_SECRET
        )
    except (stripe.error.SignatureVerificationError, ValueError) as e:
        logger.warning("Invalid webhook signature: %s", e)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid webhook signature",
        )

    event_type: str = event["type"]
    pi_id: str = event["data"]["object"]["id"]

    logger.info("Stripe webhook received: %s | pi_id: %s", event_type, pi_id)

    sb = get_admin_supabase()

    # ── Payment succeeded ─────────────────────────────────────────────────────
    if event_type == "payment_intent.succeeded":
        order_res = (
            sb.table("orders")
            .select("id, status, total_amount")
            .eq("stripe_payment_intent", pi_id)
            .single()
            .execute()
        )

        if not order_res.data:
            logger.warning("No order found for payment_intent: %s", pi_id)
            return {"message": "OK"}

        order = order_res.data

        if order["status"] != "pending":
            logger.info(
                "Webhook skipped — order %s already in status '%s'",
                order["id"], order["status"],
            )
            return {"message": "OK"}

        # Amount reconciliation — Stripe amount vs order total cross-check
        stripe_amount: float = event["data"]["object"]["amount"] / 100
        order_amount: float = float(order["total_amount"])
        if abs(stripe_amount - order_amount) > 0.01:
            logger.error(
                "Amount mismatch! order=%s stripe=%.2f order_total=%.2f",
                order["id"], stripe_amount, order_amount,
            )
            # Log karo aur alert karo — lekin order ko block mat karo (partial payment edge case)

        sb.table("orders").update({"status": "paid"}).eq("id", order["id"]).execute()

        # IDEMPOTENCY: unique constraint on stripe_payment_intent_id prevents duplicates
        try:
            sb.table("payments").insert({
                "order_id": order["id"],
                "stripe_payment_intent_id": pi_id,
                "amount": stripe_amount,
                "currency": event["data"]["object"]["currency"].upper(),
                "status": "completed",
                "payment_method": "stripe",
            }).execute()
        except Exception as e:
            # Unique constraint violation = duplicate webhook — safe to ignore
            logger.info("Payment insert skipped (likely duplicate webhook): %s", e)

        logger.info("Order %s marked as paid", order["id"])

    # ── Payment failed ────────────────────────────────────────────────────────
    elif event_type == "payment_intent.payment_failed":
        order_res = (
            sb.table("orders")
            .select("id, status, order_items(*)")
            .eq("stripe_payment_intent", pi_id)
            .single()
            .execute()
        )

        if not order_res.data:
            logger.warning("No order found for failed payment_intent: %s", pi_id)
            return {"message": "OK"}

        order = order_res.data

        if order["status"] != "pending":
            return {"message": "OK"}

        # Atomic stock restore — stale read race condition avoid karo
        for item in order.get("order_items", []):
            if item.get("product_id"):
                try:
                    sb.rpc("increment_stock", {
                        "p_id": item["product_id"],
                        "p_qty": item["quantity"],
                    }).execute()
                except Exception as e:
                    logger.error(
                        "Stock restore failed: order=%s product=%s err=%s",
                        order["id"], item["product_id"], e,
                    )

        sb.table("orders").update({"status": "cancelled"}).eq("id", order["id"]).execute()
        logger.info("Order %s cancelled after payment failure", order["id"])

    else:
        logger.debug("Unhandled webhook event type: %s", event_type)

    return {"message": "OK"}
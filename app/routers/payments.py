"""
Payments Router
================
Changes from original:
  All .single() → .maybe_single() — eliminates silent 500s when order row
  is missing during webhook processing.

No structural changes — payment flow is already well-designed.
"""
import logging
from decimal import Decimal, ROUND_HALF_UP
from typing import Any
from uuid import UUID

import stripe
from fastapi import APIRouter, Depends, HTTPException, status, Request, Header
from pydantic import BaseModel

from postgrest.exceptions import APIError as PostgrestError

from app.config import settings
from app.dependencies import get_current_user
from app.supabase_client import get_admin_supabase
from app.utils.stock import restore_stock

stripe.api_key = settings.STRIPE_SECRET_KEY
logger = logging.getLogger(__name__)
router = APIRouter(prefix="/payments", tags=["Payments"])


class PaymentIntentRequest(BaseModel):
    order_id: UUID


class PaymentIntentResponse(BaseModel):
    client_secret: str
    payment_intent_id: str


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
        .maybe_single()   # ← was .single()
        .execute()
    )
    if not order_res.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")

    order = order_res.data
    if order["status"] != "pending":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Order is no longer payable")

    amount_cents: int = int(
        (Decimal(str(order["total_amount"])) * 100).quantize(
            Decimal("1"), rounding=ROUND_HALF_UP
        )
    )

    try:
        existing_pi_id: str | None = order.get("stripe_payment_intent")

        if existing_pi_id:
            intent = stripe.PaymentIntent.retrieve(existing_pi_id)
            if intent.status in ("canceled", "succeeded"):
                intent = stripe.PaymentIntent.create(
                    amount=amount_cents,
                    currency=order.get("currency", "usd").lower(),
                    metadata={"order_id": order["id"], "user_id": current["profile"]["id"]},
                    automatic_payment_methods={"enabled": True},
                    idempotency_key=f"pi_create_{order['id']}_v2",
                )
                sb.table("orders").update({"stripe_payment_intent": intent.id}).eq("id", str(payload.order_id)).execute()
        else:
            intent = stripe.PaymentIntent.create(
                amount=amount_cents,
                currency=order.get("currency", "usd").lower(),
                metadata={"order_id": order["id"], "user_id": current["profile"]["id"]},
                automatic_payment_methods={"enabled": True},
                idempotency_key=f"pi_create_{order['id']}",
            )
            sb.table("orders").update({"stripe_payment_intent": intent.id}).eq("id", str(payload.order_id)).execute()

    except stripe.error.StripeError as e:
        logger.error("Stripe error for order %s: %s", order["id"], e)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Payment provider error: {e.user_message}")

    return {"client_secret": intent.client_secret, "payment_intent_id": intent.id}


@router.post("/webhook")
async def stripe_webhook(
    request: Request,
    stripe_signature: str | None = Header(None, alias="stripe-signature"),
) -> dict[str, str]:
    if not stripe_signature:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing stripe-signature header")

    body: bytes = await request.body()

    try:
        event = stripe.Webhook.construct_event(body, stripe_signature, settings.STRIPE_WEBHOOK_SECRET)
    except (stripe.error.SignatureVerificationError, ValueError) as e:
        logger.warning("Invalid webhook signature: %s", e)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid webhook signature")

    event_type: str = event["type"]
    pi_id: str      = event["data"]["object"]["id"]
    logger.info("Stripe webhook: %s | pi: %s", event_type, pi_id)

    sb = get_admin_supabase()

    if event_type == "payment_intent.succeeded":
        order_res = (
            sb.table("orders")
            .select("id, status, total_amount")
            .eq("stripe_payment_intent", pi_id)
            .maybe_single()   # ← was .single()
            .execute()
        )
        if not order_res.data:
            logger.warning("No order for pi: %s", pi_id)
            return {"message": "OK"}

        order = order_res.data
        if order["status"] != "pending":
            return {"message": "OK"}

        stripe_amount: float = event["data"]["object"]["amount"] / 100
        order_amount: float  = float(order["total_amount"])
        if abs(stripe_amount - order_amount) > 0.01:
            logger.error("Amount mismatch! order=%s stripe=%.2f db=%.2f", order["id"], stripe_amount, order_amount)

        sb.table("orders").update({"status": "paid"}).eq("id", order["id"]).execute()

        try:
            sb.table("payments").insert({
                "order_id":                 order["id"],
                "stripe_payment_intent_id": pi_id,
                "amount":                   stripe_amount,
                "currency":                 event["data"]["object"]["currency"].upper(),
                "status":                   "completed",
                "payment_method":           "stripe",
            }).execute()
        except Exception as e:
            logger.info("Payment insert skipped (likely duplicate webhook): %s", e)

        logger.info("Order %s marked paid", order["id"])

    elif event_type in ("payment_intent.payment_failed", "payment_intent.canceled"):
        order_res = (
            sb.table("orders")
            .select("id, status, order_items(*)")
            .eq("stripe_payment_intent", pi_id)
            .maybe_single()   # ← was .single()
            .execute()
        )
        if not order_res.data or order_res.data["status"] != "pending":
            return {"message": "OK"}

        order = order_res.data
        for item in order.get("order_items", []):
            if item.get("product_id"):
                restore_stock(sb, item["product_id"], item["quantity"], f"webhook_{event_type}:{order['id']}")

        sb.table("orders").update({"status": "cancelled"}).eq("id", order["id"]).execute()
        logger.info("Order %s cancelled — event: %s", order["id"], event_type)

    else:
        logger.debug("Unhandled webhook type: %s", event_type)

    return {"message": "OK"}
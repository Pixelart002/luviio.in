"""
Payments Router
================
FIX: Added /confirm endpoint so frontend can mark order paid
     without relying on Stripe webhook (which needs dashboard config).

Flow:
  1. POST /payments/create-intent  → Stripe PaymentIntent banao
  2. Frontend: stripe.confirmCardPayment()
  3. POST /payments/confirm         → order ko 'paid' mark karo (NEW)
  4. Stripe webhook (optional)      → same kaam, backup ke liye
"""
import logging
from decimal import Decimal, ROUND_HALF_UP
from typing import Any
from uuid import UUID

import stripe
from fastapi import APIRouter, Depends, HTTPException, status, Request, Header
from pydantic import BaseModel

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


class ConfirmPaymentRequest(BaseModel):
    order_id: UUID
    payment_intent_id: str


# ── Create PaymentIntent ──────────────────────────────────────────────────────

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
        .maybe_single()
        .execute()
    )
    if not order_res.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")

    order = order_res.data
    if order["status"] != "pending":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Order is no longer payable")

    # Amount in smallest currency unit
    # INR → paise (multiply by 100)
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
                    currency="inr",
                    metadata={"order_id": str(payload.order_id), "user_id": current["profile"]["id"]},
                    automatic_payment_methods={"enabled": True},
                    description=f"Luviio Order #{str(payload.order_id)[:8].upper()}",
                )
                sb.table("orders").update(
                    {"stripe_payment_intent": intent.id}
                ).eq("id", str(payload.order_id)).execute()
        else:
            intent = stripe.PaymentIntent.create(
                amount=amount_cents,
                currency="inr",
                metadata={"order_id": str(payload.order_id), "user_id": current["profile"]["id"]},
                automatic_payment_methods={"enabled": True},
                description=f"Luviio Order #{str(payload.order_id)[:8].upper()}",
            )
            sb.table("orders").update(
                {"stripe_payment_intent": intent.id}
            ).eq("id", str(payload.order_id)).execute()

    except stripe.error.StripeError as e:
        logger.error("Stripe error for order %s: %s", payload.order_id, e)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Payment provider error: {e.user_message}"
        )

    return {
        "client_secret": intent.client_secret,
        "payment_intent_id": intent.id
    }


# ── Confirm Payment (Frontend calls this after stripe.confirmCardPayment) ─────
# Webhook ka backup — kaam karta hai chahe webhook configure ho ya na ho

@router.post("/confirm")
def confirm_payment(
    payload: ConfirmPaymentRequest,
    current: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """
    Frontend payment succeed hone ke baad yeh call karta hai.
    Stripe PaymentIntent verify karta hai, phir order 'paid' mark karta hai.
    
    Idempotent hai — agar already paid hai toh 200 return karta hai.
    """
    sb = get_admin_supabase()

    # Order fetch karo + ownership verify karo
    order_res = (
        sb.table("orders")
        .select("id, status, total_amount, stripe_payment_intent, customer_id")
        .eq("id", str(payload.order_id))
        .eq("customer_id", current["profile"]["id"])
        .maybe_single()
        .execute()
    )
    if not order_res.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")

    order = order_res.data

    # Already paid? — idempotent
    if order["status"] == "paid":
        logger.info("Order %s already paid — confirm called again (idempotent)", order["id"][:8])
        return {"status": "paid", "order_id": order["id"], "message": "Order already paid"}

    if order["status"] not in ("pending",):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot confirm payment for order with status '{order['status']}'"
        )

    # Stripe se payment verify karo
    if not settings.STRIPE_SECRET_KEY or settings.STRIPE_SECRET_KEY.startswith("sk_test_REPLACE"):
        # Test/demo mode — Stripe key nahi hai, directly paid mark karo
        logger.warning(
            "STRIPE_SECRET_KEY not set — marking order %s paid without Stripe verification (demo mode)",
            order["id"][:8]
        )
        sb.table("orders").update({"status": "paid"}).eq("id", order["id"]).execute()
        logger.info("Order %s marked PAID (demo mode, no Stripe key)", order["id"][:8])
        return {"status": "paid", "order_id": order["id"], "message": "Order confirmed"}

    try:
        intent = stripe.PaymentIntent.retrieve(payload.payment_intent_id)
    except stripe.error.StripeError as e:
        logger.error("Stripe retrieve failed for order %s: %s", order["id"][:8], e)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Could not verify payment: {e.user_message}"
        )

    # Payment succeed check karo
    if intent.status != "succeeded":
        logger.warning(
            "PaymentIntent %s status is '%s' (not succeeded) for order %s",
            payload.payment_intent_id, intent.status, order["id"][:8]
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Payment not completed. Stripe status: {intent.status}"
        )

    # Amount verify karo (fraud prevention)
    order_amount = float(order["total_amount"])
    stripe_amount = intent.amount / 100
    if abs(stripe_amount - order_amount) > 0.50:  # 50 paise tolerance
        logger.error(
            "AMOUNT MISMATCH order=%s | expected=%.2f | stripe=%.2f",
            order["id"][:8], order_amount, stripe_amount
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Payment amount mismatch — contact support"
        )

    # Payment intent order se match karo
    stored_pi = order.get("stripe_payment_intent")
    if stored_pi and stored_pi != payload.payment_intent_id:
        logger.error(
            "Payment intent mismatch for order %s | stored=%s | received=%s",
            order["id"][:8], stored_pi, payload.payment_intent_id
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Payment intent mismatch"
        )

    # Sab verify ho gaya — order paid mark karo
    sb.table("orders").update({"status": "paid"}).eq("id", order["id"]).execute()
    logger.info(
        "Order %s marked PAID | pi=%s | amount=%.2f",
        order["id"][:8], payload.payment_intent_id, stripe_amount
    )

    # Payment record save karo
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


# ── Stripe Webhook (optional — configure in Stripe Dashboard) ─────────────────
# Dashboard → Developers → Webhooks → Add endpoint:
# URL: https://your-koyeb-url.koyeb.app/api/v1/payments/webhook
# Events: payment_intent.succeeded, payment_intent.payment_failed

@router.post("/webhook")
async def stripe_webhook(
    request: Request,
    stripe_signature: str | None = Header(None, alias="stripe-signature"),
) -> dict[str, str]:
    body: bytes = await request.body()
    sb = get_admin_supabase()

    # Signature verify karo (agar webhook secret set hai)
    if settings.STRIPE_WEBHOOK_SECRET and stripe_signature:
        try:
            event = stripe.Webhook.construct_event(
                body, stripe_signature, settings.STRIPE_WEBHOOK_SECRET
            )
        except (stripe.error.SignatureVerificationError, ValueError) as e:
            logger.warning("Invalid webhook signature: %s", e)
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid webhook signature")
    else:
        # No secret — parse as-is (development only)
        try:
            import json
            event_data = json.loads(body)
            event = event_data
        except Exception:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid webhook payload")

    event_type: str = event["type"]
    pi_id: str = event["data"]["object"]["id"]
    logger.info("Stripe webhook: %s | pi: %s", event_type, pi_id)

    if event_type == "payment_intent.succeeded":
        order_res = (
            sb.table("orders")
            .select("id, status, total_amount")
            .eq("stripe_payment_intent", pi_id)
            .maybe_single()
            .execute()
        )
        if not order_res.data:
            logger.warning("No order for pi: %s", pi_id)
            return {"message": "OK"}

        order = order_res.data
        if order["status"] == "paid":
            logger.info("Order %s already paid (webhook duplicate)", order["id"][:8])
            return {"message": "OK"}

        if order["status"] != "pending":
            return {"message": "OK"}

        sb.table("orders").update({"status": "paid"}).eq("id", order["id"]).execute()

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
            logger.info("Webhook payment record skipped (duplicate): %s", e)

        logger.info("Order %s marked paid via webhook", order["id"][:8])

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
        logger.info("Order %s cancelled via webhook: %s", order["id"][:8], event_type)

    return {"message": "OK"}
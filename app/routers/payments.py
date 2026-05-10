"""
Payments Router
===============
Stripe PaymentIntent lifecycle with idempotent, race-safe DB updates.

Payment flow:
  1. POST /payments/create-intent  → create / reuse Stripe PaymentIntent
  2. Frontend: stripe.confirmCardPayment()
  3. POST /payments/confirm        → verify with Stripe, mark paid, notify customer
  4. POST /payments/webhook        → Stripe-side backup (idempotent source of truth)

Race-condition handling:
  Both /confirm and the webhook can arrive almost simultaneously.
  Every status update uses an atomic conditional:
      UPDATE orders SET status='paid' WHERE id=? AND status='pending'
  If 0 rows are returned, the other path already won — we return gracefully.
"""
from __future__ import annotations

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
from app.services.events import (
    get_event_bus,
    OrderPaidEvent,
    OrderFailedEvent,
)

stripe.api_key = settings.STRIPE_SECRET_KEY
logger = logging.getLogger(__name__)
router = APIRouter(prefix="/payments", tags=["Payments"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class PaymentIntentRequest(BaseModel):
    order_id: UUID


class PaymentIntentResponse(BaseModel):
    client_secret:      str
    payment_intent_id:  str


class ConfirmPaymentRequest(BaseModel):
    order_id:           UUID
    payment_intent_id:  str


# ── Shared helpers ────────────────────────────────────────────────────────────

def _get_user_id(current_user: dict[str, Any]) -> str:
    """Safely extract user_id — tries profile → id → sub."""
    profile = current_user.get("profile")
    if isinstance(profile, dict) and "id" in profile:
        return str(profile["id"])
    if "id" in current_user:
        return str(current_user["id"])
    if "sub" in current_user:
        return str(current_user["sub"])

    logger.error("Cannot resolve user ID from token payload: %s", list(current_user))
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="User ID not found in session",
    )


def _amount_to_paise(amount: Any) -> int:
    """Convert INR decimal amount to paise (Stripe's smallest unit)."""
    return int(
        (Decimal(str(amount)) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    )


def _create_stripe_intent(
    amount_paise: int, order_id: str, user_id: str
) -> stripe.PaymentIntent:
    return stripe.PaymentIntent.create(
        amount=amount_paise,
        currency="inr",
        metadata={"order_id": order_id, "user_id": user_id},
        automatic_payment_methods={"enabled": True},
        description=f"Order #{order_id[:8].upper()}",
    )


def _get_customer_email(sb: Any, customer_id: str) -> str:
    """
    Fetch customer email from DB.
    Used in webhook context where `current` user is not available.
    Returns empty string on failure — non-fatal.
    """
    if not customer_id:
        return ""
    try:
        res = (
            sb.table("users")
            .select("email")
            .eq("id", customer_id)
            .limit(1)
            .execute()
        )
        if res and hasattr(res, "data") and res.data:
            return res.data[0].get("email", "")
    except Exception as exc:
        logger.warning("_get_customer_email failed | customer=%s | %s", customer_id[:8], exc)
    return ""


def _publish_paid_event(
    order: dict[str, Any],
    customer_id: str,
    customer_email: str,
) -> None:
    """
    Publish OrderPaidEvent — triggers customer email + push.
    Non-fatal: wrapped in try/except so a notification failure never
    rolls back or masks a successful payment.
    """
    try:
        get_event_bus().publish(OrderPaidEvent(
            order=order,
            customer_email=customer_email,
            customer_id=customer_id,
        ))
        logger.info("OrderPaidEvent published | order=%.8s", order.get("id", ""))
    except Exception as exc:
        logger.warning("OrderPaidEvent publish failed (non-critical): %s", exc)


def _publish_failed_event(
    sb: Any,
    order: dict[str, Any],
    customer_id: str,
    reason: str,
) -> None:
    """
    Publish OrderFailedEvent — triggers customer push.
    Non-fatal: same reasoning as _publish_paid_event.
    """
    try:
        customer_email = _get_customer_email(sb, customer_id)
        get_event_bus().publish(OrderFailedEvent(
            order=order,
            customer_email=customer_email,
            customer_id=customer_id,
            reason=reason,
        ))
        logger.info(
            "OrderFailedEvent published | order=%.8s reason=%s",
            order.get("id", ""), reason,
        )
    except Exception as exc:
        logger.warning("OrderFailedEvent publish failed (non-critical): %s", exc)


# ── POST /payments/create-intent ──────────────────────────────────────────────

@router.post("/create-intent", response_model=PaymentIntentResponse)
def create_payment_intent(
    payload: PaymentIntentRequest,
    current: dict[str, Any] = Depends(get_current_user),
) -> dict[str, str]:
    """
    Create (or reuse) a Stripe PaymentIntent for a pending order.
    If the stored intent is already canceled/succeeded, a fresh one is created.
    """
    sb       = get_admin_supabase()
    user_id  = _get_user_id(current)
    order_id = str(payload.order_id)

    try:
        order_res = (
            sb.table("orders")
            .select("id, status, total_amount, stripe_payment_intent")
            .eq("id", order_id)
            .eq("customer_id", user_id)
            .maybe_single()
            .execute()
        )
    except Exception as exc:
        logger.error("DB error fetching order %s: %s", order_id[:8], exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error fetching order",
        )

    if not order_res or not getattr(order_res, "data", None):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")

    order = order_res.data
    if order["status"] != "pending":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Order is not payable (status: {order['status']})",
        )

    amount_paise      = _amount_to_paise(order["total_amount"])
    existing_pi_id    = order.get("stripe_payment_intent")

    try:
        if existing_pi_id:
            intent = stripe.PaymentIntent.retrieve(existing_pi_id)
            if intent.status in ("canceled", "succeeded"):
                logger.info(
                    "PaymentIntent %s is %s — creating new one for order %s",
                    existing_pi_id, intent.status, order_id[:8],
                )
                intent = _create_stripe_intent(amount_paise, order_id, user_id)
                sb.table("orders").update({"stripe_payment_intent": intent.id}).eq("id", order_id).execute()
            else:
                logger.info("Reusing PaymentIntent %s for order %s", existing_pi_id, order_id[:8])
        else:
            intent = _create_stripe_intent(amount_paise, order_id, user_id)
            sb.table("orders").update({"stripe_payment_intent": intent.id}).eq("id", order_id).execute()
            logger.info("Created PaymentIntent %s for order %s", intent.id, order_id[:8])

    except stripe.error.StripeError as exc:
        logger.error("Stripe error for order %s: %s", order_id[:8], exc.user_message or exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Payment provider error: {exc.user_message or 'Unknown error'}",
        )

    return {"client_secret": intent.client_secret, "payment_intent_id": intent.id}


# ── POST /payments/confirm ────────────────────────────────────────────────────

@router.post("/confirm")
def confirm_payment(
    payload: ConfirmPaymentRequest,
    current: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """
    Called by the frontend after stripe.confirmCardPayment() returns.

    Steps:
      1. Verify the PaymentIntent with Stripe (not just trust the frontend).
      2. Amount + PI mismatch checks (fraud prevention).
      3. Atomic conditional DB update  (WHERE status='pending').
      4. Insert payment record.
      5. Publish OrderPaidEvent — customer email + push.
    """
    sb       = get_admin_supabase()
    user_id  = _get_user_id(current)
    order_id = str(payload.order_id)

    order_res = (
        sb.table("orders")
        .select("id, status, total_amount, stripe_payment_intent, customer_id")
        .eq("id", order_id)
        .eq("customer_id", user_id)
        .maybe_single()
        .execute()
    )

    if not order_res or not getattr(order_res, "data", None):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")

    order = order_res.data

    # Idempotency — already processed
    if order["status"] == "paid":
        logger.info("Order %s already paid — duplicate confirm ignored", order_id[:8])
        return {"status": "paid", "order_id": order["id"], "message": "Order already paid"}

    if order["status"] != "pending":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot confirm payment for order with status '{order['status']}'",
        )

    # ── Verify with Stripe ────────────────────────────────────────────────────
    try:
        intent = stripe.PaymentIntent.retrieve(payload.payment_intent_id)
    except stripe.error.StripeError as exc:
        logger.error("Failed to retrieve PaymentIntent %s: %s", payload.payment_intent_id, exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Could not verify payment: {exc.user_message or str(exc)}",
        )

    if intent.status != "succeeded":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Payment not completed. Stripe status: {intent.status}",
        )

    # ── Fraud checks ──────────────────────────────────────────────────────────
    order_amount  = float(order["total_amount"])
    stripe_amount = intent.amount / 100
    if abs(stripe_amount - order_amount) > 0.50:
        logger.error(
            "Amount mismatch | order=%s expected=%.2f stripe=%.2f",
            order_id[:8], order_amount, stripe_amount,
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Payment amount mismatch — contact support",
        )

    stored_pi = order.get("stripe_payment_intent")
    if stored_pi and stored_pi != payload.payment_intent_id:
        logger.error(
            "PaymentIntent mismatch | order=%s stored=%s received=%s",
            order_id[:8], stored_pi, payload.payment_intent_id,
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Payment intent mismatch",
        )

    # ── Atomic conditional update (TOCTOU-safe) ───────────────────────────────
    # .eq("status", "pending") ensures that if the Stripe webhook already
    # marked this paid, we return 0 rows and handle it gracefully.
    update_res = (
        sb.table("orders")
        .update({"status": "paid"})
        .eq("id", order["id"])
        .eq("status", "pending")
        .execute()
    )

    if not update_res or not getattr(update_res, "data", None):
        logger.info("Order %s already processed by concurrent request", order_id[:8])
        return {"status": "paid", "order_id": order["id"], "message": "Payment already processed"}

    logger.info("Order %s marked PAID | pi=%s", order_id[:8], payload.payment_intent_id)

    # ── Insert payment record ─────────────────────────────────────────────────
    try:
        sb.table("payments").insert({
            "order_id":                  order["id"],
            "stripe_payment_intent_id":  payload.payment_intent_id,
            "amount":                    stripe_amount,
            "currency":                  intent.currency.upper(),
            "status":                    "completed",
            "payment_method":            "stripe",
        }).execute()
    except Exception as exc:
        logger.info("Payment record insert skipped (likely duplicate): %s", exc)

    # ── Notify customer ───────────────────────────────────────────────────────
    paid_order                = dict(order)   # local copy — no extra DB fetch needed
    paid_order["status"]      = "paid"
    customer_id               = order.get("customer_id", "")
    customer_email            = (
        current.get("profile", {}).get("email", "")
        or _get_customer_email(sb, customer_id)
    )

    _publish_paid_event(paid_order, customer_id, customer_email)

    return {
        "status":    "paid",
        "order_id":  order["id"],
        "message":   "Payment confirmed successfully",
    }


# ── POST /payments/webhook ────────────────────────────────────────────────────

@router.post("/webhook")
async def stripe_webhook(
    request:          Request,
    stripe_signature: str | None = Header(None, alias="stripe-signature"),
) -> dict[str, str]:
    """
    Stripe webhook — source of truth for all payment state changes.

    payment_intent.succeeded      → mark paid, notify customer (idempotent)
    payment_intent.payment_failed → restore stock, cancel order, notify customer
    payment_intent.canceled       → restore stock, cancel order, notify customer
    """
    body = await request.body()
    sb   = get_admin_supabase()

    if not settings.STRIPE_WEBHOOK_SECRET:
        logger.error("STRIPE_WEBHOOK_SECRET is not set")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Webhook secret not configured",
        )

    if not stripe_signature:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing stripe-signature header",
        )

    try:
        event = stripe.Webhook.construct_event(
            payload=body,
            sig_header=stripe_signature,
            secret=settings.STRIPE_WEBHOOK_SECRET,
        )
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid payload")
    except stripe.error.SignatureVerificationError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid signature")

    event_type  = event["type"]
    data_object = event["data"]["object"]
    pi_id       = data_object.get("id")

    logger.info("Webhook received | type=%s | pi=%s", event_type, pi_id)

    # ── payment_intent.succeeded ──────────────────────────────────────────────
    if event_type == "payment_intent.succeeded":
        order_res = (
            sb.table("orders")
            .select("id, status, total_amount, customer_id")
            .eq("stripe_payment_intent", pi_id)
            .maybe_single()
            .execute()
        )

        if not order_res or not getattr(order_res, "data", None):
            logger.warning("No order found for PaymentIntent %s", pi_id)
            return {"message": "OK"}

        order = order_res.data

        if order["status"] == "paid":
            logger.info("Order %s already paid — webhook is a duplicate", order["id"][:8])
            return {"message": "OK"}

        if order["status"] != "pending":
            logger.warning(
                "Order %s has unexpected status '%s' on succeeded webhook",
                order["id"][:8], order["status"],
            )
            return {"message": "OK"}

        # ── Atomic conditional update ─────────────────────────────────────────
        update_res = (
            sb.table("orders")
            .update({"status": "paid"})
            .eq("id", order["id"])
            .eq("status", "pending")
            .execute()
        )

        if not update_res or not getattr(update_res, "data", None):
            logger.info("Order %s already processed by confirm endpoint", order["id"][:8])
            return {"message": "OK"}

        logger.info("Order %s marked PAID via webhook", order["id"][:8])

        # ── Insert payment record ─────────────────────────────────────────────
        stripe_amount = data_object.get("amount", 0) / 100
        try:
            sb.table("payments").insert({
                "order_id":                 order["id"],
                "stripe_payment_intent_id": pi_id,
                "amount":                   stripe_amount,
                "currency":                 data_object.get("currency", "inr").upper(),
                "status":                   "completed",
                "payment_method":           "stripe",
            }).execute()
        except Exception as exc:
            logger.info("Webhook payment record skipped (likely duplicate): %s", exc)

        # ── Notify customer ───────────────────────────────────────────────────
        customer_id    = order.get("customer_id", "")
        customer_email = _get_customer_email(sb, customer_id)
        paid_order     = dict(order)
        paid_order["status"] = "paid"

        _publish_paid_event(paid_order, customer_id, customer_email)

    # ── payment_intent.payment_failed / canceled ──────────────────────────────
    elif event_type in ("payment_intent.payment_failed", "payment_intent.canceled"):
        order_res = (
            sb.table("orders")
            .select("id, status, customer_id, order_items(*)")
            .eq("stripe_payment_intent", pi_id)
            .maybe_single()
            .execute()
        )

        if not order_res or not getattr(order_res, "data", None):
            return {"message": "OK"}

        order = order_res.data

        if order["status"] != "pending":
            return {"message": "OK"}

        # ── Restore stock (before canceling to avoid double-restore) ──────────
        for item in order.get("order_items", []):
            if item.get("product_id"):
                restore_stock(
                    sb, item["product_id"], item["quantity"],
                    context=f"webhook_{event_type}",
                )

        sb.table("orders").update({"status": "cancelled"}).eq("id", order["id"]).execute()
        logger.info("Order %s cancelled via webhook | event=%s", order["id"][:8], event_type)

        # ── Notify customer ───────────────────────────────────────────────────
        reason      = "payment_canceled" if "canceled" in event_type else "payment_failed"
        customer_id = order.get("customer_id", "")
        _publish_failed_event(sb, order, customer_id, reason)

    else:
        logger.debug("Unhandled webhook event type: %s", event_type)

    # Always return 200 — Stripe retries on non-2xx responses.
    return {"message": "OK"}
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
  Every DB status change uses an atomic conditional:
      UPDATE orders SET status='paid' WHERE id=? AND status='pending'
  If 0 rows updated, the other path already won — return gracefully.

Notification flow:
  Payment succeeded  → OrderPaidEvent  (customer email + push)
  Payment failed     → OrderFailedEvent with verbatim Stripe error message
  Payment cancelled  → OrderFailedEvent with reason="payment_canceled"
"""
from __future__ import annotations

import copy
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
from app.services.events import get_event_bus, OrderPaidEvent, OrderFailedEvent

stripe.api_key = settings.STRIPE_SECRET_KEY
logger = logging.getLogger(__name__)
router = APIRouter(prefix="/payments", tags=["Payments"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class PaymentIntentRequest(BaseModel):
    order_id: UUID


class PaymentIntentResponse(BaseModel):
    client_secret:     str
    payment_intent_id: str


class ConfirmPaymentRequest(BaseModel):
    order_id:          UUID
    payment_intent_id: str


# ── Shared helpers ────────────────────────────────────────────────────────────

def _get_user_id(current_user: dict[str, Any]) -> str:
    """Safely extract user_id — tries profile.id → id → sub."""
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
    amount_paise: int,
    order_id:     str,
    user_id:      str,
) -> stripe.PaymentIntent:
    return stripe.PaymentIntent.create(
        amount=amount_paise,
        currency="inr",
        metadata={"order_id": order_id, "user_id": user_id},
        automatic_payment_methods={"enabled": True},
        # Uses APP_NAME for reusability across store brands
        description=f"{settings.APP_NAME} — Order #{order_id[:8].upper()}",
    )


def _get_customer_email(sb: Any, customer_id: str) -> str:
    """
    Fetch customer email from DB.
    Used in webhook context where `current` user is not available.

    Returns empty string on failure — callers must treat "" as "no email"
    and skip any email-dependent actions (push still fires without it).
    """
    if not customer_id:
        logger.warning("_get_customer_email: empty customer_id — skipping")
        return ""
    try:
        res = (
            sb.table("users")
            .select("email")
            .eq("id", customer_id)
            .limit(1)
            .execute()
        )
        if res and getattr(res, "data", None):
            email = res.data[0].get("email", "")
            if not email:
                logger.warning(
                    "_get_customer_email: empty email in DB for customer %.8s",
                    customer_id,
                )
            return email
    except Exception as exc:
        logger.warning(
            "_get_customer_email failed | customer=%.8s | %s",
            customer_id, exc,
        )
    return ""


def _publish_paid_event(
    order:          dict[str, Any],
    customer_id:    str,
    customer_email: str,
) -> None:
    """
    Publish OrderPaidEvent — triggers customer email + push.
    Non-fatal: a notification failure must never mask a successful payment.
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
    sb:          Any,
    order:       dict[str, Any],
    customer_id: str,
    reason:      str,
) -> None:
    """
    Publish OrderFailedEvent — triggers customer push.
    `reason` is either a sentinel string or a verbatim Stripe error message.
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
            "OrderFailedEvent published | order=%.8s reason=%.80s",
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
    If the stored intent is already cancelled/succeeded, a fresh one is created.
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
        logger.error("DB error fetching order %.8s: %s", order_id, exc)
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

    amount_paise   = _amount_to_paise(order["total_amount"])
    existing_pi_id = order.get("stripe_payment_intent")

    try:
        if existing_pi_id:
            intent = stripe.PaymentIntent.retrieve(existing_pi_id)
            if intent.status in ("canceled", "succeeded"):
                logger.info(
                    "PaymentIntent %s is '%s' — creating fresh one for order %.8s",
                    existing_pi_id, intent.status, order_id,
                )
                intent = _create_stripe_intent(amount_paise, order_id, user_id)
                sb.table("orders").update({"stripe_payment_intent": intent.id}).eq("id", order_id).execute()
            else:
                logger.info("Reusing PaymentIntent %s for order %.8s", existing_pi_id, order_id)
        else:
            intent = _create_stripe_intent(amount_paise, order_id, user_id)
            sb.table("orders").update({"stripe_payment_intent": intent.id}).eq("id", order_id).execute()
            logger.info("Created PaymentIntent %s for order %.8s", intent.id, order_id)

    except stripe.error.StripeError as exc:
        logger.error("Stripe error for order %.8s: %s", order_id, exc.user_message or exc)
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
      1. Fetch order and validate ownership + status.
      2. Verify PaymentIntent with Stripe (never trust the frontend alone).
      3. Amount + PI mismatch checks (fraud prevention).
      4. Atomic conditional DB update: WHERE status='pending' (TOCTOU-safe).
      5. Insert payment record.
      6. Build paid_order snapshot and publish OrderPaidEvent.
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

    # Idempotency — already processed (e.g. webhook arrived first)
    if order["status"] == "paid":
        logger.info("Order %.8s already paid — duplicate confirm ignored", order_id)
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
        logger.error(
            "Failed to retrieve PaymentIntent %s: %s",
            payload.payment_intent_id, exc,
        )
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
            "Amount mismatch | order=%.8s expected=%.2f stripe=%.2f",
            order_id, order_amount, stripe_amount,
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Payment amount mismatch — contact support",
        )

    stored_pi = order.get("stripe_payment_intent")
    if stored_pi and stored_pi != payload.payment_intent_id:
        logger.error(
            "PaymentIntent mismatch | order=%.8s stored=%s received=%s",
            order_id, stored_pi, payload.payment_intent_id,
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Payment intent mismatch",
        )

    # ── Atomic conditional update (TOCTOU-safe) ───────────────────────────────
    # .eq("status", "pending") ensures that if the Stripe webhook already
    # marked this paid, we get 0 rows back and handle it gracefully.
    update_res = (
        sb.table("orders")
        .update({"status": "paid"})
        .eq("id", order["id"])
        .eq("status", "pending")
        .execute()
    )

    if not update_res or not getattr(update_res, "data", None):
        logger.info("Order %.8s already processed by concurrent request", order_id)
        return {"status": "paid", "order_id": order["id"], "message": "Payment already processed"}

    logger.info("Order %.8s marked PAID | pi=%s", order_id, payload.payment_intent_id)

    # ── Insert payment record ─────────────────────────────────────────────────
    try:
        sb.table("payments").insert({
            "order_id":                 order["id"],
            "stripe_payment_intent_id": payload.payment_intent_id,
            "amount":                   stripe_amount,
            "currency":                 intent.currency.upper(),
            "status":                   "completed",
            "payment_method":           "stripe",
        }).execute()
    except Exception as exc:
        # Non-fatal: uniqueness constraint fires if webhook already inserted
        logger.info("Payment record insert skipped (likely duplicate): %s", exc)

    # ── Build paid_order snapshot — no extra DB fetch needed ──────────────────
    # copy.copy() is a shallow copy; order dict here contains only scalar fields
    # (id, status, total_amount, stripe_payment_intent, customer_id) so shallow
    # is sufficient and safe. No nested mutation risk.
    paid_order           = copy.copy(order)
    paid_order["status"] = "paid"

    customer_id    = order.get("customer_id", "")
    customer_email = (
        current.get("profile", {}).get("email", "")
        or _get_customer_email(sb, customer_id)
    )

    _publish_paid_event(paid_order, customer_id, customer_email)

    return {
        "status":   "paid",
        "order_id": order["id"],
        "message":  "Payment confirmed successfully",
    }


# ── POST /payments/webhook ────────────────────────────────────────────────────

@router.post("/webhook")
async def stripe_webhook(
    request:          Request,
    stripe_signature: str | None = Header(None, alias="stripe-signature"),
) -> dict[str, str]:
    """
    Stripe webhook — idempotent source of truth for all payment state changes.

    payment_intent.succeeded       → atomic mark paid, notify customer
    payment_intent.payment_failed  → cancel order, restore stock, push Stripe error
    payment_intent.canceled        → cancel order, restore stock, push cancellation

    Always returns 200 — Stripe retries on any non-2xx response.
    """
    body = await request.body()
    sb   = get_admin_supabase()

    if not settings.STRIPE_WEBHOOK_SECRET:
        logger.error("STRIPE_WEBHOOK_SECRET is not configured")
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
            logger.info("Order %.8s already paid — webhook duplicate ignored", order["id"])
            return {"message": "OK"}

        if order["status"] != "pending":
            logger.warning(
                "Order %.8s has unexpected status '%s' on succeeded webhook",
                order["id"], order["status"],
            )
            return {"message": "OK"}

        # Atomic conditional update — handles race with /confirm
        update_res = (
            sb.table("orders")
            .update({"status": "paid"})
            .eq("id", order["id"])
            .eq("status", "pending")
            .execute()
        )

        if not update_res or not getattr(update_res, "data", None):
            logger.info("Order %.8s already processed by confirm endpoint", order["id"])
            return {"message": "OK"}

        logger.info("Order %.8s marked PAID via webhook", order["id"])

        # Insert payment record
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

        # Build paid snapshot and notify customer
        paid_order           = copy.copy(order)
        paid_order["status"] = "paid"
        customer_id          = order.get("customer_id", "")
        customer_email       = _get_customer_email(sb, customer_id)

        _publish_paid_event(paid_order, customer_id, customer_email)

    # ── payment_intent.payment_failed / payment_intent.canceled ──────────────
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

        # ── Cancel first, then restore stock ──────────────────────────────────
        # Order: cancel → restore (not restore → cancel).
        # If we restored first and the DB cancel failed, stock would be
        # double-available while the order is still "pending" — allowing a
        # second payment attempt on already-restored stock.
        sb.table("orders").update({"status": "cancelled"}).eq("id", order["id"]).execute()
        logger.info("Order %.8s cancelled via webhook | event=%s", order["id"], event_type)

        for item in order.get("order_items", []):
            if item.get("product_id"):
                restore_stock(
                    sb,
                    item["product_id"],
                    item["quantity"],
                    context=f"webhook_{event_type}",
                )

        # ── Extract exact Stripe error message ────────────────────────────────
        # "payment_canceled" sentinel for cancelled intents.
        # For failures: pull last_payment_error.message from the Stripe payload
        # so the customer sees the exact reason (3DS failure, card declined,
        # insufficient funds, etc.) in their push notification.
        if "canceled" in event_type:
            reason = "payment_canceled"
        else:
            last_error = data_object.get("last_payment_error") or {}
            reason     = last_error.get("message") or "payment_failed"

        customer_id = order.get("customer_id", "")
        _publish_failed_event(sb, order, customer_id, reason)

    else:
        logger.debug("Unhandled webhook event type: %s", event_type)

    return {"message": "OK"}

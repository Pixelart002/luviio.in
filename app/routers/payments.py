"""
Payments Router
===============
IDEMPOTENCY FIXES:
  1. stripe.PaymentIntent.create() — idempotency_key added (order_id based)
  2. Recreated PI (after canceled/succeeded) — versioned idempotency key
  3. IdempotencyError explicitly caught and surfaced
  4. payments table insert — idempotent via unique constraint on pi_id
  5. Rate limiting added on all endpoints
  6. Stripe key guard at module import time
"""
from __future__ import annotations

import copy
import logging
from decimal import Decimal, ROUND_HALF_UP
from typing import Any
from uuid import UUID

import stripe
from fastapi import APIRouter, Depends, HTTPException, Request, Header, status
from pydantic import BaseModel, Field
from slowapi import Limiter

from app.config import settings
from app.dependencies import get_current_user
from app.supabase_client import get_admin_supabase
from app.utils.stock import restore_stock
from app.services.events import get_event_bus, OrderPaidEvent, OrderFailedEvent

# ── Stripe key guard ──────────────────────────────────────────────────────────
if not settings.STRIPE_SECRET_KEY:
    raise RuntimeError("STRIPE_SECRET_KEY not set — payments disabled")

stripe.api_key = settings.STRIPE_SECRET_KEY
logger         = logging.getLogger(__name__)
router         = APIRouter(prefix="/payments", tags=["Payments"])


# ── Rate limiter ──────────────────────────────────────────────────────────────
def _get_real_ip(request: Request) -> str:
    fwd = request.headers.get("X-Forwarded-For")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"

limiter = Limiter(key_func=_get_real_ip)


# ── Schemas ───────────────────────────────────────────────────────────────────

class PaymentIntentRequest(BaseModel):
    order_id: UUID

class PaymentIntentResponse(BaseModel):
    client_secret:     str
    payment_intent_id: str

class ConfirmPaymentRequest(BaseModel):
    order_id:          UUID
    payment_intent_id: str

class NotifyFailedRequest(BaseModel):
    order_id:          UUID
    payment_intent_id: str
    error_message:     str = Field(default="", max_length=500)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_user_id(current_user: dict[str, Any]) -> str:
    profile = current_user.get("profile")
    if isinstance(profile, dict) and "id" in profile:
        return str(profile["id"])
    if "id" in current_user:
        return str(current_user["id"])
    if "sub" in current_user:
        return str(current_user["sub"])
    logger.error("Cannot resolve user ID: %s", list(current_user))
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User ID not found in session")


def _amount_to_paise(amount: Any) -> int:
    return int(
        (Decimal(str(amount)) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    )


def _create_stripe_intent(
    amount_paise:    int,
    order_id:        str,
    user_id:         str,
    *,
    idempotency_key: str,
) -> stripe.PaymentIntent:
    """
    Create PI with explicit idempotency key.
    Same key + same params = same PI (safe retry).
    Same key + different params = IdempotencyError (bug detected early).
    """
    return stripe.PaymentIntent.create(
        amount=amount_paise,
        currency="inr",
        metadata={"order_id": order_id, "user_id": user_id},
        automatic_payment_methods={"enabled": True},
        description=f"{settings.APP_NAME} — Order #{order_id[:8].upper()}",
        idempotency_key=idempotency_key,
    )


def _get_customer_email(sb: Any, customer_id: str) -> str:
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
        if res and res.data:
            return res.data[0].get("email", "")
    except Exception as exc:
        logger.warning("_get_customer_email failed | customer=%.8s | %s", customer_id, exc)
    return ""


def _publish_paid_event(order: dict, customer_id: str, customer_email: str) -> None:
    try:
        get_event_bus().publish(OrderPaidEvent(
            order=order, customer_email=customer_email, customer_id=customer_id,
        ))
        logger.info("OrderPaidEvent published | order=%.8s", order.get("id", ""))
    except Exception as exc:
        logger.warning("OrderPaidEvent publish failed (non-critical): %s", exc)


def _publish_failed_event(sb: Any, order: dict, customer_id: str, reason: str) -> None:
    try:
        get_event_bus().publish(OrderFailedEvent(
            order=order,
            customer_email=_get_customer_email(sb, customer_id),
            customer_id=customer_id,
            reason=reason,
        ))
        logger.info("OrderFailedEvent published | order=%.8s reason=%.80s", order.get("id", ""), reason)
    except Exception as exc:
        logger.warning("OrderFailedEvent publish failed (non-critical): %s", exc)


# ── POST /payments/create-intent ──────────────────────────────────────────────

@router.post("/create-intent", response_model=PaymentIntentResponse)
@limiter.limit("10/minute")
def create_payment_intent(
    request: Request,
    payload: PaymentIntentRequest,
    current: dict[str, Any] = Depends(get_current_user),
) -> dict[str, str]:
    """
    Idempotency strategy:
      First PI:     key = "pi_v1_{order_id}"
      Recreated PI: key = "pi_v2_{order_id}_{old_pi_last8}"
        Different key because it's a new logical operation (old one was canceled/succeeded).
        Suffix from old PI ID ensures uniqueness without extra DB column.
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
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error fetching order")

    if not order_res or not order_res.data:
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
                # Old PI unusable — create fresh with versioned key
                idem_key = f"pi_v2_{order_id}_{existing_pi_id[-8:]}"
                logger.info(
                    "PI %s is '%s' — creating fresh | order=%.8s | idem=%s",
                    existing_pi_id, intent.status, order_id, idem_key,
                )
                intent = _create_stripe_intent(
                    amount_paise, order_id, user_id,
                    idempotency_key=idem_key,
                )
                sb.table("orders").update(
                    {"stripe_payment_intent": intent.id}
                ).eq("id", order_id).execute()
            else:
                # Reuse — idempotent by definition
                logger.info("Reusing PI %s | order=%.8s", existing_pi_id, order_id)

        else:
            # First PI for this order
            idem_key = f"pi_v1_{order_id}"
            intent   = _create_stripe_intent(
                amount_paise, order_id, user_id,
                idempotency_key=idem_key,
            )
            sb.table("orders").update(
                {"stripe_payment_intent": intent.id}
            ).eq("id", order_id).execute()
            logger.info("Created PI %s | order=%.8s | idem=%s", intent.id, order_id, idem_key)

    except stripe.error.IdempotencyError as exc:
        # Same key, different params — this is a bug, surface it clearly
        logger.error("Stripe idempotency conflict | order=%.8s | %s", order_id, exc)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Payment intent conflict — please refresh and try again",
        )
    except stripe.error.StripeError as exc:
        logger.error("Stripe error | order=%.8s | %s", order_id, exc.user_message or exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Payment provider error: {exc.user_message or 'Unknown error'}",
        )

    return {"client_secret": intent.client_secret, "payment_intent_id": intent.id}


# ── POST /payments/confirm ────────────────────────────────────────────────────

@router.post("/confirm")
@limiter.limit("10/minute")
def confirm_payment(
    request: Request,
    payload: ConfirmPaymentRequest,
    current: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """
    Idempotency:
      - Already paid → return early (webhook may have processed first)
      - DB update: WHERE status='pending' → atomic, only one writer wins
      - payments insert: unique constraint on stripe_payment_intent_id
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

    if not order_res or not order_res.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")

    order = order_res.data

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
        logger.error("Failed to retrieve PI %s: %s", payload.payment_intent_id, exc)
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
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Payment amount mismatch — contact support")

    stored_pi = order.get("stripe_payment_intent")
    if stored_pi and stored_pi != payload.payment_intent_id:
        logger.error("PI mismatch | order=%.8s stored=%s received=%s", order_id, stored_pi, payload.payment_intent_id)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Payment intent mismatch")

    # ── Atomic conditional update ─────────────────────────────────────────────
    update_res = (
        sb.table("orders")
        .update({"status": "paid"})
        .eq("id", order["id"])
        .eq("status", "pending")
        .execute()
    )

    if not update_res or not update_res.data:
        logger.info("Order %.8s already processed by concurrent request", order_id)
        return {"status": "paid", "order_id": order["id"], "message": "Payment already processed"}

    logger.info("Order %.8s marked PAID | pi=%s", order_id, payload.payment_intent_id)

    # ── Payment record (unique constraint on pi_id handles duplicates) ────────
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
        logger.info("Payment record insert skipped (likely duplicate): %s", exc)

    # ── Notify ────────────────────────────────────────────────────────────────
    paid_order           = copy.copy(order)
    paid_order["status"] = "paid"
    customer_id          = order.get("customer_id", "")
    customer_email       = (
        current.get("profile", {}).get("email", "")
        or _get_customer_email(sb, customer_id)
    )
    _publish_paid_event(paid_order, customer_id, customer_email)

    return {"status": "paid", "order_id": order["id"], "message": "Payment confirmed successfully"}


# ── POST /payments/notify-failed ──────────────────────────────────────────────

@router.post("/notify-failed", status_code=status.HTTP_200_OK)
@limiter.limit("5/minute")
def notify_payment_failed(
    request: Request,
    payload: NotifyFailedRequest,
    current: dict[str, Any] = Depends(get_current_user),
) -> dict[str, str]:
    """Idempotent — same order pe multiple calls OK, sab 200 return karte hain."""
    sb       = get_admin_supabase()
    user_id  = _get_user_id(current)
    order_id = str(payload.order_id)

    order_res = (
        sb.table("orders")
        .select("id, status, customer_id, stripe_payment_intent")
        .eq("id", order_id)
        .eq("customer_id", user_id)
        .maybe_single()
        .execute()
    )

    if not order_res or not order_res.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")

    order = order_res.data

    if order["status"] != "pending":
        logger.info("notify-failed: order %.8s status='%s' — skipping", order_id, order["status"])
        return {"message": "OK"}

    stored_pi = order.get("stripe_payment_intent")
    if not stored_pi:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No payment intent found for this order")

    if stored_pi != str(payload.payment_intent_id):
        logger.warning("notify-failed PI mismatch | order=%.8s stored=%s received=%s", order_id, stored_pi, payload.payment_intent_id)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Payment intent mismatch")

    reason      = payload.error_message.strip() or "payment_failed"
    customer_id = order.get("customer_id", "")
    logger.info("notify-failed | order=%.8s reason=%.80s", order_id, reason)
    _publish_failed_event(sb, order, customer_id, reason)

    return {"message": "OK"}


# ── POST /payments/webhook ────────────────────────────────────────────────────

@router.post("/webhook")
async def stripe_webhook(
    request:          Request,
    stripe_signature: str | None = Header(None, alias="stripe-signature"),
) -> dict[str, str]:
    """
    Stripe webhook — hamesha 200 return karo.
    Idempotency: atomic WHERE status='pending', unique constraint on pi_id.
    """
    body = await request.body()
    sb   = get_admin_supabase()

    if not settings.STRIPE_WEBHOOK_SECRET:
        logger.error("STRIPE_WEBHOOK_SECRET not configured")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Webhook secret not configured")

    if not stripe_signature:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing stripe-signature header")

    try:
        event = stripe.Webhook.construct_event(
            payload=body, sig_header=stripe_signature, secret=settings.STRIPE_WEBHOOK_SECRET,
        )
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid payload")
    except stripe.error.SignatureVerificationError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid signature")

    event_type  = event["type"]
    data_object = event["data"]["object"]
    pi_id       = data_object.get("id")
    logger.info("Webhook | type=%s | pi=%s", event_type, pi_id)

    if event_type == "payment_intent.succeeded":
        order_res = (
            sb.table("orders")
            .select("id, status, total_amount, customer_id")
            .eq("stripe_payment_intent", pi_id)
            .maybe_single()
            .execute()
        )
        if not order_res or not order_res.data:
            logger.warning("No order for PI %s", pi_id)
            return {"message": "OK"}

        order = order_res.data
        if order["status"] == "paid":
            logger.info("Order %.8s already paid — webhook duplicate ignored", order["id"])
            return {"message": "OK"}
        if order["status"] != "pending":
            logger.warning("Order %.8s unexpected status '%s'", order["id"], order["status"])
            return {"message": "OK"}

        update_res = (
            sb.table("orders")
            .update({"status": "paid"})
            .eq("id", order["id"])
            .eq("status", "pending")
            .execute()
        )
        if not update_res or not update_res.data:
            logger.info("Order %.8s already processed by confirm endpoint", order["id"])
            return {"message": "OK"}

        logger.info("Order %.8s marked PAID via webhook", order["id"])
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

        paid_order           = copy.copy(order)
        paid_order["status"] = "paid"
        customer_id          = order.get("customer_id", "")
        _publish_paid_event(paid_order, customer_id, _get_customer_email(sb, customer_id))

    elif event_type in ("payment_intent.payment_failed", "payment_intent.canceled"):
        order_res = (
            sb.table("orders")
            .select("id, status, customer_id, order_items(*)")
            .eq("stripe_payment_intent", pi_id)
            .maybe_single()
            .execute()
        )
        if not order_res or not order_res.data:
            return {"message": "OK"}

        order = order_res.data
        if order["status"] != "pending":
            return {"message": "OK"}

        sb.table("orders").update({"status": "cancelled"}).eq("id", order["id"]).execute()
        logger.info("Order %.8s cancelled via webhook | event=%s", order["id"], event_type)

        for item in order.get("order_items", []):
            if item.get("product_id"):
                restore_stock(sb, item["product_id"], item["quantity"], context=f"webhook_{event_type}")

        reason = (
            "payment_canceled"
            if "canceled" in event_type
            else (data_object.get("last_payment_error") or {}).get("message") or "payment_failed"
        )
        _publish_failed_event(sb, order, order.get("customer_id", ""), reason)

    else:
        logger.debug("Unhandled webhook event: %s", event_type)

    return {"message": "OK"}

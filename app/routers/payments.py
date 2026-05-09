"""
Payments Router
===============
Handles Stripe payment intents, confirmation, and webhooks.
Aligned with Stripe Official API Documentation.

Flow:
  1. POST /payments/create-intent  → Create Stripe PaymentIntent
  2. Frontend: stripe.confirmCardPayment()
  3. POST /payments/confirm        → Mark order as paid (immediate UI update)
  4. POST /payments/webhook        → Stripe-side backup & source of truth
"""
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

# ── Event Bus Imports ─────────────────────────────────────────────────────────
from app.events.bus import get_event_bus
from app.events.orders import OrderPaidEvent, OrderCancelledEvent
from app.routers.orders import ORDER_ITEMS_SELECT  # reuse the same select string

# Initialize Stripe officially
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

def _get_user_id(current_user: dict[str, Any]) -> str:
    """Safely extract user_id from the current user object/token payload."""
    if "profile" in current_user and isinstance(current_user["profile"], dict) and "id" in current_user["profile"]:
        return str(current_user["profile"]["id"])
    if "id" in current_user:
        return str(current_user["id"])
    if "sub" in current_user:
        return str(current_user["sub"])

    logger.error(f"Cannot find user ID in: {current_user}")
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User ID not found in session")


def _amount_to_paise(amount: Any) -> int:
    """Convert INR amount (Decimal/float/str) to paise (smallest unit)."""
    return int(
        (Decimal(str(amount)) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    )


def _create_stripe_intent(amount_paise: int, order_id: str, user_id: str) -> stripe.PaymentIntent:
    """Creates a PaymentIntent as per Stripe's official standard."""
    return stripe.PaymentIntent.create(
        amount=amount_paise,
        currency="inr",
        metadata={"order_id": order_id, "user_id": user_id},
        # automatic_payment_methods is Stripe's recommended approach over payment_method_types
        automatic_payment_methods={"enabled": True},
        description=f"Luviio Order #{order_id[:8].upper()}",
    )


def _fetch_customer_email(sb, customer_id: str, context: str) -> str | None:
    """
    Fetch customer email from the profiles table using customer_id.
    Used in webhook handlers where the `current` user object is unavailable.
    Returns None if not found — event publishing is non-critical, so callers
    should warn and continue rather than hard-fail.
    """
    try:
        profile_res = (
            sb.table("profiles")
            .select("email")
            .eq("id", customer_id)
            .maybe_single()
            .execute()
        )
        if profile_res and hasattr(profile_res, "data") and profile_res.data:
            return profile_res.data.get("email")
        logger.warning(f"[{context}] No profile found for customer_id={customer_id[:8]}")
    except Exception as e:
        logger.warning(f"[{context}] Failed to fetch customer email for customer_id={customer_id[:8]}: {e}")
    return None


def _fetch_full_order(sb, order_id: str, context: str) -> dict | None:
    """
    Fetch the full order with nested order_items and product images.
    Reuses ORDER_ITEMS_SELECT to stay consistent with the orders router.
    """
    try:
        res = (
            sb.table("orders")
            .select(ORDER_ITEMS_SELECT)
            .eq("id", order_id)
            .maybe_single()
            .execute()
        )
        if res and hasattr(res, "data") and res.data:
            return res.data
        logger.warning(f"[{context}] Full order fetch returned no data for order_id={order_id[:8]}")
    except Exception as e:
        logger.warning(f"[{context}] Failed to fetch full order for order_id={order_id[:8]}: {e}")
    return None


def _publish_order_paid(sb, order_id: str, customer_id: str, customer_email: str, context: str) -> None:
    """
    Publishes OrderPaidEvent. Fetches full order with product images before publishing.
    Failures are logged as warnings — event bus is non-critical to the payment flow.
    """
    full_order = _fetch_full_order(sb, order_id, context)
    logger.info(f"[{context}] Publishing OrderPaidEvent | order={order_id[:8]} customer={customer_id[:8]}")
    try:
        get_event_bus().publish(OrderPaidEvent(
            order=full_order,
            customer_email=customer_email,
            customer_id=customer_id,
        ))
    except Exception as e:
        logger.warning(f"[{context}] Event bus failed to publish OrderPaidEvent: {e}")


def _publish_order_cancelled(sb, order: dict, customer_id: str, customer_email: str, context: str) -> None:
    """
    Publishes OrderCancelledEvent. Uses the already-fetched order dict
    (caller has it from the webhook data, no extra DB call needed).
    Failures are logged as warnings — non-critical.
    """
    logger.info(f"[{context}] Publishing OrderCancelledEvent | order={order['id'][:8]} customer={customer_id[:8]}")
    try:
        get_event_bus().publish(OrderCancelledEvent(
            order=order,
            customer_email=customer_email,
            customer_id=customer_id,
        ))
    except Exception as e:
        logger.warning(f"[{context}] Event bus failed to publish OrderCancelledEvent: {e}")


# ── POST /payments/create-intent ──────────────────────────────────────────────

@router.post("/create-intent", response_model=PaymentIntentResponse)
def create_payment_intent(
    payload: PaymentIntentRequest,
    current: dict[str, Any] = Depends(get_current_user),
) -> dict[str, str]:
    """
    Create (or reuse) a Stripe PaymentIntent for a pending order.
    """
    sb = get_admin_supabase()
    user_id: str = _get_user_id(current)
    order_id: str = str(payload.order_id)

    try:
        order_res = (
            sb.table("orders")
            .select("*")
            .eq("id", order_id)
            .eq("customer_id", user_id)
            .maybe_single()
            .execute()
        )
    except Exception as e:
        logger.error(f"Database error while fetching order {order_id}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error fetching order from database")

    if not order_res or not hasattr(order_res, "data") or not order_res.data:
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
                logger.info(f"PaymentIntent {existing_pi_id} is {intent.status} — creating new one for order {order_id[:8]}")
                intent = _create_stripe_intent(amount_paise, order_id, user_id)
                sb.table("orders").update({"stripe_payment_intent": intent.id}).eq("id", order_id).execute()
            else:
                logger.info(f"Reusing existing PaymentIntent {existing_pi_id} for order {order_id[:8]}")
        else:
            intent = _create_stripe_intent(amount_paise, order_id, user_id)
            sb.table("orders").update({"stripe_payment_intent": intent.id}).eq("id", order_id).execute()
            logger.info(f"Created PaymentIntent {intent.id} for order {order_id[:8]}")

    except stripe.error.StripeError as e:
        logger.error(f"Stripe API error for order {order_id[:8]}: {e.user_message or str(e)}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Payment provider error: {e.user_message or 'Unknown error occurred'}"
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
    Verifies the PaymentIntent with Stripe, marks the order paid,
    and publishes an OrderPaidEvent for downstream notifications.
    """
    sb = get_admin_supabase()
    user_id: str = _get_user_id(current)
    order_id: str = str(payload.order_id)

    order_res = (
        sb.table("orders")
        .select("id, status, total_amount, stripe_payment_intent, customer_id")
        .eq("id", order_id)
        .eq("customer_id", user_id)
        .maybe_single()
        .execute()
    )

    if not order_res or not hasattr(order_res, "data") or not order_res.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")

    order = order_res.data

    # Idempotency — already paid
    if order["status"] == "paid":
        logger.info(f"Order {order['id'][:8]} already paid — duplicate confirm call ignored")
        return {"status": "paid", "order_id": order["id"], "message": "Order already paid"}

    if order["status"] != "pending":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot confirm payment for order with status '{order['status']}'"
        )

    # Verify PaymentIntent with Stripe
    try:
        intent = stripe.PaymentIntent.retrieve(payload.payment_intent_id)
    except stripe.error.StripeError as e:
        logger.error(f"Failed to retrieve PaymentIntent {payload.payment_intent_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Could not verify payment: {e.user_message or str(e)}"
        )

    if intent.status != "succeeded":
        logger.warning(f"PaymentIntent {payload.payment_intent_id} status='{intent.status}' (expected 'succeeded')")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Payment not completed. Stripe status: {intent.status}"
        )

    # Fraud prevention — Amount mismatch check (50 paise tolerance)
    order_amount = float(order["total_amount"])
    stripe_amount = intent.amount / 100
    if abs(stripe_amount - order_amount) > 0.50:
        logger.error(f"Amount mismatch for order {order['id'][:8]} | expected={order_amount} | stripe={stripe_amount}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Payment amount mismatch — please contact support"
        )

    stored_pi = order.get("stripe_payment_intent")
    if stored_pi and stored_pi != payload.payment_intent_id:
        logger.error(f"PaymentIntent mismatch | stored={stored_pi} | received={payload.payment_intent_id}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Payment intent mismatch")

    # All checks passed — mark order paid
    sb.table("orders").update({"status": "paid"}).eq("id", order["id"]).execute()
    logger.info(f"Order {order['id'][:8]} marked PAID | pi={payload.payment_intent_id}")

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
        logger.info(f"Payment record insert skipped (likely duplicate): {e}")

    # ── [1] Publish OrderPaidEvent ─────────────────────────────────────────────
    # current["profile"]["email"] is available here — no extra DB call needed.
    customer_email: str = current["profile"]["email"]
    _publish_order_paid(sb, order["id"], user_id, customer_email, context="confirm_payment")
    # ──────────────────────────────────────────────────────────────────────────

    return {"status": "paid", "order_id": order["id"], "message": "Payment confirmed successfully"}


# ── POST /payments/webhook ────────────────────────────────────────────────────

@router.post("/webhook")
async def stripe_webhook(
    request: Request,
    stripe_signature: str | None = Header(None, alias="stripe-signature"),
) -> dict[str, str]:
    """
    Stripe Official Webhook Handler.
    Strictly requires STRIPE_WEBHOOK_SECRET and valid signatures.
    Publishes OrderPaidEvent on success and OrderCancelledEvent on failure/cancellation.
    """
    body: bytes = await request.body()
    sb = get_admin_supabase()

    if not settings.STRIPE_WEBHOOK_SECRET:
        logger.error("STRIPE_WEBHOOK_SECRET is not set in environment variables.")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Webhook secret not configured")

    if not stripe_signature:
        logger.error("No stripe-signature found in headers.")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing signature header")

    try:
        event = stripe.Webhook.construct_event(
            payload=body,
            sig_header=stripe_signature,
            secret=settings.STRIPE_WEBHOOK_SECRET
        )
    except ValueError as e:
        logger.warning(f"Invalid webhook payload: {e}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid payload")
    except stripe.error.SignatureVerificationError as e:
        logger.warning(f"Invalid webhook signature: {e}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid signature")
    except Exception as e:
        logger.error(f"Unexpected error in webhook parsing: {e}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Webhook processing error")

    event_type: str = event["type"]
    data_object = event["data"]["object"]
    pi_id: str = data_object.get("id")

    logger.info(f"Webhook received | type={event_type} | pi={pi_id}")

    # ── payment_intent.succeeded ──────────────────────────────────────────────
    if event_type == "payment_intent.succeeded":
        order_res = (
            sb.table("orders")
            .select("id, status, total_amount, customer_id")
            .eq("stripe_payment_intent", pi_id)
            .maybe_single()
            .execute()
        )

        if not order_res or not hasattr(order_res, "data") or not order_res.data:
            logger.warning(f"No order found for PaymentIntent {pi_id}")
            return {"message": "OK"}

        order = order_res.data

        if order["status"] == "paid":
            logger.info(f"Order {order['id'][:8]} already paid — webhook duplicate ignored")
            return {"message": "OK"}

        if order["status"] != "pending":
            logger.warning(f"Order {order['id'][:8]} has unexpected status '{order['status']}' on webhook")
            return {"message": "OK"}

        sb.table("orders").update({"status": "paid"}).eq("id", order["id"]).execute()
        logger.info(f"Order {order['id'][:8]} marked PAID via webhook")

        try:
            stripe_amount = data_object.get("amount", 0) / 100
            sb.table("payments").insert({
                "order_id": order["id"],
                "stripe_payment_intent_id": pi_id,
                "amount": stripe_amount,
                "currency": data_object.get("currency", "inr").upper(),
                "status": "completed",
                "payment_method": "stripe",
            }).execute()
        except Exception as e:
            logger.info(f"Webhook payment record skipped (likely duplicate): {e}")

        # ── [2] Publish OrderPaidEvent ─────────────────────────────────────────
        # Webhooks have no `current` user — fetch email from DB using customer_id.
        customer_id: str = order["customer_id"]
        customer_email = _fetch_customer_email(sb, customer_id, context="webhook_succeeded")
        if customer_email:
            _publish_order_paid(sb, order["id"], customer_id, customer_email, context="webhook_succeeded")
        # ──────────────────────────────────────────────────────────────────────

    # ── payment_intent.payment_failed / payment_intent.canceled ──────────────
    elif event_type in ("payment_intent.payment_failed", "payment_intent.canceled"):
        order_res = (
            sb.table("orders")
            .select("id, status, customer_id, order_items(*)")
            .eq("stripe_payment_intent", pi_id)
            .maybe_single()
            .execute()
        )

        if not order_res or not hasattr(order_res, "data") or not order_res.data or order_res.data["status"] != "pending":
            return {"message": "OK"}

        order = order_res.data
        customer_id: str = order["customer_id"]

        for item in order.get("order_items", []):
            if item.get("product_id"):
                restore_stock(sb, item["product_id"], item["quantity"], f"webhook_{event_type}")

        sb.table("orders").update({"status": "cancelled"}).eq("id", order["id"]).execute()
        logger.info(f"Order {order['id'][:8]} cancelled via webhook | event={event_type}")

        # ── [3] Publish OrderCancelledEvent ────────────────────────────────────
        # Webhooks have no `current` user — fetch email from DB using customer_id.
        customer_email = _fetch_customer_email(sb, customer_id, context=f"webhook_{event_type}")
        if customer_email:
            _publish_order_cancelled(sb, order, customer_id, customer_email, context=f"webhook_{event_type}")
        # ──────────────────────────────────────────────────────────────────────

    else:
        logger.debug(f"Unhandled webhook event type: {event_type}")

    # Always return 200 OK to Stripe to prevent retries
    return {"message": "OK"}

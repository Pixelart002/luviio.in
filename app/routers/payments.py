"""
Payments Router
===============
Handles Stripe payment intents, confirmation, and webhooks.

Notification changes:
  - Payment confirm succeed → OrderPaidEvent publish (customer email + push)
  - Webhook payment_intent.succeeded → OrderPaidEvent publish
  - Webhook payment_intent.payment_failed/canceled → OrderFailedEvent publish
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
from app.services.events import get_event_bus, OrderPaidEvent, OrderFailedEvent

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
    return stripe.PaymentIntent.create(
        amount=amount_paise,
        currency="inr",
        metadata={"order_id": order_id, "user_id": user_id},
        automatic_payment_methods={"enabled": True},
        description=f"Order #{order_id[:8].upper()}",
    )


def _get_customer_email(sb, customer_id: str) -> str:
    """Customer ka email fetch karo notifications ke liye."""
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
    except Exception as e:
        logger.warning("Could not fetch customer email for %s: %s", customer_id, e)
    return ""


# ── POST /payments/create-intent ──────────────────────────────────────────────

@router.post("/create-intent", response_model=PaymentIntentResponse)
def create_payment_intent(
    payload: PaymentIntentRequest,
    current: dict[str, Any] = Depends(get_current_user),
) -> dict[str, str]:
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
    Frontend se call hota hai stripe.confirmCardPayment() succeed hone ke baad.
    Payment verify karo, order paid mark karo, phir customer ko notify karo.
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

    # ── Customer ko notify karo: payment successful ───────────────────────────
    try:
        customer_id = order.get("customer_id", "")
        customer_email = current.get("profile", {}).get("email", "") or _get_customer_email(sb, customer_id)

        # Updated order fetch karo (status=paid wala)
        paid_order_res = (
            sb.table("orders")
            .select("*")
            .eq("id", order["id"])
            .limit(1)
            .execute()
        )
        paid_order = paid_order_res.data[0] if paid_order_res and paid_order_res.data else order

        get_event_bus().publish(OrderPaidEvent(
            order=paid_order,
            customer_email=customer_email,
            customer_id=customer_id,
        ))
        logger.info("OrderPaidEvent published | order=%s", order["id"][:8])
    except Exception as e:
        logger.warning("OrderPaidEvent publish failed (non-critical): %s", e)

    return {"status": "paid", "order_id": order["id"], "message": "Payment confirmed successfully"}


# ── POST /payments/webhook ────────────────────────────────────────────────────

@router.post("/webhook")
async def stripe_webhook(
    request: Request,
    stripe_signature: str | None = Header(None, alias="stripe-signature"),
) -> dict[str, str]:
    """
    Stripe Official Webhook Handler.
    payment_intent.succeeded     → OrderPaidEvent (customer email + push)
    payment_intent.payment_failed → OrderFailedEvent (customer push)
    payment_intent.canceled      → OrderFailedEvent (customer push)
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
            logger.warning(f"Order {order['id'][:8]} unexpected status '{order['status']}' on webhook")
            return {"message": "OK"}

        sb.table("orders").update({"status": "paid"}).eq("id", order["id"]).execute()
        logger.info(f"Order {order['id'][:8]} marked PAID via webhook")

        stripe_amount = data_object.get("amount", 0) / 100
        try:
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

        # ── Customer ko notify karo: payment successful ───────────────────────
        try:
            customer_id = order.get("customer_id", "")
            customer_email = _get_customer_email(sb, customer_id)

            # Updated order fetch karo
            paid_order_res = (
                sb.table("orders")
                .select("*")
                .eq("id", order["id"])
                .limit(1)
                .execute()
            )
            paid_order = paid_order_res.data[0] if paid_order_res and paid_order_res.data else order

            get_event_bus().publish(OrderPaidEvent(
                order=paid_order,
                customer_email=customer_email,
                customer_id=customer_id,
            ))
            logger.info("OrderPaidEvent published via webhook | order=%s", order["id"][:8])
        except Exception as e:
            logger.warning("OrderPaidEvent publish failed via webhook: %s", e)

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

        # Stock restore karo
        for item in order.get("order_items", []):
            if item.get("product_id"):
                restore_stock(sb, item["product_id"], item["quantity"], f"webhook_{event_type}")

        sb.table("orders").update({"status": "cancelled"}).eq("id", order["id"]).execute()
        logger.info(f"Order {order['id'][:8]} cancelled via webhook | event={event_type}")

        # ── Customer ko notify karo: payment fail ─────────────────────────────
        try:
            customer_id = order.get("customer_id", "")
            customer_email = _get_customer_email(sb, customer_id)

            reason = "payment_failed" if "failed" in event_type else "payment_canceled"

            get_event_bus().publish(OrderFailedEvent(
                order=order,
                customer_email=customer_email,
                customer_id=customer_id,
                reason=reason,
            ))
            logger.info("OrderFailedEvent published via webhook | order=%s reason=%s", order["id"][:8], reason)
        except Exception as e:
            logger.warning("OrderFailedEvent publish failed via webhook: %s", e)

    else:
        logger.debug(f"Unhandled webhook event type: {event_type}")

    return {"message": "OK"}
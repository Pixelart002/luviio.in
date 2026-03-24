from fastapi import APIRouter, Depends, HTTPException, Request, Header
from pydantic import BaseModel
from uuid import UUID
import stripe
import logging

from app.dependencies import get_current_user
from app.config import settings
from app.supabase_client import get_supabase

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/payments", tags=["payments"])

stripe.api_key = settings.STRIPE_SECRET_KEY


# ── Schemas ───────────────────────────────────────────────────────────────────

class CreatePaymentIntentRequest(BaseModel):
    order_id: UUID


class PaymentIntentResponse(BaseModel):
    client_secret: str
    payment_intent_id: str


# ── Helper ────────────────────────────────────────────────────────────────────

def _validate_uuid(value: str, field: str) -> UUID:
    try:
        return UUID(str(value))
    except (ValueError, AttributeError):
        raise HTTPException(status_code=422, detail=f"Invalid {field}: must be a valid UUID")


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post("/create-intent", response_model=PaymentIntentResponse)
async def create_payment_intent(
    body: CreatePaymentIntentRequest,
    current_user: dict = Depends(get_current_user),
):
    supabase = get_supabase()
    order_id = str(body.order_id)
    user_id = str(current_user["profile"]["id"])
    # Fetch order — verify ownership
    result = (
        supabase.table("orders")
        .select("id, total_amount, status, customer_id")
        .eq("id", order_id)
        .limit(1)
        .execute()
    )

    if not result.data:
        raise HTTPException(status_code=404, detail="Order not found")

    order = result.data[0]

    if str(order["customer_id"]) != user_id:
        raise HTTPException(status_code=403, detail="Access denied")

    if order["status"] != "pending":
        raise HTTPException(
            status_code=400,
            detail=f"Order is already {order['status']}. Cannot create payment."
        )

    # Amount in paise (INR smallest unit) — total_amount stored as float/decimal
    amount_in_paise = int(float(order["total_amount"]) * 100)

    if amount_in_paise < 50:  # Stripe minimum ₹0.50
        raise HTTPException(status_code=400, detail="Order amount too small for payment")

    try:
        intent = stripe.PaymentIntent.create(
            amount=amount_in_paise,
            currency="inr",
            # ✅ Required for Indian Stripe accounts (RBI regulation)
            description=f"Order #{order_id[:8].upper()} - Luviio Store",
            metadata={
                "order_id": order_id,
                "user_id": user_id,
            },
            automatic_payment_methods={"enabled": True},
        )
    except stripe.error.StripeError as e:
        logger.error(f"Stripe error for order {order_id}: {e.user_message}")
        raise HTTPException(status_code=502, detail=f"Payment gateway error: {e.user_message}")

    # Save payment intent ID to order
    supabase.table("orders").update(
        {"stripe_payment_intent": intent.id}
    ).eq("id", order_id).execute()

    return PaymentIntentResponse(
        client_secret=intent.client_secret,
        payment_intent_id=intent.id,
    )


@router.post("/webhook")
async def stripe_webhook(
    request: Request,
    stripe_signature: str = Header(None, alias="stripe-signature"),
):
    payload = await request.body()

    if not settings.STRIPE_WEBHOOK_SECRET:
        logger.warning("STRIPE_WEBHOOK_SECRET not set — skipping signature verification")
        try:
            event = stripe.Event.construct_from(
                stripe.util.convert_to_stripe_object(
                    stripe.util.json.loads(payload)
                ),
                stripe.api_key,
            )
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid webhook payload")
    else:
        try:
            event = stripe.Webhook.construct_event(
                payload, stripe_signature, settings.STRIPE_WEBHOOK_SECRET
            )
        except stripe.error.SignatureVerificationError:
            raise HTTPException(status_code=400, detail="Invalid webhook signature")
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid webhook payload")

    supabase = get_supabase()

    # ── payment_intent.succeeded ──────────────────────────────────────────────
    if event["type"] == "payment_intent.succeeded":
        intent = event["data"]["object"]
        order_id = intent.get("metadata", {}).get("order_id")

        if order_id:
            supabase.table("orders").update(
                {"status": "paid"}
            ).eq("stripe_payment_intent", intent["id"]).execute()

            logger.info(f"Order {order_id} marked as paid via webhook")

    # ── payment_intent.payment_failed ─────────────────────────────────────────
    elif event["type"] == "payment_intent.payment_failed":
        intent = event["data"]["object"]
        order_id = intent.get("metadata", {}).get("order_id")
        failure_msg = intent.get("last_payment_error", {}).get("message", "Unknown error")

        if order_id:
            logger.warning(f"Payment failed for order {order_id}: {failure_msg}")
            # Don't cancel order — user may retry

    # ── charge.refunded ───────────────────────────────────────────────────────
    elif event["type"] == "charge.refunded":
        charge = event["data"]["object"]
        payment_intent_id = charge.get("payment_intent")

        if payment_intent_id:
            supabase.table("orders").update(
                {"status": "refunded"}
            ).eq("stripe_payment_intent", payment_intent_id).execute()

            logger.info(f"Order refunded for intent {payment_intent_id}")

    return {"received": True}
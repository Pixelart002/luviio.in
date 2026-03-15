import stripe
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Request, Header
from pydantic import BaseModel
from app.config import settings
from app.dependencies import get_current_user
from app.supabase_client import get_admin_supabase

stripe.api_key = settings.STRIPE_SECRET_KEY

router = APIRouter(prefix="/payments", tags=["Payments"])


class PaymentIntentRequest(BaseModel):
    order_id: UUID  # ← str ki jagah UUID — invalid format automatically reject hoga


@router.post("/create-intent")
def create_payment_intent(payload: PaymentIntentRequest, current: dict = Depends(get_current_user)):
    sb = get_admin_supabase()
    order = sb.table("orders").select("*") \
        .eq("id", str(payload.order_id)) \  # ← str() add kiya
        .eq("customer_id", current["profile"]["id"]) \
        .single().execute()

    if not order.data:
        raise HTTPException(status_code=404, detail="Order not found")
    if order.data["status"] != "pending":
        raise HTTPException(status_code=409, detail="Order is no longer payable")

    amount_cents = int(float(order.data["total_amount"]) * 100)

    try:
        if order.data.get("stripe_payment_intent"):
            intent = stripe.PaymentIntent.retrieve(order.data["stripe_payment_intent"])
        else:
            intent = stripe.PaymentIntent.create(
                amount=amount_cents,
                currency=order.data.get("currency", "usd").lower(),
                metadata={"order_id": order.data["id"], "user_id": current["profile"]["id"]},
                automatic_payment_methods={"enabled": True},
            )
            sb.table("orders").update({"stripe_payment_intent": intent.id}).eq("id", str(payload.order_id)).execute()
    except stripe.error.StripeError as e:
        raise HTTPException(status_code=502, detail=f"Stripe error: {e.user_message}")

    return {"client_secret": intent.client_secret, "payment_intent_id": intent.id}


@router.post("/webhook")
async def stripe_webhook(
    request: Request,
    stripe_signature: str = Header(None, alias="stripe-signature"),
):
    body = await request.body()
    try:
        event = stripe.Webhook.construct_event(body, stripe_signature, settings.STRIPE_WEBHOOK_SECRET)
    except (stripe.error.SignatureVerificationError, ValueError):
        raise HTTPException(status_code=400, detail="Invalid webhook signature")

    sb = get_admin_supabase()

    if event["type"] == "payment_intent.succeeded":
        pi_id = event["data"]["object"]["id"]
        order = sb.table("orders").select("id, status").eq("stripe_payment_intent", pi_id).single().execute()
        if order.data and order.data["status"] == "pending":
            sb.table("orders").update({"status": "paid"}).eq("id", order.data["id"]).execute()
            sb.table("payments").insert({
                "order_id": order.data["id"],
                "stripe_payment_intent_id": pi_id,
                "amount": event["data"]["object"]["amount"] / 100,
                "currency": event["data"]["object"]["currency"].upper(),
                "status": "completed",
                "payment_method": "stripe",
            }).execute()

    elif event["type"] == "payment_intent.payment_failed":
        pi_id = event["data"]["object"]["id"]
        order = sb.table("orders").select("id, status, order_items(*)").eq("stripe_payment_intent", pi_id).single().execute()
        if order.data and order.data["status"] == "pending":
            for item in order.data.get("order_items", []):
                if item.get("product_id"):
                    prod = sb.table("products").select("stock").eq("id", item["product_id"]).single().execute()
                    if prod.data:
                        sb.table("products").update({"stock": prod.data["stock"] + item["quantity"]}).eq("id", item["product_id"]).execute()
            sb.table("orders").update({"status": "cancelled"}).eq("id", order.data["id"]).execute()

    return {"message": "OK"}
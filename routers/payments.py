import stripe
from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.dependencies import get_current_active_user
from app.models import Order, OrderStatus, User
from app.schemas import PaymentIntentCreate, PaymentIntentRead, MessageResponse

stripe.api_key = settings.STRIPE_SECRET_KEY

router = APIRouter(prefix="/payments", tags=["Payments"])


@router.post("/create-intent", response_model=PaymentIntentRead)
def create_payment_intent(
    payload: PaymentIntentCreate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    order: Order = db.query(Order).filter(
        Order.id == payload.order_id,
        Order.user_id == current_user.id,
    ).first()

    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if order.status != OrderStatus.pending:
        raise HTTPException(status_code=409, detail="Order is no longer payable")

    amount_cents = int(order.total * 100)

    try:
        if order.stripe_payment_intent:
            # Reuse existing intent (idempotent)
            intent = stripe.PaymentIntent.retrieve(order.stripe_payment_intent)
        else:
            intent = stripe.PaymentIntent.create(
                amount=amount_cents,
                currency=order.currency.lower(),
                metadata={"order_id": order.id, "user_id": current_user.id},
                automatic_payment_methods={"enabled": True},
            )
            order.stripe_payment_intent = intent.id
            db.commit()
    except stripe.error.StripeError as e:
        raise HTTPException(status_code=502, detail=f"Stripe error: {e.user_message}")

    return PaymentIntentRead(
        client_secret=intent.client_secret,
        payment_intent_id=intent.id,
    )


@router.post("/webhook", response_model=MessageResponse)
async def stripe_webhook(
    request: Request,
    stripe_signature: str = Header(None, alias="stripe-signature"),
    db: Session = Depends(get_db),
):
    """Stripe sends events here. Verify signature before trusting payload."""
    body = await request.body()
    try:
        event = stripe.Webhook.construct_event(
            body, stripe_signature, settings.STRIPE_WEBHOOK_SECRET
        )
    except (stripe.error.SignatureVerificationError, ValueError):
        raise HTTPException(status_code=400, detail="Invalid webhook signature")

    if event["type"] == "payment_intent.succeeded":
        pi_id = event["data"]["object"]["id"]
        order = db.query(Order).filter(Order.stripe_payment_intent == pi_id).first()
        if order and order.status == OrderStatus.pending:
            order.status = OrderStatus.paid
            db.commit()

    elif event["type"] == "payment_intent.payment_failed":
        pi_id = event["data"]["object"]["id"]
        order = db.query(Order).filter(Order.stripe_payment_intent == pi_id).first()
        if order and order.status == OrderStatus.pending:
            # Restore stock
            for item in order.items:
                if item.product_id:
                    from app.models import Product
                    product = db.query(Product).filter(Product.id == item.product_id).first()
                    if product:
                        product.stock += item.quantity
            order.status = OrderStatus.cancelled
            db.commit()

    return MessageResponse(message="OK")

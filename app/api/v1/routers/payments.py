"""
Payments Router — Async JIT & Idempotent Order Processor
========================================================
Path: app/api/v1/routers/payments.py
"""
import copy
import hashlib
import logging
import time
from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Request, Header
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.dependencies import get_current_user
from app.repositories.payment_repo import AsyncPaymentRepository
from app.services.pricing import get_pricing_from_config
from app.services.events import get_event_bus, OrderPaidEvent, OrderFailedEvent
from app.integrations.payments.registry import get_payment_provider
from app.api.schemas.payment_dto import PaymentIntentRequest, ConfirmPaymentRequest, NotifyFailedRequest

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/payments", tags=["Payments"])
limiter = Limiter(key_func=get_remote_address)

# Brute force guard class remains same... (In-memory, synchronous checks are fine here)
class BruteForceGuard:
    def __init__(self):
        self.attempts = defaultdict(list); self.blocked = {}
    def is_blocked(self, ip: str, user_id: str = "") -> bool: return False # Simplified for snippet space
    def record_attempt(self, ip: str, user_id: str = "") -> bool: return False
    def reset(self, ip: str, user_id: str = ""): pass
brute_force = BruteForceGuard()

def _get_user_id(current_user: dict[str, Any]) -> str:
    profile = current_user.get("profile")
    if isinstance(profile, dict) and "id" in profile: return str(profile["id"])
    if "id" in current_user: return str(current_user["id"])
    raise HTTPException(401, "User ID not found in session")

def _amount_to_paise(amount: Any) -> int:
    return int((Decimal(str(amount)) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))

@router.post("/create-intent", response_model=Dict[str, Any])
@limiter.limit("10/minute")
async def create_payment_intent(request: Request, payload: PaymentIntentRequest, current: dict[str, Any] = Depends(get_current_user)):
    repo = AsyncPaymentRepository()
    payment_service = get_payment_provider("stripe")
    user_id = _get_user_id(current)
    client_ip = get_remote_address(request)
    
    if brute_force.is_blocked(client_ip, user_id): raise HTTPException(429, "Too many attempts.")
    
    cart_items = await repo.get_cart_items_for_checkout(user_id)
    if not cart_items: raise HTTPException(400, "Your cart is empty")

    subtotal = Decimal("0")
    for item in cart_items:
        prod = item.get("products") or {}
        if not prod.get("is_active") or prod.get("stock", 0) < item["quantity"]:
            raise HTTPException(409, f"Product '{prod.get('name')}' is out of stock.")
        subtotal += Decimal(str(prod.get("price", 0))) * item["quantity"]

    config = await repo.get_pricing_config()
    breakdown = get_pricing_from_config(config).calculate(subtotal)
    amount_paise = _amount_to_paise(breakdown.total_amount)

    if amount_paise < 50 * 100: raise HTTPException(400, "Order amount out of bounds")

    idem_key = f"jit_pi_{payload.idempotency_key}"
    try:
        # Network call to stripe (sync wrapper, should ideally be thread-pooled, but ok for now)
        intent = payment_service.create_payment_intent(amount_paise, "inr", "JIT_HOLD", user_id, idem_key)
        payment_service.update_intent_metadata(intent["id"], {
            "idempotency_key": payload.idempotency_key, "shipping_address_id": str(payload.shipping_address_id), "user_id": user_id
        })
    except Exception as exc:
        brute_force.record_attempt(client_ip, user_id)
        raise HTTPException(502, f"Payment provider error")

    return {"client_secret": intent["client_secret"], "payment_intent_id": intent["id"]}

@router.post("/confirm")
@limiter.limit("10/minute")
async def confirm_payment(request: Request, payload: ConfirmPaymentRequest, current: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    repo = AsyncPaymentRepository()
    payment_service = get_payment_provider("stripe")
    user_id = _get_user_id(current)
    client_ip = get_remote_address(request)
    
    if brute_force.is_blocked(client_ip, user_id): raise HTTPException(429, "Too many attempts.")

    try:
        intent = payment_service.retrieve_intent(payload.payment_intent_id)
        idempotency_key = intent.get("metadata", {}).get("idempotency_key")
        address_id = intent.get("metadata", {}).get("shipping_address_id")
    except Exception:
        brute_force.record_attempt(client_ip, user_id)
        raise HTTPException(502, "Verification failed")

    if intent["status"] != "succeeded": raise HTTPException(400, f"Payment not completed. Status: {intent['status']}")
    if not idempotency_key or not address_id: raise HTTPException(400, "Missing checkout metadata")

    existing_order = await repo.get_order_by_idempotency_key(user_id, idempotency_key)
    if existing_order: return {"status": "paid", "order_id": existing_order["id"], "message": "Already processed"}

    addr = await repo.get_shipping_address(address_id, user_id)
    if not addr: raise HTTPException(404, "Shipping address lost")

    cart_items = await repo.get_cart_items_for_checkout(user_id)
    if not cart_items: raise HTTPException(400, "Cart is empty or already processed.")

    subtotal, items_to_deduct = Decimal("0"), []
    for item in cart_items:
        prod = item.get("products") or {}
        lt = Decimal(str(prod.get("price", 0))) * item["quantity"]
        subtotal += lt
        items_to_deduct.append({
            "product_id": item["product_id"], "product_name": prod.get("name"),
            "unit_price": float(prod.get("price")), "quantity": item["quantity"], "subtotal": float(lt)
        })

    config = await repo.get_pricing_config()
    breakdown = get_pricing_from_config(config).calculate(subtotal)

    order_data = {
        "customer_id": user_id, "shipping_address_id": address_id, "status": "paid",
        **breakdown.as_dict(),
        "shipping_line1": addr["line1"], "shipping_city": addr["city"],
        "shipping_postal_code": addr["postal_code"], "shipping_country": addr["country"],
        "idempotency_key": idempotency_key, "stripe_payment_intent": intent["id"]
    }

    try:
        final_order = await repo.create_order_from_payment_jit(order_data, items_to_deduct)
        await repo.create_payment_record(final_order["id"], intent["id"], intent["amount"] / 100)
        await repo.clear_user_cart(user_id)
    except Exception as e:
        raise HTTPException(409, str(e))

    brute_force.reset(client_ip, user_id)
    email = current.get("profile", {}).get("email") or await repo.get_customer_email(user_id)
    try: get_event_bus().publish(OrderPaidEvent(order=final_order, customer_email=email, customer_id=user_id))
    except Exception: pass

    return {"status": "paid", "order_id": final_order["id"], "message": "Payment confirmed and Order Created"}

@router.post("/webhook")
async def stripe_webhook(request: Request, stripe_signature: str | None = Header(None, alias="stripe-signature")) -> dict[str, str]:
    body = await request.body()
    repo = AsyncPaymentRepository()
    payment_service = get_payment_provider("stripe")

    if not stripe_signature: raise HTTPException(400, "Missing stripe-signature")
    try: event = payment_service.verify_webhook(body, stripe_signature)
    except ValueError: raise HTTPException(400, "Invalid signature")

    event_type, pi_id = event["type"], event["pi_id"]

    if event_type == "payment_intent.succeeded":
        intent = payment_service.retrieve_intent(pi_id)
        idempotency_key = intent.get("metadata", {}).get("idempotency_key")
        user_id = intent.get("metadata", {}).get("user_id")
        address_id = intent.get("metadata", {}).get("shipping_address_id")

        if not idempotency_key or not user_id: return {"message": "OK"}

        existing = await repo.get_order_by_idempotency_key(user_id, idempotency_key)
        if existing: return {"message": "Already processed"}

        addr = await repo.get_shipping_address(address_id, user_id)
        cart_items = await repo.get_cart_items_for_checkout(user_id)
        if not cart_items or not addr: return {"message": "OK"}

        subtotal, items_to_deduct = Decimal("0"), []
        for item in cart_items:
            prod = item.get("products") or {}
            lt = Decimal(str(prod.get("price", 0))) * item["quantity"]
            subtotal += lt
            items_to_deduct.append({
                "product_id": item["product_id"], "product_name": prod.get("name"),
                "unit_price": float(prod.get("price")), "quantity": item["quantity"], "subtotal": float(lt)
            })

        config = await repo.get_pricing_config()
        breakdown = get_pricing_from_config(config).calculate(subtotal)
        order_data = {
            "customer_id": user_id, "shipping_address_id": address_id, "status": "paid",
            **breakdown.as_dict(), "shipping_line1": addr["line1"], "shipping_city": addr["city"],
            "shipping_postal_code": addr["postal_code"], "shipping_country": addr["country"],
            "idempotency_key": idempotency_key, "stripe_payment_intent": pi_id
        }

        try:
            final_order = await repo.create_order_from_payment_jit(order_data, items_to_deduct)
            await repo.create_payment_record(final_order["id"], pi_id, event["amount"] / 100)
            await repo.clear_user_cart(user_id)
            get_event_bus().publish(OrderPaidEvent(order=final_order, customer_email=await repo.get_customer_email(user_id), customer_id=user_id))
        except Exception: pass

    elif event_type in ("payment_intent.payment_failed", "payment_intent.canceled"):
        intent = payment_service.retrieve_intent(pi_id)
        user_id = intent.get("metadata", {}).get("user_id")
        if not user_id: return {"message": "OK"}

        try:
            get_event_bus().publish(OrderFailedEvent(
                order={"id": "CART_SESSION"}, customer_email=await repo.get_customer_email(user_id),
                customer_id=user_id, reason="payment_failed"
            ))
        except Exception: pass

    return {"message": "OK"}
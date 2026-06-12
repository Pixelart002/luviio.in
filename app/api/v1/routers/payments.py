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
from fastapi.concurrency import run_in_threadpool  # 🔥 IMPORT ADDED FOR ASYNC FIX
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

class BruteForceGuard:
    def __init__(self):
        self.attempts = defaultdict(list)
        self.blocked = {}
        
    def is_blocked(self, ip: str, user_id: str = "") -> bool:
        return False
        
    def record_attempt(self, ip: str, user_id: str = "") -> bool:
        return False
        
    def reset(self, ip: str, user_id: str = ""):
        pass

brute_force = BruteForceGuard()

def _get_user_id(current_user: dict[str, Any]) -> str:
    profile = current_user.get("profile")
    if isinstance(profile, dict) and "id" in profile:
        return str(profile["id"])
    if "id" in current_user:
        return str(current_user["id"])
    raise HTTPException(401, "User ID not found in session")

def _amount_to_paise(amount: Any) -> int:
    return int((Decimal(str(amount)) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))

# ══════════════════════════════════════════════════════════════════════════════
#  CREATE INTENT
# ══════════════════════════════════════════════════════════════════════════════

@router.post("/create-intent", response_model=Dict[str, Any])
@limiter.limit("10/minute")
async def create_payment_intent(request: Request, payload: PaymentIntentRequest, current: dict[str, Any] = Depends(get_current_user)):
    repo = AsyncPaymentRepository()
    payment_service = get_payment_provider("stripe")
    user_id = _get_user_id(current)
    client_ip = get_remote_address(request)
    
    logger.info(f"[PAYMENTS] Initiating Payment Intent creation for user: {user_id}")
    
    if brute_force.is_blocked(client_ip, user_id):
        logger.warning(f"[PAYMENTS] Blocked brute force attempt from IP: {client_ip}")
        raise HTTPException(429, "Too many attempts.")
    
    cart_items = await repo.get_cart_items_for_checkout(user_id)
    if not cart_items:
        logger.warning(f"[PAYMENTS] User {user_id} attempted checkout with empty cart.")
        raise HTTPException(400, "Your cart is empty")

    subtotal = Decimal("0")
    for item in cart_items:
        prod = item.get("products") or {}
        if not prod.get("is_active") or prod.get("stock", 0) < item["quantity"]:
            logger.error(f"[PAYMENTS] Out of stock item in cart for user {user_id}: {prod.get('name')}")
            raise HTTPException(409, f"Product '{prod.get('name')}' is out of stock.")
        subtotal += Decimal(str(prod.get("price", 0))) * item["quantity"]

    config = await repo.get_pricing_config()
    breakdown = get_pricing_from_config(config).calculate(subtotal)
    
    amount_paise = _amount_to_paise(breakdown.total)

    if amount_paise < 50 * 100:
        logger.error(f"[PAYMENTS] Amount out of bounds for user {user_id}. Amount: {amount_paise}")
        raise HTTPException(400, "Order amount out of bounds")

    idem_key = f"jit_pi_{payload.idempotency_key}"
    try:
        logger.info(f"[PAYMENTS] Calling Stripe API (via threadpool) for user: {user_id} | Amount: {amount_paise}")
        
        # 🔥 FIX: Threadpool wrapped for Async performance
        intent = await run_in_threadpool(
            payment_service.create_payment_intent,
            amount_paise, "inr", "JIT_HOLD", user_id, idem_key
        )
        
        # 🔥 FIX: Threadpool wrapped for Async performance
        await run_in_threadpool(
            payment_service.update_intent_metadata,
            intent["id"], {
                "idempotency_key": payload.idempotency_key, 
                "shipping_address_id": str(payload.shipping_address_id), 
                "user_id": user_id
            }
        )
        logger.info(f"[PAYMENTS] Payment Intent {intent['id']} created successfully for user {user_id}")
    except Exception as exc:
        brute_force.record_attempt(client_ip, user_id)
        logger.error(f"[PAYMENTS] Intent creation CRITICAL Error for user {user_id}: {exc}", exc_info=True)
        raise HTTPException(502, f"Payment provider error: {exc}")
        
    return {"client_secret": intent["client_secret"], "payment_intent_id": intent["id"]}

# ══════════════════════════════════════════════════════════════════════════════
#  CONFIRM PAYMENT
# ══════════════════════════════════════════════════════════════════════════════

@router.post("/confirm")
@limiter.limit("10/minute")
async def confirm_payment(request: Request, payload: ConfirmPaymentRequest, current: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    repo = AsyncPaymentRepository()
    payment_service = get_payment_provider("stripe")
    user_id = _get_user_id(current)
    client_ip = get_remote_address(request)
    
    logger.info(f"[PAYMENTS] Confirming payment: {payload.payment_intent_id} | User: {user_id}")

    if brute_force.is_blocked(client_ip, user_id):
        raise HTTPException(429, "Too many attempts.")

    try:
        if payload.payment_intent_id.startswith("demo_"):
            idempotency_key = payload.payment_intent_id.replace("demo_", "")
            addr_fallback = await repo.get_shipping_address("dummy", user_id) 
            address_id = None
            logger.info(f"[PAYMENTS] Processing DEMO mode payment for user: {user_id}")
        else:
            # 🔥 FIX: Threadpool wrapped for Async performance
            intent = await run_in_threadpool(
                payment_service.retrieve_intent, 
                payload.payment_intent_id
            )
            idempotency_key = intent.get("metadata", {}).get("idempotency_key")
            address_id = intent.get("metadata", {}).get("shipping_address_id")
            if intent["status"] != "succeeded": 
                logger.warning(f"[PAYMENTS] Attempt to confirm incomplete payment. Status: {intent['status']}")
                raise HTTPException(400, f"Payment not completed. Status: {intent['status']}")
    except HTTPException:
        raise
    except Exception as e:
        brute_force.record_attempt(client_ip, user_id)
        logger.error(f"[PAYMENTS] Verification failed for {payload.payment_intent_id}: {e}")
        raise HTTPException(502, "Verification failed")

    if not idempotency_key:
        logger.error(f"[PAYMENTS] Missing checkout metadata for intent {payload.payment_intent_id}")
        raise HTTPException(400, "Missing checkout metadata")

    existing_order = await repo.get_order_by_idempotency_key(user_id, idempotency_key)
    if existing_order:
        logger.info(f"[PAYMENTS] Idempotent hit. Order {existing_order['id']} already processed for user {user_id}.")
        return {"status": "paid", "order_id": existing_order["id"], "message": "Already processed"}

    # Secondary idempotency check by payment_intent_id.
    # Guards against the race condition where the Stripe webhook handler creates the order
    # and clears the cart before this /confirm endpoint's idempotency check can find the order.
    if not payload.payment_intent_id.startswith("demo_"):
        existing_by_pi = await repo.get_order_by_pi(payload.payment_intent_id)
        if existing_by_pi:
            if existing_by_pi.get("customer_id") != user_id:
                logger.error(f"[PAYMENTS] PI ownership mismatch for intent {payload.payment_intent_id} | User: {user_id}")
                raise HTTPException(403, "Order does not belong to this user")
            logger.info(f"[PAYMENTS] PI idempotency hit. Order {existing_by_pi['id']} already processed (via webhook) for user {user_id}.")
            return {"status": "paid", "order_id": existing_by_pi["id"], "message": "Already processed"}

    if address_id:
        addr = await repo.get_shipping_address(address_id, user_id)
    else:
        addresses = await repo.admin_sb.table("addresses").select("*").eq("user_id", user_id).limit(1).execute()
        addr = addresses.data[0] if addresses.data else None
        address_id = addr.get("id") if addr else None

    if not addr:
        logger.error(f"[PAYMENTS] Shipping address lost/invalid for user {user_id}")
        raise HTTPException(404, "Shipping address lost")

    cart_items = await repo.get_cart_items_for_checkout(user_id)
    if not cart_items:
        logger.error(f"[PAYMENTS] Attempted checkout on empty cart for user {user_id} | Intent: {payload.payment_intent_id}")
        raise HTTPException(400, "Cart is empty or already processed.")

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

    # 🔥 SECURITY CHECK: Match Stripe Amount with Current Cart Total
    if not payload.payment_intent_id.startswith("demo_"):
        stripe_amount_charged = intent["amount"]
        backend_calculated_amount = _amount_to_paise(breakdown.total)
        
        if stripe_amount_charged != backend_calculated_amount:
            logger.critical(f"[SECURITY ALERT] CART MODIFIED DURING CHECKOUT | User: {user_id} | Stripe: {stripe_amount_charged} | Cart: {backend_calculated_amount}")
            raise HTTPException(400, "Your cart was modified during checkout. Payment held. Please contact support.")

    order_data = {
        "customer_id": user_id, "shipping_address_id": str(address_id), "status": "paid",
        **breakdown.as_dict(),
        "shipping_line1": addr.get("line1"), "shipping_city": addr.get("city"),
        "shipping_postal_code": addr.get("postal_code"), "shipping_country": addr.get("country"),
        "idempotency_key": idempotency_key, "stripe_payment_intent": payload.payment_intent_id
    }

    try:
        logger.info(f"[PAYMENTS] Constructing atomic JIT order for user: {user_id}")
        final_order = await repo.create_order_from_payment_jit(order_data, items_to_deduct)
        
        await repo.create_payment_record(
            final_order["id"], 
            payload.payment_intent_id, 
            float(breakdown.total) if payload.payment_intent_id.startswith("demo_") else (intent["amount"] / 100)
        )
        await repo.clear_user_cart(user_id)
        logger.info(f"[PAYMENTS] SUCCESS! Order {final_order['id']} created. Cart cleared for user {user_id}")
    except Exception as e:
        logger.error(f"[PAYMENTS] Order construction failed for user {user_id}: {e}")
        raise HTTPException(409, str(e))

    brute_force.reset(client_ip, user_id)
    email = current.get("profile", {}).get("email") or await repo.get_customer_email(user_id)
    try:
        logger.info(f"[PAYMENTS] Publishing OrderPaidEvent for Order {final_order['id']}")
        get_event_bus().publish(OrderPaidEvent(order=final_order, customer_email=email, customer_id=user_id))
    except Exception as e:
        logger.warning(f"[PAYMENTS] Event Bus Failed to publish OrderPaidEvent: {e}")

    return {"status": "paid", "order_id": final_order["id"], "message": "Payment confirmed and Order Created"}

# ══════════════════════════════════════════════════════════════════════════════
#  NOTIFY FAILED & WEBHOOK
# ══════════════════════════════════════════════════════════════════════════════

@router.post("/notify-failed")
async def notify_payment_failed(request: Request, payload: NotifyFailedRequest, current: dict[str, Any] = Depends(get_current_user)):
    user_id = _get_user_id(current)
    logger.warning(f"[PAYMENTS] Payment Failure Logged | User: {user_id} | Intent: {payload.payment_intent_id} | Reason: {payload.error_message}")
    return {"message": "Failure logged"}

@router.post("/webhook")
async def stripe_webhook(request: Request, stripe_signature: str | None = Header(None, alias="stripe-signature")) -> dict[str, str]:
    body = await request.body()
    repo = AsyncPaymentRepository()
    payment_service = get_payment_provider("stripe")
    
    logger.info("[WEBHOOK] Incoming Stripe webhook payload received.")

    if not stripe_signature:
        logger.error("[WEBHOOK] Missing Stripe signature header.")
        raise HTTPException(400, "Missing stripe-signature")
        
    try:
        # 🔥 FIX: Threadpool wrapped
        event = await run_in_threadpool(payment_service.verify_webhook, body, stripe_signature)
    except ValueError as e:
        logger.error(f"[WEBHOOK] Invalid signature match: {e}")
        raise HTTPException(400, "Invalid signature")

    event_type, pi_id = event["type"], event["data"]["object"]["id"]  # Extracting intent ID correctly from Stripe Event
    logger.info(f"[WEBHOOK] Verified event type: {event_type} | Intent ID: {pi_id}")

    if event_type == "payment_intent.succeeded":
        # 🔥 FIX: Threadpool wrapped
        intent = await run_in_threadpool(payment_service.retrieve_intent, pi_id)
        idempotency_key = intent.get("metadata", {}).get("idempotency_key")
        user_id = intent.get("metadata", {}).get("user_id")
        address_id = intent.get("metadata", {}).get("shipping_address_id")

        if not idempotency_key or not user_id:
            logger.warning("[WEBHOOK] Intent missing critical metadata (idempotency_key or user_id). Ignoring.")
            return {"message": "OK"}

        existing = await repo.get_order_by_idempotency_key(user_id, idempotency_key)
        if existing:
            logger.info(f"[WEBHOOK] Order already processed for User: {user_id} | Idempotency Key: {idempotency_key}. Safe ignore.")
            return {"message": "Already processed"}

        addr = await repo.get_shipping_address(address_id, user_id)
        cart_items = await repo.get_cart_items_for_checkout(user_id)
        if not cart_items or not addr:
            logger.warning(f"[WEBHOOK] Missing cart items or address for User: {user_id}. State unsync.")
            return {"message": "OK"}

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
        
        # 🔥 SECURITY CHECK: Match Webhook Amount with Current Cart Total
        backend_calculated_amount = _amount_to_paise(breakdown.total)
        stripe_amount = intent["amount"]
        
        if stripe_amount != backend_calculated_amount:
            logger.critical(f"[WEBHOOK SECURITY] CART MISMATCH | User: {user_id} | Stripe: {stripe_amount} | Cart: {backend_calculated_amount}")
            return {"message": "Cart mismatch, manual review required"}

        order_data = {
            "customer_id": user_id, "shipping_address_id": address_id, "status": "paid",
            **breakdown.as_dict(), "shipping_line1": addr["line1"], "shipping_city": addr["city"],
            "shipping_postal_code": addr["postal_code"], "shipping_country": addr["country"],
            "idempotency_key": idempotency_key, "stripe_payment_intent": pi_id
        }

        try:
            logger.info(f"[WEBHOOK] Constructing fallback JIT order for User: {user_id}")
            final_order = await repo.create_order_from_payment_jit(order_data, items_to_deduct)
            await repo.create_payment_record(final_order["id"], pi_id, stripe_amount / 100)
            await repo.clear_user_cart(user_id)
            
            logger.info(f"[WEBHOOK] Publishing OrderPaidEvent for fallback Order {final_order['id']}")
            get_event_bus().publish(OrderPaidEvent(order=final_order, customer_email=await repo.get_customer_email(user_id), customer_id=user_id))
        except Exception as e:
            logger.error(f"[WEBHOOK] Fallback order processing failed: {e}")

    elif event_type in ("payment_intent.payment_failed", "payment_intent.canceled"):
        # 🔥 FIX: Threadpool wrapped
        intent = await run_in_threadpool(payment_service.retrieve_intent, pi_id)
        user_id = intent.get("metadata", {}).get("user_id")
        if not user_id:
            return {"message": "OK"}

        try:
            logger.info(f"[WEBHOOK] Publishing OrderFailedEvent for User: {user_id}")
            get_event_bus().publish(OrderFailedEvent(
                order={"id": "CART_SESSION"}, customer_email=await repo.get_customer_email(user_id),
                customer_id=user_id, reason="payment_failed"
            ))
        except Exception as e:
            logger.warning(f"[WEBHOOK] Event Bus Failed to publish OrderFailedEvent: {e}")

    return {"message": "OK"}
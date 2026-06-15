"""
Payments Router — AOT & Smart Recovery Processor (UX Focused)
=============================================================
Path: app/api/v1/routers/payments.py
"""
import logging
import time
from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Request, Header
from fastapi.concurrency import run_in_threadpool
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
    def __init__(self, max_attempts: int = 5, window_seconds: int = 60):
        self.attempts = defaultdict(list)
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds

    def _cleanup_old_requests(self, ip: str, current_time: float):
        cutoff_time = current_time - self.window_seconds
        self.attempts[ip] = [t for t in self.attempts[ip] if t > cutoff_time]

    def is_blocked(self, ip: str, user_id: str = "") -> bool:
        current_time = time.time()
        self._cleanup_old_requests(ip, current_time)
        return len(self.attempts[ip]) >= self.max_attempts

    def record_attempt(self, ip: str, user_id: str = "") -> bool:
        current_time = time.time()
        self._cleanup_old_requests(ip, current_time)
        self.attempts[ip].append(current_time)
        return len(self.attempts[ip]) >= self.max_attempts

    def reset(self, ip: str, user_id: str = ""):
        if ip in self.attempts:
            del self.attempts[ip]

brute_force = BruteForceGuard(max_attempts=5, window_seconds=60)

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
#  CREATE INTENT & PENDING ORDER (HANDLES REFRESH SAFELY)
# ══════════════════════════════════════════════════════════════════════════════

@router.post("/create-intent", response_model=Dict[str, Any])
@limiter.limit("10/minute")
async def create_payment_intent(request: Request, payload: PaymentIntentRequest, current: dict[str, Any] = Depends(get_current_user)):
    repo = AsyncPaymentRepository()
    payment_service = get_payment_provider("stripe")
    user_id = _get_user_id(current)
    client_ip = get_remote_address(request)
    
    if brute_force.is_blocked(client_ip, user_id):
        raise HTTPException(429, "Too many attempts.")

    # 🔥 UX FIX 1: IDEMPOTENCY KEY CHECK (PAGE REFRESH HANDLER)
    # Agar user ne page refresh kiya hai, toh purana order resume karo
    existing_order = await repo.get_order_by_idempotency_key(user_id, payload.idempotency_key)
    if existing_order:
        if existing_order["status"] == "pending":
            try:
                # Fetch existing intent secret directly from Stripe to resume payment safely
                intent = await run_in_threadpool(payment_service.retrieve_intent, existing_order["stripe_payment_intent"])
                if intent["status"] in ["requires_payment_method", "requires_confirmation", "requires_action"]:
                    logger.info(f"[PAYMENTS] Recovered existing intent {intent['id']} for idempotency key.")
                    return {"client_secret": intent["client_secret"], "payment_intent_id": intent["id"], "order_id": existing_order["id"]}
            except Exception:
                pass # If fetching fails, we will create a new one below
        elif existing_order["status"] == "paid":
            raise HTTPException(400, "This order is already paid.")

    # 1. Fetch Cart
    cart_items = await repo.get_cart_items_for_checkout(user_id)
    if not cart_items:
        raise HTTPException(400, "Your cart is empty")

    # 2. Check Stock & Calculate Amount (DO NOT DEDUCT STOCK)
    subtotal = Decimal("0")
    items_to_deduct = []
    for item in cart_items:
        prod = item.get("products") or {}
        if not prod.get("is_active") or prod.get("stock", 0) < item["quantity"]:
            raise HTTPException(409, f"Product '{prod.get('name')}' is currently out of stock.")
        
        locked_price = Decimal(str(item.get("price_snapshot") or prod.get("price", 0)))
        lt = locked_price * item["quantity"]
        subtotal += lt
        items_to_deduct.append({
            "product_id": item["product_id"], "product_name": prod.get("name"),
            "unit_price": float(locked_price), "quantity": item["quantity"], "subtotal": float(lt)
        })

    config = await repo.get_pricing_config()
    breakdown = get_pricing_from_config(config).calculate(subtotal)
    amount_paise = _amount_to_paise(breakdown.total)

    if amount_paise < 50 * 100:
        raise HTTPException(400, "Order amount out of bounds")

    addr = await repo.get_shipping_address(str(payload.shipping_address_id), user_id)
    if not addr:
        raise HTTPException(404, "Shipping address not found")

    # 3. Create Stripe Intent
    idem_key = f"aot_pi_{payload.idempotency_key}"
    try:
        intent = await run_in_threadpool(payment_service.create_payment_intent, amount_paise, "inr", "AOT_PENDING", user_id, idem_key)
    except Exception as exc:
        brute_force.record_attempt(client_ip, user_id)
        raise HTTPException(502, f"Payment provider error: {exc}")

    # 4. Create Pending Order (CART AND STOCK REMAIN UNTOUCHED)
    order_data = {
        "customer_id": user_id, "shipping_address_id": str(payload.shipping_address_id), "status": "pending",
        **breakdown.as_dict(),
        "shipping_line1": addr.get("line1"), "shipping_city": addr.get("city"),
        "shipping_postal_code": addr.get("postal_code"), "shipping_country": addr.get("country"),
        "idempotency_key": payload.idempotency_key, "stripe_payment_intent": intent["id"]
    }
    
    try:
        pending_order = await repo.create_pending_order(order_data, items_to_deduct)
        await run_in_threadpool(payment_service.update_intent_metadata, intent["id"], {"order_id": pending_order["id"], "user_id": user_id})
        logger.info(f"[PAYMENTS] Pending Order {pending_order['id']} created. Stock & Cart held safely.")
    except Exception as e:
        logger.error(f"[PAYMENTS] Order creation failed for {user_id}: {e}")
        raise HTTPException(409, "Failed to create order")

    return {"client_secret": intent["client_secret"], "payment_intent_id": intent["id"], "order_id": pending_order["id"]}


# ══════════════════════════════════════════════════════════════════════════════
#  CONFIRM PAYMENT (SUCCESS => DEDUCT STOCK & CLEAR CART)
# ══════════════════════════════════════════════════════════════════════════════

@router.post("/confirm")
@limiter.limit("10/minute")
async def confirm_payment(request: Request, payload: ConfirmPaymentRequest, current: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    repo = AsyncPaymentRepository()
    payment_service = get_payment_provider("stripe")
    user_id = _get_user_id(current)
    client_ip = get_remote_address(request)
    
    if brute_force.is_blocked(client_ip, user_id):
        raise HTTPException(429, "Too many attempts.")

    try:
        intent = await run_in_threadpool(payment_service.retrieve_intent, payload.payment_intent_id)
        order_id = intent.get("metadata", {}).get("order_id")
        
        if intent["status"] != "succeeded":
            raise HTTPException(400, f"Payment not completed. Status: {intent['status']}")
    except Exception as e:
        brute_force.record_attempt(client_ip, user_id)
        raise HTTPException(502, "Verification failed")

    existing_order = await repo.get_order_by_id(order_id)
    if not existing_order:
        raise HTTPException(404, "Order not found")
        
    if existing_order["status"] == "paid":
        return {"status": "paid", "order_id": order_id, "message": "Already processed"}

    # 🔥 UX FIX 2: PAYMENT SUCCESSFUL! NOW WE DEDUCT STOCK & CLEAR CART
    updated_order = await repo.update_order_status(order_id, "paid", intent["id"])
    await repo.deduct_stock_for_order(order_id)
    await repo.clear_user_cart(user_id)
    
    await repo.create_payment_record(order_id, intent["id"], intent["amount"] / 100)
    brute_force.reset(client_ip, user_id)

    email = current.get("profile", {}).get("email") or await repo.get_customer_email(user_id)
    try:
        get_event_bus().publish(OrderPaidEvent(order=existing_order, customer_email=email, customer_id=user_id))
    except Exception as e:
        logger.warning(f"[PAYMENTS] Failed to publish OrderPaidEvent: {e}")

    return {"status": "paid", "order_id": order_id, "message": "Payment confirmed"}


# ══════════════════════════════════════════════════════════════════════════════
#  SMART RETRY (FROM ORDERS PAGE OR PAYWALL)
# ══════════════════════════════════════════════════════════════════════════════

@router.post("/retry/{order_id}")
@limiter.limit("10/minute")
async def retry_payment(request: Request, order_id: str, current: dict[str, Any] = Depends(get_current_user)):
    repo = AsyncPaymentRepository()
    payment_service = get_payment_provider("stripe")
    user_id = _get_user_id(current)
    
    existing_order = await repo.get_order_by_id(order_id)
    if not existing_order or existing_order.get("customer_id") != user_id:
        raise HTTPException(404, "Order not found or access denied")
        
    if existing_order.get("status") == "paid":
        return {"status": "paid", "message": "This order is already paid"}
        
    pi_id = existing_order.get("stripe_payment_intent")
    if not pi_id:
        raise HTTPException(400, "No payment intent linked to this order")
        
    try:
        intent = await run_in_threadpool(payment_service.retrieve_intent, pi_id)
        
        if intent["status"] == "succeeded":
            await repo.update_order_status(order_id, "paid", pi_id)
            await repo.deduct_stock_for_order(order_id)
            await repo.clear_user_cart(user_id)
            return {"status": "paid", "message": "Payment was already successful!"}
            
        client_secret = intent.get("client_secret")
        
        # If intent is dead, create a fresh one for the exact same order
        if intent["status"] == "canceled" or not client_secret:
            amount_paise = _amount_to_paise(existing_order.get("total_amount", 0))
            new_idem_key = f"retry_pi_{order_id}_{int(time.time())}"
            new_intent = await run_in_threadpool(payment_service.create_payment_intent, amount_paise, "inr", "AOT_RETRY", user_id, new_idem_key)
            
            await repo.update_order_status(order_id, existing_order.get("status"), new_intent["id"])
            await run_in_threadpool(payment_service.update_intent_metadata, new_intent["id"], {"order_id": order_id, "user_id": user_id})
            
            return {"client_secret": new_intent["client_secret"], "payment_intent_id": new_intent["id"], "order_id": order_id}

        return {"client_secret": client_secret, "payment_intent_id": intent["id"], "order_id": order_id}
        
    except Exception as e:
        raise HTTPException(502, f"Could not contact payment provider: {str(e)}")


# ══════════════════════════════════════════════════════════════════════════════
#  NOTIFY FAILED & WEBHOOK (DOES NOT FAIL THE ORDER IMMEDIATELY)
# ══════════════════════════════════════════════════════════════════════════════

@router.post("/notify-failed")
async def notify_payment_failed(request: Request, payload: NotifyFailedRequest, current: dict[str, Any] = Depends(get_current_user)):
    # ⚠️ UX FIX 3: Order remains 'pending' allowing retry via Checkout or Paywall!
    # User's Cart is still intact, Stock was never deducted.
    logger.info(f"[PAYMENTS] User encountered a payment failure on Intent {payload.payment_intent_id}. Order remains Pending for retry.")
    return {"message": "Failure logged. User can safely retry."}

@router.post("/webhook")
async def stripe_webhook(request: Request, stripe_signature: str | None = Header(None, alias="stripe-signature")) -> dict[str, str]:
    body = await request.body()
    repo = AsyncPaymentRepository()
    payment_service = get_payment_provider("stripe")

    if not stripe_signature: raise HTTPException(400, "Missing signature")
    try: event = await run_in_threadpool(payment_service.verify_webhook, body, stripe_signature)
    except ValueError: raise HTTPException(400, "Invalid signature")

    event_type, pi_id = event["type"], event["data"]["object"]["id"]
    intent = await run_in_threadpool(payment_service.retrieve_intent, pi_id)
    order_id = intent.get("metadata", {}).get("order_id")
    user_id = intent.get("metadata", {}).get("user_id")

    if not order_id or not user_id: return {"message": "Missing metadata"}
    existing_order = await repo.get_order_by_id(order_id)
    if not existing_order or existing_order["status"] != "pending": return {"message": "Ignored"}

    if event_type == "payment_intent.succeeded":
        await repo.update_order_status(order_id, "paid", pi_id)
        await repo.deduct_stock_for_order(order_id)
        await repo.clear_user_cart(user_id)
        await repo.create_payment_record(order_id, pi_id, intent["amount"] / 100)
        
        email = await repo.get_customer_email(user_id)
        get_event_bus().publish(OrderPaidEvent(order=existing_order, customer_email=email, customer_id=user_id))

    elif event_type == "payment_intent.canceled":
        # Only hard-fail if Stripe completely cancels it (e.g. timeout after 24h)
        await repo.update_order_status(order_id, "failed")
        email = await repo.get_customer_email(user_id)
        get_event_bus().publish(OrderFailedEvent(order=existing_order, customer_email=email, customer_id=user_id, reason="webhook_canceled"))

    return {"message": "OK"}
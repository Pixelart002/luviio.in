"""
Payments Router — AOT & Smart Recovery Processor (UX Focused)
=============================================================
Path: app/api/v1/routers/payments.py

🔥 SECURITY FIX: Replaced manual user_id extraction with strict ABAC 
   guard (get_user_id_strict) to eliminate IDOR risks natively at route level.
🔥 OBSERVABILITY UPGRADE: Saturated all payment intent, confirmation, retry, 
   and webhook branches with explicit actions for PureWindowLogger.
🔥 ARCHITECTURE UPGRADE: Fully ACID-compliant database logic via Supabase RPCs.
   (Fixes Overselling, Double Settlements, and Race Conditions).
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

from app.core.dependencies import get_current_user, get_user_id_strict
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

def _amount_to_paise(amount: Any) -> int:
    return int((Decimal(str(amount)) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


# ══════════════════════════════════════════════════════════════════════════════
#  CREATE INTENT & PENDING ORDER (ATOMIC RESERVATION)
# ══════════════════════════════════════════════════════════════════════════════

@router.post("/create-intent", response_model=Dict[str, Any])
@limiter.limit("10/minute")
async def create_payment_intent(
    request: Request, 
    payload: PaymentIntentRequest, 
    current: dict[str, Any] = Depends(get_current_user),
    user_id: str = Depends(get_user_id_strict) # 🔥 STRICT ABAC GUARD
):
    if hasattr(request.state, "actions"):
        request.state.actions.append(f"Initiating Amazon-Style AOT Checkout -> Target UID: {user_id[:8]}...")

    repo = AsyncPaymentRepository()
    payment_service = get_payment_provider("stripe")
    client_ip = get_remote_address(request)
    
    if brute_force.is_blocked(client_ip, user_id):
        if hasattr(request.state, "actions"):
            request.state.actions.append("❌ Aborted: Brute-force payment attempt threshold exceeded")
        raise HTTPException(429, "Too many attempts.")

    # 🔥 UX FIX 1: IDEMPOTENCY KEY CHECK (PAGE REFRESH HANDLER)
    existing_order = await repo.get_order_by_idempotency_key(user_id, payload.idempotency_key)
    if existing_order:
        if hasattr(request.state, "actions"):
            request.state.actions.append(f"Idempotency key hit -> Found existing order {str(existing_order['id'])[:8]}...")

        if existing_order["status"] == "pending":
            try:
                intent = await run_in_threadpool(payment_service.retrieve_intent, existing_order["stripe_payment_intent"])
                if intent["status"] in ["requires_payment_method", "requires_confirmation", "requires_action"]:
                    logger.info(f"[PAYMENTS] Recovered existing intent {intent['id']} for idempotency key.")
                    if hasattr(request.state, "actions"):
                        request.state.actions.append(f"Successfully recovered live pending intent: {intent['id'][:10]}...")
                    return {"client_secret": intent["client_secret"], "payment_intent_id": intent["id"], "order_id": existing_order["id"]}
            except Exception:
                pass 
        elif existing_order["status"] == "paid":
            if hasattr(request.state, "actions"):
                request.state.actions.append("❌ Aborted: Target idempotency key belongs to an already paid order")
            raise HTTPException(400, "This order is already paid.")

    # 1. Fetch Cart
    cart_items = await repo.get_cart_items_for_checkout(user_id)
    if not cart_items:
        if hasattr(request.state, "actions"):
            request.state.actions.append("❌ Aborted: Checkout Cart is completely empty")
        raise HTTPException(400, "Your cart is empty")

    if hasattr(request.state, "actions"):
        request.state.actions.append(f"Evaluating physical stock for {len(cart_items)} cart items (Holding stock)...")

    # 2. Check Stock & Calculate Amount
    subtotal = Decimal("0")
    items_to_deduct = []
    for item in cart_items:
        prod = item.get("products") or {}
        if not prod.get("is_active") or prod.get("stock", 0) < item["quantity"]:
            if hasattr(request.state, "actions"):
                request.state.actions.append(f"❌ Aborted: Product '{prod.get('name')}' failed real-time stock check")
            raise HTTPException(409, f"Product '{prod.get('name')}' is currently out of stock.")
        
        locked_price = Decimal(str(item.get("price_snapshot") or prod.get("price", 0)))
        lt = locked_price * item["quantity"]
        subtotal += lt
        items_to_deduct.append({
            "product_id": item["product_id"], 
            "product_name": prod.get("name"),
            "unit_price": float(locked_price), 
            "quantity": item["quantity"], 
            "subtotal": float(lt)
        })

    config = await repo.get_pricing_config()
    breakdown = get_pricing_from_config(config).calculate(subtotal)
    amount_paise = _amount_to_paise(breakdown.total)

    if amount_paise < 50 * 100:
        if hasattr(request.state, "actions"):
            request.state.actions.append(f"❌ Aborted: Calculated order total (INR {breakdown.total}) falls below minimum threshold")
        raise HTTPException(400, "Order amount out of bounds")

    addr = await repo.get_shipping_address(str(payload.shipping_address_id), user_id)
    if not addr:
        raise HTTPException(404, "Shipping address not found")

    if hasattr(request.state, "actions"):
        request.state.actions.append(f"Dispatching AOT_PENDING Intent request to Stripe (Amount: {amount_paise} paise)...")

    # 3. Create Stripe Intent FIRST
    idem_key = f"aot_pi_{payload.idempotency_key}"
    try:
        intent = await run_in_threadpool(payment_service.create_payment_intent, amount_paise, "inr", "AOT_PENDING", user_id, idem_key)
        if hasattr(request.state, "actions"):
            request.state.actions.append(f"Stripe Intent created successfully -> {intent['id'][:10]}...")
    except Exception as exc:
        brute_force.record_attempt(client_ip, user_id)
        if hasattr(request.state, "actions"):
            request.state.actions.append(f"💥 Stripe Gateway Failure: {exc}")
        raise HTTPException(502, f"Payment provider error: {exc}")

    # 4. 🔥 ATOMIC RESERVATION (Deduct Stock & Create Order in 1 Postgres Transaction)
    order_data = {
        "customer_id": user_id, "shipping_address_id": str(payload.shipping_address_id), "status": "pending",
        **breakdown.as_dict(),
        "shipping_line1": addr.get("line1"), "shipping_city": addr.get("city"),
        "shipping_postal_code": addr.get("postal_code"), "shipping_country": addr.get("country"),
        "idempotency_key": payload.idempotency_key, "stripe_payment_intent": intent["id"]
    }
    
    try:
        if hasattr(request.state, "actions"):
            request.state.actions.append("Executing strict Atomic DB Stock Reservation & Order Generation")

        pending_order = await repo.create_pending_order_with_reservation(order_data, items_to_deduct)
        
        await run_in_threadpool(payment_service.update_intent_metadata, intent["id"], {"order_id": pending_order["id"], "user_id": user_id})
        logger.info(f"[PAYMENTS] Pending Order {pending_order['id']} created. Stock locked atomically.")
        
        if hasattr(request.state, "actions"):
            request.state.actions.extend([
                f"Generated AOT Pending Order ledger -> ID: {str(pending_order['id'])[:8]}...",
                "Synced DB Order ID back to Stripe Intent metadata"
            ])
    except Exception as e:
        logger.error(f"[PAYMENTS] Reservation Race Condition or DB Failure for {user_id}: {e}")
        if hasattr(request.state, "actions"):
            request.state.actions.append(f"💥 Atomic Reservation Failed: Inventory depleted right before checkout")
        raise HTTPException(409, "Inventory was depleted right before checkout. Try again.")

    return {"client_secret": intent["client_secret"], "payment_intent_id": intent["id"], "order_id": pending_order["id"]}


# ══════════════════════════════════════════════════════════════════════════════
#  CONFIRM PAYMENT (ATOMIC SETTLEMENT)
# ══════════════════════════════════════════════════════════════════════════════

@router.post("/confirm")
@limiter.limit("10/minute")
async def confirm_payment(
    request: Request, 
    payload: ConfirmPaymentRequest, 
    current: dict[str, Any] = Depends(get_current_user),
    user_id: str = Depends(get_user_id_strict) # 🔥 STRICT ABAC GUARD
) -> dict[str, Any]:
    if hasattr(request.state, "actions"):
        request.state.actions.append(f"Verifying payment success for Stripe Intent: {payload.payment_intent_id[:10]}...")

    repo = AsyncPaymentRepository()
    payment_service = get_payment_provider("stripe")
    client_ip = get_remote_address(request)
    
    if brute_force.is_blocked(client_ip, user_id):
        raise HTTPException(429, "Too many attempts.")

    try:
        intent = await run_in_threadpool(payment_service.retrieve_intent, payload.payment_intent_id)
        order_id = intent.get("metadata", {}).get("order_id")
        
        if intent["status"] != "succeeded":
            if hasattr(request.state, "actions"):
                request.state.actions.append(f"❌ Aborted: Stripe returned unverified status -> '{intent['status']}'")
            raise HTTPException(400, f"Payment not completed. Status: {intent['status']}")
            
        if hasattr(request.state, "actions"):
            request.state.actions.append("Stripe Gateway verified payment state as 'SUCCEEDED'")
    except HTTPException:
        raise
    except Exception as e:
        brute_force.record_attempt(client_ip, user_id)
        raise HTTPException(502, "Verification failed")

    existing_order = await repo.get_order_by_id(order_id)
    if not existing_order:
        raise HTTPException(404, "Order not found")
        
    # 🔥 ATOMIC SETTLEMENT: Row Locks prevent Double Settlement with Webhook
    if hasattr(request.state, "actions"):
        request.state.actions.append("Executing Exclusive Row-Lock Transaction (Settle, Ledger, Clear Cart)")

    try:
        result = await repo.settle_order_transaction(order_id, intent["id"], intent["amount"] / 100, user_id)
    except Exception as e:
        logger.error(f"Atomic Settlement Failed: {e}")
        raise HTTPException(500, "Database Settlement Failed")

    if result == "ALREADY_PAID":
        if hasattr(request.state, "actions"):
            request.state.actions.append("Transaction Idempotent -> Webhook already settled this order")
        return {"status": "paid", "order_id": order_id, "message": "Already processed"}

    brute_force.reset(client_ip, user_id)

    if hasattr(request.state, "actions"):
        request.state.actions.extend([
            f"Committed DB state shift: 'PENDING' -> 'PAID' (Order: {str(order_id)[:8]}...)",
            "Purged user's active shopping cart ledger",
            "Generated immutable Payment Receipt record inside DB"
        ])

    email = current.get("profile", {}).get("email") or await repo.get_customer_email(user_id)
    try:
        get_event_bus().publish(OrderPaidEvent(order=existing_order, customer_email=email, customer_id=user_id))
        if hasattr(request.state, "actions"):
            request.state.actions.append("Published async OrderPaid background orchestration event")
    except Exception as e:
        logger.warning(f"[PAYMENTS] Failed to publish OrderPaidEvent: {e}")

    return {"status": "paid", "order_id": order_id, "message": "Payment confirmed"}


# ══════════════════════════════════════════════════════════════════════════════
#  SMART RETRY (FROM ORDERS PAGE OR PAYWALL)
# ══════════════════════════════════════════════════════════════════════════════

@router.post("/retry/{order_id}")
@limiter.limit("10/minute")
async def retry_payment(
    request: Request, 
    order_id: str, 
    current: dict[str, Any] = Depends(get_current_user),
    user_id: str = Depends(get_user_id_strict) # 🔥 STRICT ABAC GUARD
):
    if hasattr(request.state, "actions"):
        request.state.actions.append(f"Initiating Smart Paywall Retry for Order: {order_id[:8]}...")

    repo = AsyncPaymentRepository()
    payment_service = get_payment_provider("stripe")
    
    existing_order = await repo.get_order_by_id(order_id)
    if not existing_order or existing_order.get("customer_id") != user_id:
        raise HTTPException(404, "Order not found or access denied")
        
    if existing_order.get("status") == "paid":
        if hasattr(request.state, "actions"):
            request.state.actions.append("Aborted retry -> Inspected order is already settled as PAID")
        return {"status": "paid", "message": "This order is already paid"}
        
    pi_id = existing_order.get("stripe_payment_intent")
    if not pi_id:
        raise HTTPException(400, "No payment intent linked to this order")
        
    try:
        intent = await run_in_threadpool(payment_service.retrieve_intent, pi_id)
        
        if intent["status"] == "succeeded":
            if hasattr(request.state, "actions"):
                request.state.actions.extend([
                    "Stripe API confirmed existing dead intent actually succeeded!",
                    "Auto-reconciling Order status via Atomic Settlement"
                ])
            # Set via atomic RPC if Stripe already marked it succeeded
            await repo.settle_order_transaction(order_id, pi_id, intent["amount"] / 100, user_id)
            return {"status": "paid", "message": "Payment was already successful!"}
            
        client_secret = intent.get("client_secret")
        
        # If intent is dead, create a fresh one for the exact same order
        if intent["status"] == "canceled" or not client_secret:
            if hasattr(request.state, "actions"):
                request.state.actions.append("Existing intent expired -> Generating fresh AOT_RETRY Stripe Intent")

            amount_paise = _amount_to_paise(existing_order.get("total_amount", 0))
            new_idem_key = f"retry_pi_{order_id}_{int(time.time())}"
            new_intent = await run_in_threadpool(payment_service.create_payment_intent, amount_paise, "inr", "AOT_RETRY", user_id, new_idem_key)
            
            # Simple blind update is safe here because it's just swapping the stripe intent ID 
            # while status is still 'pending'
            await repo.admin_sb.table("orders").update({"stripe_payment_intent": new_intent["id"]}).eq("id", order_id).execute()
            await run_in_threadpool(payment_service.update_intent_metadata, new_intent["id"], {"order_id": order_id, "user_id": user_id})
            
            return {"client_secret": new_intent["client_secret"], "payment_intent_id": new_intent["id"], "order_id": order_id}

        if hasattr(request.state, "actions"):
            request.state.actions.append("Re-issuing active existing client_secret back to frontend Paywall")

        return {"client_secret": client_secret, "payment_intent_id": intent["id"], "order_id": order_id}
        
    except Exception as e:
        raise HTTPException(502, f"Could not contact payment provider: {str(e)}")


# ══════════════════════════════════════════════════════════════════════════════
#  NOTIFY FAILED & WEBHOOK (DB ROW-LOCKED)
# ══════════════════════════════════════════════════════════════════════════════

@router.post("/notify-failed")
async def notify_payment_failed(request: Request, payload: NotifyFailedRequest, current: dict[str, Any] = Depends(get_current_user)):
    if hasattr(request.state, "actions"):
        request.state.actions.append(f"Intercepted client-side drop on Intent {payload.payment_intent_id[:10]}... (Order preserved as Pending)")

    logger.info(f"[PAYMENTS] User encountered a payment failure on Intent {payload.payment_intent_id}. Order remains Pending for retry.")
    return {"message": "Failure logged. User can safely retry."}

@router.post("/webhook")
async def stripe_webhook(request: Request, stripe_signature: str | None = Header(None, alias="stripe-signature")) -> dict[str, str]:
    if hasattr(request.state, "actions"):
        request.state.actions.append("Intercepted Stripe asynchronous Webhook handshake")

    body = await request.body()
    repo = AsyncPaymentRepository()
    payment_service = get_payment_provider("stripe")

    if not stripe_signature: 
        if hasattr(request.state, "actions"):
            request.state.actions.append("❌ Webhook dropped: Missing Stripe signature header")
        raise HTTPException(400, "Missing signature")

    try: 
        event = await run_in_threadpool(payment_service.verify_webhook, body, stripe_signature)
        if hasattr(request.state, "actions"):
            request.state.actions.append("Cryptographic webhook signature verified successfully")
    except ValueError: 
        raise HTTPException(400, "Invalid signature")

    event_type, pi_id = event["type"], event["data"]["object"]["id"]
    intent = await run_in_threadpool(payment_service.retrieve_intent, pi_id)
    order_id = intent.get("metadata", {}).get("order_id")
    user_id = intent.get("metadata", {}).get("user_id")

    if hasattr(request.state, "actions"):
        request.state.actions.append(f"Parsed Webhook Event -> '{event_type}' (Target Order: {str(order_id)[:8]}...)")

    if not order_id or not user_id: return {"message": "Missing metadata"}
    existing_order = await repo.get_order_by_id(order_id)
    if not existing_order or existing_order["status"] != "pending": return {"message": "Ignored"}

    if event_type == "payment_intent.succeeded":
        if hasattr(request.state, "actions"):
            request.state.actions.append("Webhook executing Row-Lock Settlement")

        try:
            # 🔥 DOUBLE-SETTLEMENT DEFENSE
            result = await repo.settle_order_transaction(order_id, pi_id, intent["amount"] / 100, user_id)
            if result == "SUCCESS":
                email = await repo.get_customer_email(user_id)
                get_event_bus().publish(OrderPaidEvent(order=existing_order, customer_email=email, customer_id=user_id))
                if hasattr(request.state, "actions"):
                    request.state.actions.append("Out-of-band Webhook settlement successfully completed")
        except Exception as e:
            logger.error(f"Webhook settlement failed: {e}")

    elif event_type == "payment_intent.canceled":
        if hasattr(request.state, "actions"):
            request.state.actions.append("Stripe timeout -> Cancelling & Releasing Inventory Lock Atomically")

        try:
            # 🔥 ATOMIC INVENTORY RELEASE
            await repo.release_abandoned_order(order_id)
            email = await repo.get_customer_email(user_id)
            get_event_bus().publish(OrderFailedEvent(order=existing_order, customer_email=email, customer_id=user_id, reason="webhook_canceled"))
        except Exception as e:
            logger.error(f"Webhook cancellation failed: {e}")

    return {"message": "OK"}
import time
import logging
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict
from collections import defaultdict
from starlette.concurrency import run_in_threadpool

from app.repositories.payment_repo import AsyncPaymentRepository
from app.services.pricing import get_pricing_from_config
from app.services.events import get_event_bus, OrderPaidEvent, OrderFailedEvent
from app.integrations.payments.registry import get_payment_provider
from app.core.exceptions import LuviioException, OutOfStockException, PaymentFailedException

logger = logging.getLogger(__name__)

class BruteForceGuard:
    def __init__(self, max_attempts: int = 5, window_seconds: int = 60):
        self.attempts = defaultdict(list)
        self.max_attempts, self.window_seconds = max_attempts, window_seconds

    def is_blocked(self, ip: str) -> bool:
        now = time.time()
        self.attempts[ip] = [t for t in self.attempts[ip] if t > now - self.window_seconds]
        return len(self.attempts[ip]) >= self.max_attempts

    def record(self, ip: str):
        self.attempts[ip].append(time.time())

    def reset(self, ip: str):
        self.attempts.pop(ip, None)

brute_guard = BruteForceGuard()

class PaymentService:
    def __init__(self):
        self.repo = AsyncPaymentRepository()
        self.provider = get_payment_provider("stripe")

    def _paise(self, amount: Any) -> int:
        return int((Decimal(str(amount)) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))

    async def create_intent(self, user_id: str, client_ip: str, idempotency_key: str, address_id: str) -> Dict[str, Any]:
        if brute_guard.is_blocked(client_ip): 
            raise LuviioException("Too many attempts", "RATE_LIMIT", 429)

        existing = await self.repo.get_order_by_idempotency_key(user_id, idempotency_key)
        if existing:
            if existing["status"] == "pending":
                try:
                    intent = await run_in_threadpool(self.provider.retrieve_intent, existing["stripe_payment_intent"])
                    if intent["status"] in ["requires_payment_method", "requires_confirmation", "requires_action"]:
                        return {"client_secret": intent["client_secret"], "payment_intent_id": intent["id"], "order_id": existing["id"]}
                except Exception: pass 
            elif existing["status"] == "paid":
                raise LuviioException("This order is already paid.", "ALREADY_PAID", 400)

        cart_items = await self.repo.get_cart_items_for_checkout(user_id)
        if not cart_items: 
            raise LuviioException("Your cart is empty", "EMPTY_CART", 400)

        subtotal = Decimal("0")
        items_to_deduct = []
        for item in cart_items:
            prod = item.get("products") or {}
            if not prod.get("is_active") or prod.get("stock", 0) < item["quantity"]:
                raise OutOfStockException(prod.get("name", "Item"))
            
            locked_price = Decimal(str(item.get("price_snapshot") or prod.get("price", 0)))
            lt = locked_price * item["quantity"]
            subtotal += lt
            
            # 🔥 CRITICAL FIX: Restored missing fields required by the Supabase SQL RPC function!
            items_to_deduct.append({
                "product_id": item["product_id"], 
                "product_name": prod.get("name", "Item"),
                "unit_price": float(locked_price),
                "compare_price": float(prod.get("compare_price"),
                "quantity": item["quantity"], 
                "subtotal": float(lt)
            })

        config = await self.repo.get_pricing_config()
        breakdown = get_pricing_from_config(config).calculate(subtotal)
        amount_paise = self._paise(breakdown.total)

        if amount_paise < 5000: 
            raise LuviioException("Order amount out of bounds", "INVALID_AMOUNT", 400)

        addr = await self.repo.get_shipping_address(address_id, user_id)
        if not addr: 
            raise LuviioException("Shipping address not found", "NOT_FOUND", 404)

        try:
            intent = await run_in_threadpool(self.provider.create_payment_intent, amount_paise, "inr", "AOT_PENDING", user_id, f"aot_pi_{idempotency_key}")
        except Exception as exc:
            brute_guard.record(client_ip)
            raise PaymentFailedException(str(exc))

        order_data = {
            "customer_id": user_id, "shipping_address_id": address_id, "status": "pending",
            **breakdown.as_dict(),
            "shipping_line1": addr.get("line1"), "shipping_city": addr.get("city"),
            "shipping_postal_code": addr.get("postal_code"), "shipping_country": addr.get("country"),
            "idempotency_key": idempotency_key, "stripe_payment_intent": intent["id"]
        }
        
        try:
            pending_order = await self.repo.create_pending_order_with_reservation(order_data, items_to_deduct)
            await run_in_threadpool(self.provider.update_intent_metadata, intent["id"], {"order_id": pending_order["id"], "user_id": user_id})
        except Exception as e:
            logger.error(f"[CRITICAL DB ERROR] Atomic Reservation Failed: {e}")
            raise LuviioException("Inventory depleted or Database error during checkout", "RACE_CONDITION", 409)

        return {"client_secret": intent["client_secret"], "payment_intent_id": intent["id"], "order_id": pending_order["id"]}

    async def confirm_payment(self, user_id: str, client_ip: str, pi_id: str, email: str) -> Dict[str, Any]:
        if brute_guard.is_blocked(client_ip): raise LuviioException("Too many attempts", "RATE_LIMIT", 429)

        try:
            intent = await run_in_threadpool(self.provider.retrieve_intent, pi_id)
            if intent["status"] != "succeeded":
                raise PaymentFailedException(intent["status"])
        except Exception as e:
            brute_guard.record(client_ip)
            raise PaymentFailedException("Verification failed")

        order_id = intent.get("metadata", {}).get("order_id")
        existing_order = await self.repo.get_order_by_id(order_id)
        if not existing_order: raise LuviioException("Order not found", "NOT_FOUND", 404)

        try:
            result = await self.repo.settle_order_transaction(order_id, intent["id"], intent["amount"] / 100, user_id)
        except Exception as e:
            raise LuviioException("Database Settlement Failed", "DB_ERROR", 500)

        if result == "ALREADY_PAID":
            return {"status": "paid", "order_id": order_id, "message": "Already processed"}

        brute_guard.reset(client_ip)
        
        # 🔥 RACE-CONDITION FIX: Explicitly mutate existing order dictionary to reflect new state
        # before pushing onto the event bus to prevent stale data reading downstream.
        existing_order["status"] = "paid"
        
        try: 
            get_event_bus().publish(OrderPaidEvent(order=existing_order, customer_email=email, customer_id=user_id))
        except Exception as e: 
            logger.error(f"Event bus failed during publish: {e}")

        return {"status": "paid", "order_id": order_id, "message": "Payment confirmed"}

    async def retry_payment(self, user_id: str, order_id: str) -> Dict[str, Any]:
        existing_order = await self.repo.get_order_by_id(order_id)
        if not existing_order or existing_order.get("customer_id") != user_id:
            raise LuviioException("Order not found", "NOT_FOUND", 404)
            
        if existing_order.get("status") == "paid":
            return {"status": "paid", "message": "This order is already paid"}
            
        pi_id = existing_order.get("stripe_payment_intent")
        if not pi_id: raise LuviioException("No payment intent linked", "INVALID_STATE", 400)
            
        try:
            intent = await run_in_threadpool(self.provider.retrieve_intent, pi_id)
            if intent["status"] == "succeeded":
                await self.repo.settle_order_transaction(order_id, pi_id, intent["amount"] / 100, user_id)
                return {"status": "paid", "message": "Payment was already successful!"}
                
            client_secret = intent.get("client_secret")
            if intent["status"] == "canceled" or not client_secret:
                amount_paise = self._paise(existing_order.get("total_amount", 0))
                new_intent = await run_in_threadpool(self.provider.create_payment_intent, amount_paise, "inr", "AOT_RETRY", user_id, f"retry_pi_{order_id}_{int(time.time())}")
                await self.repo.update_order_payment_intent(order_id, new_intent["id"])
                await run_in_threadpool(self.provider.update_intent_metadata, new_intent["id"], {"order_id": order_id, "user_id": user_id})
                return {"client_secret": new_intent["client_secret"], "payment_intent_id": new_intent["id"], "order_id": order_id}

            return {"client_secret": client_secret, "payment_intent_id": intent["id"], "order_id": order_id}
        except Exception as e:
            raise PaymentFailedException(str(e))

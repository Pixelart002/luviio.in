"""
Payment Service — Enterprise Gateway Engine & Brute-Force Guard
===============================================================
Path: app/services/payment_service.py
"""
import time
import logging
from uuid import UUID
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict
from collections import defaultdict
from fastapi import HTTPException, status
from starlette.concurrency import run_in_threadpool

from app.repositories.payment_repo import AsyncPaymentRepository
from app.permissions.policies.payment_policies import PaymentPolicy
from app.services.pricing import get_pricing_from_config
from app.services.events import get_event_bus, OrderPaidEvent
from app.integrations.payments.registry import get_payment_provider
from app.constants.payment_messages import PaymentMessages, PaymentSecurityMessages

logger = logging.getLogger(__name__)

class BruteForceGuard:
    """In-memory sliding window defense against payment gateway enumeration."""
    def __init__(self, max_attempts: int = 5, window_seconds: int = 60):
        self.attempts = defaultdict(list)
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds

    def assert_safe(self, ip: str) -> None:
        now = time.time()
        self.attempts[ip] = [t for t in self.attempts[ip] if t > now - self.window_seconds]
        if len(self.attempts[ip]) >= self.max_attempts:
            raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=PaymentSecurityMessages.RATE_LIMIT_EXCEEDED)

    def record(self, ip: str): self.attempts[ip].append(time.time())
    def reset(self, ip: str): self.attempts.pop(ip, None)

brute_guard = BruteForceGuard()

class PaymentService:
    def __init__(self):
        self.repo = AsyncPaymentRepository()
        self.provider = get_payment_provider("stripe")

    def _paise(self, amount: Any) -> int:
        return int((Decimal(str(amount)) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))

    async def create_intent(self, user_id: str, client_ip: str, idempotency_key: str, address_id: str) -> Dict[str, Any]:
        brute_guard.assert_safe(client_ip)

        existing = await self.repo.get_order_by_idempotency_key(user_id, idempotency_key)
        if existing:
            if existing["status"] == "pending":
                try:
                    intent = await run_in_threadpool(self.provider.retrieve_intent, existing["stripe_payment_intent"])
                    if intent["status"] in ["requires_payment_method", "requires_confirmation", "requires_action"]:
                        return {"client_secret": intent["client_secret"], "payment_intent_id": intent["id"], "order_id": existing["id"]}
                    else:
                        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=PaymentSecurityMessages.INTENT_STATE_ERROR)
                except HTTPException as he: raise he
                except Exception as exc:
                    logger.error("Failed to retrieve Stripe intent for order %s: %s", existing['id'], exc)
                    raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=PaymentSecurityMessages.PAYMENT_FAILED)
            elif existing["status"] == "paid":
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=PaymentSecurityMessages.ALREADY_PAID)
            else:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=PaymentSecurityMessages.DUPLICATE_ORDER)

        cart_items = await self.repo.get_cart_items_for_checkout(user_id)
        if not cart_items: 
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=PaymentSecurityMessages.EMPTY_CART)

        subtotal = Decimal("0")
        items_to_deduct = []
        for item in cart_items:
            prod = item.get("products") or {}
            if not prod.get("is_active") or prod.get("stock", 0) < item["quantity"]:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Item out of stock: {prod.get('name', 'Unknown')}")
            
            locked_price = Decimal(str(item.get("price_snapshot") or prod.get("price", 0)))
            lt = locked_price * item["quantity"]
            subtotal += lt
            
            items_to_deduct.append({
                "product_id": item["product_id"], 
                "product_name": prod.get("name", "Item"),
                "unit_price": float(locked_price),
                "compare_price": float(prod.get("compare_price") or 0.0),
                "quantity": item["quantity"], 
                "subtotal": float(lt)
            })

        config = await self.repo.get_pricing_config()
        breakdown = get_pricing_from_config(config).calculate(subtotal)
        amount_paise = self._paise(breakdown.total)

        if amount_paise < 5000: 
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=PaymentSecurityMessages.INVALID_AMOUNT)

        addr = await self.repo.get_shipping_address(address_id, user_id)
        if not addr: 
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=PaymentSecurityMessages.ADDRESS_NOT_FOUND)

        try:
            intent = await run_in_threadpool(self.provider.create_payment_intent, amount_paise, "inr", "AOT_PENDING", user_id, f"aot_pi_{idempotency_key}")
        except Exception as exc:
            brute_guard.record(client_ip)
            logger.error("Stripe Intent Creation Failed: %s", exc)
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=PaymentSecurityMessages.PAYMENT_FAILED)

        order_data = {
            "customer_id": user_id, "shipping_address_id": address_id, "status": "pending",
            **breakdown.as_dict(),
            "shipping_line1": addr.get("line1"), "shipping_city": addr.get("city"),
            "shipping_postal_code": addr.get("postal_code"), "shipping_country": addr.get("country"),
            "idempotency_key": str(UUID(idempotency_key)), "stripe_payment_intent": intent["id"]
        }
        
        try:
            pending_order = await self.repo.create_pending_order_with_reservation(order_data, items_to_deduct)
            await run_in_threadpool(self.provider.update_intent_metadata, intent["id"], {"order_id": pending_order["id"], "user_id": user_id})
        except Exception as e:
            logger.error("CRITICAL DB ERROR - Atomic Reservation Failed: %s", e)
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Inventory depleted or checkout race condition detected.")

        return {"client_secret": intent["client_secret"], "payment_intent_id": intent["id"], "order_id": pending_order["id"]}

    async def confirm_payment(self, user_id: str, client_ip: str, pi_id: str, email: str) -> Dict[str, Any]:
        brute_guard.assert_safe(client_ip)

        try:
            intent = await run_in_threadpool(self.provider.retrieve_intent, pi_id)
            if intent["status"] != "succeeded":
                raise HTTPException(status_code=status.HTTP_402_PAYMENT_REQUIRED, detail=PaymentSecurityMessages.PAYMENT_FAILED)
        except HTTPException as he: raise he
        except Exception as e:
            brute_guard.record(client_ip)
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=PaymentSecurityMessages.PAYMENT_FAILED)

        # Secure Metadata Extraction (Tamper-Proof)
        order_id = intent.get("metadata", {}).get("order_id")
        raw_order = await self.repo.get_order_by_id(order_id)
        
        # Enforce ABAC Policies (Ownership & State)
        PaymentPolicy.assert_can_process_payment(raw_order, user_id)

        try:
            result = await self.repo.settle_order_transaction(order_id, intent["id"], intent["amount"] / 100, user_id)
        except Exception as e:
            logger.error("Database Settlement Failed for order %s: %s", order_id, e)
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=PaymentSecurityMessages.DB_SETTLEMENT_ERROR)

        if result == "ALREADY_PAID":
            return {"status": "paid", "order_id": order_id, "message": PaymentMessages.PAYMENT_ALREADY_SETTLED}

        brute_guard.reset(client_ip)
        raw_order["status"] = "paid"
        
        try: 
            get_event_bus().publish(OrderPaidEvent(order=raw_order, customer_email=email, customer_id=user_id))
        except Exception as e: 
            logger.error("Event bus failed during publish: %s", e)

        return {"status": "paid", "order_id": order_id, "message": PaymentMessages.PAYMENT_CONFIRMED}

    async def retry_payment(self, user_id: str, order_id: str) -> Dict[str, Any]:
        raw_order = await self.repo.get_order_by_id(order_id)
        
        # Enforce ABAC Policies
        existing_order = PaymentPolicy.assert_can_process_payment(raw_order, user_id)
            
        pi_id = existing_order.get("stripe_payment_intent")
        if not pi_id: 
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=PaymentSecurityMessages.MISSING_INTENT_LINK)
            
        try:
            intent = await run_in_threadpool(self.provider.retrieve_intent, pi_id)
            if intent["status"] == "succeeded":
                await self.repo.settle_order_transaction(order_id, pi_id, intent["amount"] / 100, user_id)
                return {"status": "paid", "order_id": order_id, "message": PaymentMessages.RETRY_SUCCESSFUL}
                
            client_secret = intent.get("client_secret")
            if intent["status"] == "canceled" or not client_secret:
                amount_paise = self._paise(existing_order.get("total_amount", 0))
                new_intent = await run_in_threadpool(self.provider.create_payment_intent, amount_paise, "inr", "AOT_RETRY", user_id, f"retry_pi_{order_id}_{int(time.time())}")
                await self.repo.update_order_payment_intent(order_id, new_intent["id"])
                await run_in_threadpool(self.provider.update_intent_metadata, new_intent["id"], {"order_id": order_id, "user_id": user_id})
                return {"client_secret": new_intent["client_secret"], "payment_intent_id": new_intent["id"], "order_id": order_id}

            return {"client_secret": client_secret, "payment_intent_id": intent["id"], "order_id": order_id}
        except Exception as e:
            logger.error("Retry payment intent generation failed: %s", e)
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=PaymentSecurityMessages.PAYMENT_FAILED)
"""
Payment Service — Enterprise Orchestration (With Atomic GST & HSN Snapshots)
============================================================================
Path: /app/services/payments/service.py
"""
import time
import logging
from uuid import UUID
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict
from collections import defaultdict
from fastapi import HTTPException, status
from starlette.concurrency import run_in_threadpool
from nanoid import generate  # 🔥 FIX: Added NanoID for clean Order Numbers

from app.repositories.payment_repo import AsyncPaymentRepository
from app.services.pricing import get_pricing_from_config
from app.events.registry import get_event_bus, OrderPaidEvent
from app.integrations.payments.registry import get_payment_provider
from app.permissions.policies.payment_policies import PaymentPolicy
from app.constants.payment_messages import PaymentMessages, PaymentSecurityMessages, PaymentRules
from app.enums.order_status import OrderStatus

logger = logging.getLogger(__name__)

class BruteForceGuard:
    """Internal memory guard to prevent gateway spamming."""
    def __init__(self):
        self.attempts = defaultdict(list)

    def assert_safe(self, ip: str) -> None:
        now = time.time()
        self.attempts[ip] = [t for t in self.attempts[ip] if t > now - PaymentRules.BRUTE_FORCE_WINDOW_SEC]
        if len(self.attempts[ip]) >= PaymentRules.BRUTE_FORCE_MAX_ATTEMPTS:
            raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=PaymentSecurityMessages.RATE_LIMIT)

    def record(self, ip: str): self.attempts[ip].append(time.time())
    def reset(self, ip: str): self.attempts.pop(ip, None)

brute_guard = BruteForceGuard()

class PaymentService:
    def __init__(self):
        self.repo = AsyncPaymentRepository()
        self.provider = get_payment_provider("stripe")

    def _paise(self, amount: Any) -> int:
        return int((Decimal(str(amount)) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))

    def _generate_clean_order_number(self) -> str:
        """Generates Amazon-style readable ID excluding ambiguous letters (0, O, 1, I)."""
        short_id = generate('23456789ABCDEFGHJKLMNPQRSTUVWXYZ', 8)
        return f"ORD-{short_id[:4]}-{short_id[4:]}"

    async def create_intent(self, user_id: str, client_ip: str, idempotency_key: str, address_id: str) -> Dict[str, Any]:
        # 🛡️ 1. Security Check (Gateway Spamming)
        brute_guard.assert_safe(client_ip)

        # 🛡️ 2. Idempotency & State Machine Check
        existing = await self.repo.get_order_by_idempotency_key(user_id, idempotency_key)
        if existing:
            if existing["status"] == OrderStatus.PENDING.value:
                try:
                    intent = await run_in_threadpool(self.provider.retrieve_intent, existing["stripe_payment_intent"])
                    if intent["status"] in ["requires_payment_method", "requires_confirmation", "requires_action"]:
                        return {"client_secret": intent["client_secret"], "payment_intent_id": intent["id"], "order_id": existing["id"]}
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT, 
                        detail=PaymentSecurityMessages.INTENT_STATE_ERROR.format(status=intent['status'])
                    )
                except HTTPException: raise
                except Exception as exc:
                    logger.error(f"[PAYMENT ERROR] Stripe retrieval failed: {exc}")
                    raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=PaymentSecurityMessages.PAYMENT_FAILED)
            elif existing["status"] == OrderStatus.PAID.value:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=PaymentSecurityMessages.ALREADY_PAID)
            else:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=PaymentSecurityMessages.DUPLICATE_ORDER)

        # 🚀 INVENTORY EXHAUSTION GUARD
        has_pending = await self.repo.has_active_pending_order(user_id)
        PaymentPolicy.assert_no_active_pending_order(has_pending)

        # 🛡️ 4. Cart & Stock Policies
        cart_items = await self.repo.get_cart_items_for_checkout(user_id)
        PaymentPolicy.assert_valid_cart(cart_items)

        subtotal = Decimal("0")
        items_to_deduct = []
        
        for item in cart_items:
            prod = item.get("products") or {}
            PaymentPolicy.assert_stock_availability(item["quantity"], prod)
            
            locked_price = Decimal(str(item.get("price_snapshot") or prod.get("price", 0)))
            lt = locked_price * item["quantity"]
            subtotal += lt
            
            # 🔥 UPGRADE: Include HSN Code & GST Percentage for atomic database snapshot!
            hsn_code = str(prod.get("hsn_code") or item.get("hsn_code") or "9988").strip()
            gst_percentage = int(prod.get("gst_percentage") if prod.get("gst_percentage") is not None else (item.get("gst_percentage") if item.get("gst_percentage") is not None else 18))

            items_to_deduct.append({
                "product_id": item["product_id"], 
                "product_name": prod.get("name", "Item"),
                "hsn_code": hsn_code,              # <-- Added for RPC snapshot
                "gst_percentage": gst_percentage,  # <-- Added for RPC snapshot
                "unit_price": float(locked_price),
                "compare_price": float(prod.get("compare_price") or 0.0),
                "quantity": item["quantity"], 
                "subtotal": float(lt)
            })

        # 🛡️ 5. Pricing & Limits Policy
        config = await self.repo.get_pricing_config()
        # 🔥 UPGRADE: Pass items=items_to_deduct so PricingEngine calculates exact item-by-item tax!
        breakdown = get_pricing_from_config(config).calculate(items=items_to_deduct)
        amount_paise = self._paise(breakdown.total)
        
        PaymentPolicy.assert_minimum_amount(amount_paise)

        addr = await self.repo.get_shipping_address(address_id, user_id)
        if not addr: 
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=PaymentSecurityMessages.ADDRESS_NOT_FOUND)

        # 6. Execute Provider (Stripe)
        try:
            intent = await run_in_threadpool(self.provider.create_payment_intent, amount_paise, "inr", "AOT_PENDING", user_id, f"aot_pi_{idempotency_key}")
        except Exception as exc:
            brute_guard.record(client_ip)
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=PaymentSecurityMessages.PAYMENT_FAILED)

        # 🔥 FIX: Attached clean human-readable order_number
        order_number = self._generate_clean_order_number()

        order_data = {
            "customer_id": user_id, "shipping_address_id": address_id, "status": OrderStatus.PENDING.value,
            "order_number": order_number,
            **breakdown.as_dict(),
            "shipping_line1": addr.get("line1"), "shipping_city": addr.get("city"),
            "shipping_postal_code": addr.get("postal_code"), "shipping_country": addr.get("country"),
            "idempotency_key": str(UUID(idempotency_key)), "stripe_payment_intent": intent["id"]
        }
        
        # 7. Atomic RPC Execution
        try:
            pending_order = await self.repo.create_pending_order_with_reservation(order_data, items_to_deduct)
            await run_in_threadpool(self.provider.update_intent_metadata, intent["id"], {"order_id": pending_order["id"], "user_id": user_id})
        except Exception as e:
            logger.error(f"[CRITICAL DB ERROR] Atomic Reservation Failed: {e}")
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=PaymentSecurityMessages.RACE_CONDITION)

        return {"client_secret": intent["client_secret"], "payment_intent_id": intent["id"], "order_id": pending_order["id"], "order_number": order_number}

    async def confirm_payment(self, user_id: str, client_ip: str, pi_id: str, email: str) -> Dict[str, Any]:
        brute_guard.assert_safe(client_ip)

        try:
            intent = await run_in_threadpool(self.provider.retrieve_intent, pi_id)
            if intent["status"] != "succeeded":
                raise HTTPException(status_code=status.HTTP_402_PAYMENT_REQUIRED, detail=PaymentSecurityMessages.PAYMENT_FAILED)
        except HTTPException: raise
        except Exception:
            brute_guard.record(client_ip)
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=PaymentSecurityMessages.PAYMENT_FAILED)

        order_id = intent.get("metadata", {}).get("order_id")
        existing_order = await self.repo.get_order_by_id(order_id)
        
        PaymentPolicy.assert_can_confirm(existing_order, user_id)

        try:
            result = await self.repo.settle_order_transaction(order_id, intent["id"], intent["amount"] / 100, user_id)
        except Exception:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=PaymentSecurityMessages.RACE_CONDITION)

        if result == "ALREADY_PAID":
            return {"status": OrderStatus.PAID.value, "order_id": order_id, "message": PaymentMessages.ALREADY_SETTLED}

        brute_guard.reset(client_ip)
        existing_order["status"] = OrderStatus.PAID.value
        
        try: get_event_bus().publish(OrderPaidEvent(order=existing_order, customer_email=email, customer_id=user_id))
        except Exception as e: logger.error(f"Event bus failed: {e}")

        return {"status": OrderStatus.PAID.value, "order_id": order_id, "message": PaymentMessages.CONFIRMED}

    async def retry_payment(self, user_id: str, order_id: str) -> Dict[str, Any]:
        existing_order = await self.repo.get_order_by_id(order_id)
        PaymentPolicy.assert_can_retry(existing_order, user_id)
            
        if existing_order.get("status") == OrderStatus.PAID.value:
            return {"status": OrderStatus.PAID.value, "message": PaymentMessages.RETRY_SUCCESSFUL}
            
        pi_id = existing_order.get("stripe_payment_intent")
            
        try:
            intent = await run_in_threadpool(self.provider.retrieve_intent, pi_id)
            if intent["status"] == "succeeded":
                await self.repo.settle_order_transaction(order_id, pi_id, intent["amount"] / 100, user_id)
                return {"status": OrderStatus.PAID.value, "message": PaymentMessages.RETRY_SUCCESSFUL}
                
            client_secret = intent.get("client_secret")
            if intent["status"] == "canceled" or not client_secret:
                amount_paise = self._paise(existing_order.get("total_amount", 0))
                new_intent = await run_in_threadpool(self.provider.create_payment_intent, amount_paise, "inr", "AOT_RETRY", user_id, f"retry_pi_{order_id}_{int(time.time())}")
                await self.repo.update_order_payment_intent(order_id, new_intent["id"])
                await run_in_threadpool(self.provider.update_intent_metadata, new_intent["id"], {"order_id": order_id, "user_id": user_id})
                return {"client_secret": new_intent["client_secret"], "payment_intent_id": new_intent["id"], "order_id": order_id}

            return {"client_secret": client_secret, "payment_intent_id": intent["id"], "order_id": order_id}
        except Exception:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=PaymentSecurityMessages.PAYMENT_FAILED)
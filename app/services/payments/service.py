"""
Payment Service -- Enterprise Orchestration (With Atomic GST & HSN Snapshots)
=============================================================================
Path: app/services/payments/service.py

Architecture & Fixes:
  * Cart Lifecycle: Cart is cleared immediately upon successful atomic order creation & stock reservation.
  * Self-Healing Retry Logic: Auto-generates fresh Stripe intents for unlinked/canceled orders.
  * Atomic GST & HSN Snapshots: Locks exact legal inventory prices & tax rates at checkout.
  * Router-Level Limiting: Removed unsafe in-memory limiters; delegates rate mitigation to slowapi.
  * Idempotent Checkout: Prevents double-charging via UUID-based idempotency keys.
  * Null Intent Guard: Prevents 502 Bad Gateway crashes when Stripe ID is None or Empty in DB.
"""
import time
import logging
from uuid import UUID
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List
from fastapi import HTTPException, status
from starlette.concurrency import run_in_threadpool
from nanoid import generate

from app.repositories.payment_repo import AsyncPaymentRepository
from app.services.pricing import get_pricing_from_config
from app.events.registry import get_event_bus, OrderPaidEvent
from app.integrations.payments.registry import get_payment_provider
from app.permissions.policies.payment_policies import PaymentPolicy
from app.constants.payment_messages import PaymentMessages, PaymentSecurityMessages, PaymentRules
from app.enums.order_status import OrderStatus

logger = logging.getLogger(__name__)


# ==============================================================================
# PAYMENT SERVICE ORCHESTRATOR
# ==============================================================================

class PaymentService:
    def __init__(self) -> None:
        self.repo = AsyncPaymentRepository()
        self.provider = get_payment_provider("stripe")

    def _paise(self, amount: Any) -> int:
        """Converts currency amount to minor units (Paise) using Banker's rounding."""
        return int((Decimal(str(amount)) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))

    def _generate_clean_order_number(self) -> str:
        """Generates Amazon-style readable ID excluding ambiguous letters (0, O, 1, I)."""
        short_id = generate('23456789ABCDEFGHJKLMNPQRSTUVWXYZ', 8)
        return f"ORD-{short_id[:4]}-{short_id[4:]}"

    # --------------------------------------------------------------------------
    # INTENT CREATION (Checkout Step 1)
    # --------------------------------------------------------------------------

    async def create_intent(self, user_id: str, client_ip: str, idempotency_key: str, address_id: str) -> Dict[str, Any]:
        # 🛡️ Step 1: Safe UUID Casting Guard (Prevent 500 Crash on malformed input)
        try:
            clean_idem_key = str(UUID(idempotency_key))
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=PaymentSecurityMessages.INVALID_IDEMPOTENCY_KEY
            )

        # 🛡️ Step 2: Idempotency & State Machine Check
        existing = await self.repo.get_order_by_idempotency_key(user_id, clean_idem_key)
        if existing:
            if existing.get("status") == OrderStatus.PENDING.value:
                existing_pi = existing.get("stripe_payment_intent")
                
                # 🔥 Null Intent Guard
                if existing_pi and isinstance(existing_pi, str) and len(existing_pi.strip()) > 0:
                    try:
                        intent = await run_in_threadpool(self.provider.retrieve_intent, existing_pi)
                        if intent.get("status") in {"requires_payment_method", "requires_confirmation", "requires_action"}:
                            return {
                                "client_secret": intent.get("client_secret"), 
                                "payment_intent_id": intent.get("id"), 
                                "order_id": existing["id"],
                                "order_number": existing.get("order_number", "")
                            }
                        raise HTTPException(
                            status_code=status.HTTP_409_CONFLICT, 
                            detail=PaymentSecurityMessages.INTENT_STATE_ERROR.format(status=intent.get('status'))
                        )
                    except HTTPException: 
                        raise
                    except Exception as exc:
                        logger.error("[PAYMENT ERROR] Stripe retrieval failed for existing order: %s", exc)
                
                # 🔥 Self-Healing: Generate fresh intent if lost
                logger.warning("[PAYMENT RECOVERY] Existing order %s lacks valid intent. Replacing...", existing['id'])
                amount_paise = self._paise(existing.get("total_amount", 0))
                if amount_paise < PaymentRules.MIN_ORDER_AMOUNT_PAISE:
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=PaymentSecurityMessages.ZERO_AMOUNT_RETRY)
                try:
                    new_intent = await run_in_threadpool(self.provider.create_payment_intent, amount_paise, "inr", "AOT_RECOVERY", user_id, f"aot_rec_{clean_idem_key}_{int(time.time())}")
                    await self.repo.update_order_payment_intent(existing["id"], new_intent["id"])
                    await run_in_threadpool(self.provider.update_intent_metadata, new_intent["id"], {"order_id": existing["id"], "user_id": user_id})
                    return {
                        "client_secret": new_intent["client_secret"], 
                        "payment_intent_id": new_intent["id"], 
                        "order_id": existing["id"],
                        "order_number": existing.get("order_number", "")
                    }
                except Exception as exc:
                    logger.error("[PAYMENT ERROR] Recovery intent creation failed: %s", exc)
                    raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=PaymentSecurityMessages.PAYMENT_FAILED) from exc

            elif existing.get("status") == OrderStatus.PAID.value:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=PaymentSecurityMessages.ALREADY_PAID)
            else:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=PaymentSecurityMessages.DUPLICATE_ORDER)

        # 🛡️ Step 3: Inventory Exhaustion & Cart Checks
        has_pending = await self.repo.has_active_pending_order(user_id)
        PaymentPolicy.assert_no_active_pending_order(has_pending)

        cart_items = await self.repo.get_cart_items_for_checkout(user_id)
        PaymentPolicy.assert_valid_cart(cart_items)

        subtotal = Decimal("0")
        items_to_deduct: List[Dict[str, Any]] = []
        
        for item in cart_items:
            prod = item.get("products") or {}
            PaymentPolicy.assert_stock_availability(item["quantity"], prod)
            
            locked_price = Decimal(str(item.get("price_snapshot") or prod.get("price", 0)))
            lt = locked_price * item["quantity"]
            subtotal += lt
            
            hsn_code = str(prod.get("hsn_code") or item.get("hsn_code") or "9988").strip()
            gst_percentage = int(prod.get("gst_percentage") if prod.get("gst_percentage") is not None else (item.get("gst_percentage") if item.get("gst_percentage") is not None else 18))

            items_to_deduct.append({
                "product_id": item["product_id"], 
                "product_name": prod.get("name", "Item"),
                "hsn_code": hsn_code,
                "gst_percentage": gst_percentage,
                "unit_price": float(locked_price),
                "compare_price": float(prod.get("compare_price") or 0.0),
                "quantity": item["quantity"], 
                "subtotal": float(lt)
            })

        config = await self.repo.get_pricing_config()
        breakdown = get_pricing_from_config(config).calculate(items=items_to_deduct)
        amount_paise = self._paise(breakdown.total)
        
        PaymentPolicy.assert_minimum_amount(amount_paise)

        addr = await self.repo.get_shipping_address(address_id, user_id)
        if not addr: 
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=PaymentSecurityMessages.ADDRESS_NOT_FOUND)

        try:
            intent = await run_in_threadpool(self.provider.create_payment_intent, amount_paise, "inr", "AOT_PENDING", user_id, f"aot_pi_{clean_idem_key}")
        except Exception as exc:
            logger.error("[PAYMENT ERROR] Initial Stripe Intent creation failed: %s", exc)
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=PaymentSecurityMessages.PAYMENT_FAILED) from exc

        order_number = self._generate_clean_order_number()

        order_data = {
            "customer_id": user_id, 
            "shipping_address_id": address_id, 
            "status": OrderStatus.PENDING.value,
            "order_number": order_number,
            **breakdown.as_dict(),
            "shipping_line1": addr.get("line1"), 
            "shipping_city": addr.get("city"),
            "shipping_postal_code": addr.get("postal_code"), 
            "shipping_country": addr.get("country"),
            "idempotency_key": clean_idem_key, 
            "stripe_payment_intent": intent["id"]
        }
        
        try:
            # Atomic operation: Locks stock and creates order
            pending_order = await self.repo.create_pending_order_with_reservation(order_data, items_to_deduct)
            await run_in_threadpool(self.provider.update_intent_metadata, intent["id"], {"order_id": pending_order["id"], "user_id": user_id})
            
            # 🚀 FAANG FIX: Order ban chuka hai, stock lock ho gaya hai -> Turant Cart Khali Karo!
            try:
                from app.services.cart.service import CartService
                await CartService().clear_cart(user_id)
                logger.info(f"Cart cleared successfully for user {user_id[:8]} after order reservation.")
            except Exception as cart_exc:
                # We don't crash the checkout if cart clearing fails, just log it.
                logger.error("Failed to clear cart after successful order reservation: %s", cart_exc)

        except Exception as e:
            logger.error("[CRITICAL DB ERROR] Atomic Reservation Failed: %s", e)
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=PaymentSecurityMessages.RACE_CONDITION) from e

        return {
            "client_secret": intent["client_secret"], 
            "payment_intent_id": intent["id"], 
            "order_id": pending_order["id"], 
            "order_number": order_number
        }

    # --------------------------------------------------------------------------
    # PAYMENT CONFIRMATION (Checkout Step 2)
    # --------------------------------------------------------------------------

    async def confirm_payment(self, user_id: str, client_ip: str, pi_id: str, email: str) -> Dict[str, Any]:
        if not pi_id or not isinstance(pi_id, str) or len(pi_id.strip()) == 0:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid Payment Intent ID provided.")

        try:
            intent = await run_in_threadpool(self.provider.retrieve_intent, pi_id)
            if intent.get("status") != "succeeded":
                raise HTTPException(status_code=status.HTTP_402_PAYMENT_REQUIRED, detail=PaymentSecurityMessages.PAYMENT_FAILED)
        except HTTPException: 
            raise
        except Exception as exc:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=PaymentSecurityMessages.PAYMENT_FAILED) from exc

        order_id = intent.get("metadata", {}).get("order_id", "")
        if not order_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=PaymentSecurityMessages.INVALID_METADATA)

        existing_order = await self.repo.get_order_by_id(order_id)
        PaymentPolicy.assert_can_confirm(existing_order, user_id)

        try:
            result = await self.repo.settle_order_transaction(order_id, intent["id"], intent.get("amount", 0) / 100, user_id)
        except Exception as exc:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=PaymentSecurityMessages.RACE_CONDITION) from exc

        if result == "ALREADY_PAID":
            return {"status": OrderStatus.PAID.value, "order_id": order_id, "message": PaymentMessages.ALREADY_SETTLED}

        if existing_order:
            existing_order["status"] = OrderStatus.PAID.value
        
        try: 
            get_event_bus().publish(OrderPaidEvent(order=existing_order, customer_email=email, customer_id=user_id))
        except Exception as e: 
            logger.error("Event bus failed: %s", e)

        return {"status": OrderStatus.PAID.value, "order_id": order_id, "message": PaymentMessages.CONFIRMED}

    # --------------------------------------------------------------------------
    # SMART PAYWALL RETRY (Self-Healing Enterprise Retry)
    # --------------------------------------------------------------------------

    async def retry_payment(self, user_id: str, order_id: str) -> Dict[str, Any]:
        existing_order = await self.repo.get_order_by_id(order_id)
        PaymentPolicy.assert_can_retry(existing_order, user_id)
            
        if existing_order and existing_order.get("status") == OrderStatus.PAID.value:
            return {"status": OrderStatus.PAID.value, "message": PaymentMessages.RETRY_SUCCESSFUL}
            
        amount_paise = self._paise(existing_order.get("total_amount", 0) if existing_order else 0)
        
        if amount_paise < PaymentRules.MIN_ORDER_AMOUNT_PAISE:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=PaymentSecurityMessages.ZERO_AMOUNT_RETRY)
            
        pi_id = existing_order.get("stripe_payment_intent") if existing_order else None
            
        if not pi_id or not isinstance(pi_id, str) or len(pi_id.strip()) == 0:
            logger.info("[PAYMENT RETRY] No intent linked to Order %s. Generating fresh intent...", order_id[:8])
            return await self._create_and_link_replacement_intent(user_id, order_id, amount_paise)

        try:
            intent = await run_in_threadpool(self.provider.retrieve_intent, pi_id)
            
            if intent.get("status") == "succeeded":
                await self.repo.settle_order_transaction(order_id, pi_id, intent.get("amount", 0) / 100, user_id)
                return {"status": OrderStatus.PAID.value, "message": PaymentMessages.RETRY_SUCCESSFUL}
                
            client_secret = intent.get("client_secret")
            
            if intent.get("status") == "canceled" or not client_secret:
                logger.warning("[PAYMENT RETRY] Intent %s is canceled/dead. Replacing...", pi_id)
                return await self._create_and_link_replacement_intent(user_id, order_id, amount_paise)

            return {"client_secret": client_secret, "payment_intent_id": intent.get("id"), "order_id": order_id}
            
        except Exception as exc:
            logger.warning("[PAYMENT RETRY] Stripe lookup failed for %s (%s). Falling back to new intent...", pi_id, exc)
            return await self._create_and_link_replacement_intent(user_id, order_id, amount_paise)

    async def _create_and_link_replacement_intent(self, user_id: str, order_id: str, amount_paise: int) -> Dict[str, Any]:
        """Helper to generate a fresh Stripe intent and bind it to the order ledger."""
        try:
            new_intent = await run_in_threadpool(
                self.provider.create_payment_intent, 
                amount_paise, 
                "inr", 
                "AOT_RETRY", 
                user_id, 
                f"retry_pi_{order_id}_{int(time.time())}"
            )
            await self.repo.update_order_payment_intent(order_id, new_intent["id"])
            await run_in_threadpool(self.provider.update_intent_metadata, new_intent["id"], {"order_id": order_id, "user_id": user_id})
            
            return {
                "client_secret": new_intent.get("client_secret"), 
                "payment_intent_id": new_intent.get("id"), 
                "order_id": order_id
            }
        except Exception as exc:
            logger.error("[PAYMENT RETRY] Critical failure creating replacement intent: %s", exc, exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY, 
                detail=PaymentSecurityMessages.PAYMENT_FAILED
            ) from exc
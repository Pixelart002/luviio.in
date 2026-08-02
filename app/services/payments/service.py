"""
Payment Service -- Enterprise Orchestration (With Atomic GST & HSN Snapshots)
=============================================================================
Path: app/services/payments/service.py

Architecture & Fixes:
  * Cart Lifecycle: Cart is cleared immediately upon successful atomic order creation & stock reservation.
  * Self-Healing Retry Logic: Auto-generates fresh Stripe intents for unlinked/canceled orders.
  * Atomic GST & HSN Snapshots: Locks exact legal inventory prices & tax rates at checkout.
  * Enterprise Snapshots: Captures full B2B/B2C Shipping & Billing address telemetry natively.
  * Idempotent Checkout: Prevents double-charging via UUID-based idempotency keys.
  * Null Intent Guard: Prevents 502 Bad Gateway crashes when Stripe ID is None or Empty in DB.

Lifecycle-hardening changes in this version (payment-failure / webhook fix):
  * A `payments` row is now created the moment ANY PaymentIntent is created
    -- first attempt or retry -- so a failed attempt is never missing from
    the payments table.
  * `payment_intent.payment_failed` no longer cancels the order. Stripe
    keeps a declined PaymentIntent alive & confirmable, so customers can
    retry on the SAME intent -- immediately cancelling would orphan a
    perfectly good retry. We only record the failed attempt now.
  * Only an explicit `payment_intent.canceled` event (fired by our own
    abandoned-checkout cron, an admin action, or Stripe itself) triggers
    cancel_order_and_release_stock.
  * `retry_payment` now explicitly refuses to retry a cancelled/refunded
    order instead of silently handing back a client_secret for a dead order.
  * `confirm_payment` and the webhook's success handler now both check for
    the 'ORDER_ALREADY_CANCELLED' result and auto-refund via Stripe instead
    of ever letting a cancelled order flip back to 'paid'.
  * Webhook processing is now idempotent against Stripe's at-least-once
    delivery via a webhook-event ledger.

Round 2 (payment_attempts audit trail + Amazon-style attempt limiting):
  * Every PaymentIntent create now carries ip_address/user_agent into the
    payments row (previously `client_ip` was accepted but never used
    anywhere -- dead parameter). A DB trigger mirrors every payments
    status change into the append-only `payment_attempts` log (see
    migration 005) -- no Python code has to remember to log an attempt.
  * `_create_and_link_replacement_intent` now enforces
    PaymentRules.BRUTE_FORCE_MAX_ATTEMPTS -- once an order has racked up
    too many attempts, further retries are blocked (429) instead of
    letting a bad card or a script hammer the same order forever. The
    order itself is untouched; the abandoned-checkout sweep still cleans
    it up on its normal timeout.
  * The inline "recovery" intent-creation branch inside create_intent()
    was a near-duplicate of _create_and_link_replacement_intent() --
    removed; it now just calls the shared helper, so the attempt cap and
    metadata capture apply there too automatically.
"""
import time
import logging
from uuid import UUID
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List, Optional
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

class PaymentService:
    def __init__(self) -> None:
        self.repo = AsyncPaymentRepository()
        self.provider = get_payment_provider("stripe")

    def _paise(self, amount: Any) -> int:
        return int((Decimal(str(amount)) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))

    def _generate_clean_order_number(self) -> str:
        short_id = generate('23456789ABCDEFGHJKLMNPQRSTUVWXYZ', 8)
        return f"ORD-{short_id[:4]}-{short_id[4:]}"

    # --------------------------------------------------------------------------
    # INTENT CREATION (Checkout Step 1)
    # --------------------------------------------------------------------------

    async def create_intent(
        self, 
        user_id: str, 
        client_ip: str, 
        idempotency_key: str, 
        address_id: str,
        billing_address_id: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> Dict[str, Any]:
        
        try:
            clean_idem_key = str(UUID(idempotency_key))
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=PaymentSecurityMessages.INVALID_IDEMPOTENCY_KEY
            )

        existing = await self.repo.get_order_by_idempotency_key(user_id, clean_idem_key)
        if existing:
            if existing.get("status") == OrderStatus.PENDING.value:
                existing_pi = existing.get("stripe_payment_intent")
                
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
                
                logger.warning("[PAYMENT RECOVERY] Existing order %s lacks valid intent. Replacing...", existing['id'])
                amount_paise = self._paise(existing.get("total_amount", 0))
                if amount_paise < PaymentRules.MIN_ORDER_AMOUNT_PAISE:
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=PaymentSecurityMessages.ZERO_AMOUNT_RETRY)
                # 🔥 FIX: reuse the single replacement-intent helper (was
                # duplicated inline here before) -- this also means the
                # attempt-count cap and ip/user_agent metadata capture apply
                # here too, automatically, with no separate code path to
                # keep in sync.
                result = await self._create_and_link_replacement_intent(
                    user_id, existing["id"], amount_paise, ip_address=client_ip, user_agent=user_agent
                )
                result["order_number"] = existing.get("order_number", "")
                return result

            elif existing.get("status") == OrderStatus.PAID.value:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=PaymentSecurityMessages.ALREADY_PAID)
            else:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=PaymentSecurityMessages.DUPLICATE_ORDER)

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

        # Fetch Shipping Address
        addr = await self.repo.get_shipping_address(address_id, user_id)
        if not addr: 
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=PaymentSecurityMessages.ADDRESS_NOT_FOUND)

        # 🔥 ENTERPRISE FIX: Fetch Billing Address (if different), else default to Shipping
        billing_addr = addr
        is_same_as_shipping = True
        
        if billing_address_id and billing_address_id != address_id:
            fetched_billing = await self.repo.get_shipping_address(billing_address_id, user_id)
            if fetched_billing:
                billing_addr = fetched_billing
                is_same_as_shipping = False

        try:
            intent = await run_in_threadpool(self.provider.create_payment_intent, amount_paise, "inr", "AOT_PENDING", user_id, f"aot_pi_{clean_idem_key}")
        except Exception as exc:
            logger.error("[PAYMENT ERROR] Initial Stripe Intent creation failed: %s", exc)
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=PaymentSecurityMessages.PAYMENT_FAILED) from exc

        order_number = self._generate_clean_order_number()

        # 🚀 ENTERPRISE SNAPSHOT: Dual Shipping & Billing Mapping
        order_data = {
            "customer_id": user_id, 
            "status": OrderStatus.PENDING.value,
            "order_number": order_number,
            "idempotency_key": clean_idem_key, 
            "stripe_payment_intent": intent["id"],
            **breakdown.as_dict(),
            
            # --- SHIPPING SNAPSHOT ---
            "shipping_address_id": address_id, 
            "shipping_name": addr.get("full_name"),
            "shipping_phone": addr.get("phone"),
            "shipping_email": addr.get("email"),
            "shipping_line1": addr.get("line1"), 
            "shipping_line2": addr.get("line2"), 
            "shipping_landmark": addr.get("landmark"),
            "shipping_city": addr.get("city"),
            "shipping_state": addr.get("state"),
            "shipping_postal_code": addr.get("postal_code"), 
            "shipping_country": addr.get("country", "IN"),
            "shipping_company_name": addr.get("company_name"),
            "shipping_gstin": addr.get("gstin"),

            # --- BILLING SNAPSHOT ---
            "billing_same_as_shipping": is_same_as_shipping,
            "billing_address_id": billing_addr.get("id"),
            "billing_name": billing_addr.get("full_name"),
            "billing_phone": billing_addr.get("phone"),
            "billing_email": billing_addr.get("email"),
            "billing_line1": billing_addr.get("line1"), 
            "billing_line2": billing_addr.get("line2"), 
            "billing_landmark": billing_addr.get("landmark"),
            "billing_city": billing_addr.get("city"),
            "billing_state": billing_addr.get("state"),
            "billing_postal_code": billing_addr.get("postal_code"), 
            "billing_country": billing_addr.get("country", "IN"),
            "billing_company_name": billing_addr.get("company_name"),
            "billing_gstin": billing_addr.get("gstin"),
        }
        
        try:
            pending_order = await self.repo.create_pending_order_with_reservation(order_data, items_to_deduct)
            await run_in_threadpool(self.provider.update_intent_metadata, intent["id"], {"order_id": pending_order["id"], "user_id": user_id})

            # 🔥 FIX (Problem 1): write the payments row NOW, not only on success.
            # This is what guarantees the payments table never has a "hole" for
            # a PaymentIntent that later fails.
            await self.repo.create_or_touch_payment_intent_record(
                pending_order["id"], user_id, intent["id"], amount_paise / 100,
                ip_address=client_ip, user_agent=user_agent
            )

            try:
                from app.services.cart.service import CartService
                await CartService().clear_cart(user_id)
                logger.info(f"Cart cleared successfully for user {user_id[:8]} after order reservation.")
            except Exception as cart_exc:
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

        # 🔥 FIX (Problem 3 / Scenario B): the order was cancelled (stock
        # already released -- possibly resold) before this payment landed.
        # Never resurrect it as 'paid'. Refund the customer automatically
        # and surface a clear message instead of a confusing success state.
        if result == "ORDER_ALREADY_CANCELLED":
            logger.critical(
                "[PAYMENT] User %s successfully paid Intent %s but Order %s was already "
                "cancelled. Auto-refunding to avoid an unfulfillable paid order.",
                user_id[:8], pi_id, order_id
            )
            try:
                await run_in_threadpool(self.provider.process_refund, pi_id)
            except Exception as refund_exc:
                logger.error("[PAYMENT] Auto-refund FAILED for orphaned success %s: %s -- needs manual refund.", pi_id, refund_exc)
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=PaymentSecurityMessages.ORDER_CANCELLED_AUTO_REFUNDED
            )

        if existing_order:
            existing_order["status"] = OrderStatus.PAID.value
        
        try: 
            get_event_bus().publish(OrderPaidEvent(order=existing_order, customer_email=email, customer_id=user_id))
        except Exception as e: 
            logger.error("Event bus failed: %s", e)

        return {"status": OrderStatus.PAID.value, "order_id": order_id, "message": PaymentMessages.CONFIRMED}

    async def retry_payment(self, user_id: str, order_id: str, client_ip: Optional[str] = None, user_agent: Optional[str] = None) -> Dict[str, Any]:
        existing_order = await self.repo.get_order_by_id(order_id)
        PaymentPolicy.assert_can_retry(existing_order, user_id)

        current_status = existing_order.get("status") if existing_order else None

        if current_status == OrderStatus.PAID.value:
            return {"status": OrderStatus.PAID.value, "message": PaymentMessages.RETRY_SUCCESSFUL}

        # 🔥 FIX (Scenario A/B): an order can only reach 'cancelled' now via
        # an explicit PaymentIntent cancellation or the abandoned-checkout
        # timeout sweep -- never from a single card decline. If it's here,
        # the retry window has genuinely closed and stock is gone.
        if current_status in (OrderStatus.CANCELLED.value, OrderStatus.REFUNDED.value):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=PaymentSecurityMessages.ORDER_NO_LONGER_RETRYABLE
            )

        amount_paise = self._paise(existing_order.get("total_amount", 0) if existing_order else 0)
        
        if amount_paise < PaymentRules.MIN_ORDER_AMOUNT_PAISE:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=PaymentSecurityMessages.ZERO_AMOUNT_RETRY)
            
        pi_id = existing_order.get("stripe_payment_intent") if existing_order else None
            
        if not pi_id or not isinstance(pi_id, str) or len(pi_id.strip()) == 0:
            logger.info("[PAYMENT RETRY] No intent linked to Order %s. Generating fresh intent...", order_id[:8])
            return await self._create_and_link_replacement_intent(user_id, order_id, amount_paise, ip_address=client_ip, user_agent=user_agent)

        try:
            intent = await run_in_threadpool(self.provider.retrieve_intent, pi_id)
            
            if intent.get("status") == "succeeded":
                result = await self.repo.settle_order_transaction(order_id, pi_id, intent.get("amount", 0) / 100, user_id)
                if result == "ORDER_ALREADY_CANCELLED":
                    try:
                        await run_in_threadpool(self.provider.process_refund, pi_id)
                    except Exception:
                        pass
                    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=PaymentSecurityMessages.ORDER_CANCELLED_AUTO_REFUNDED)
                return {"status": OrderStatus.PAID.value, "message": PaymentMessages.RETRY_SUCCESSFUL}
                
            client_secret = intent.get("client_secret")
            
            if intent.get("status") == "canceled" or not client_secret:
                logger.warning("[PAYMENT RETRY] Intent %s is canceled/dead. Replacing...", pi_id)
                return await self._create_and_link_replacement_intent(user_id, order_id, amount_paise, ip_address=client_ip, user_agent=user_agent)

            return {"client_secret": client_secret, "payment_intent_id": intent.get("id"), "order_id": order_id}
            
        except HTTPException:
            raise
        except Exception as exc:
            logger.warning("[PAYMENT RETRY] Stripe lookup failed for %s (%s). Falling back to new intent...", pi_id, exc)
            return await self._create_and_link_replacement_intent(user_id, order_id, amount_paise, ip_address=client_ip, user_agent=user_agent)

    async def _create_and_link_replacement_intent(
        self, user_id: str, order_id: str, amount_paise: int,
        ip_address: Optional[str] = None, user_agent: Optional[str] = None
    ) -> Dict[str, Any]:
        # 🔥 NEW (Amazon-style retry cap): block further retries once an
        # order has racked up too many attempts. Keeps a single bad card
        # (or a scripted attack) from hammering the same order forever --
        # the order itself is untouched and will still get cleaned up by
        # the abandoned-checkout sweep on its normal timeout.
        attempt_count = await self.repo.get_attempt_count(order_id)
        if attempt_count >= PaymentRules.BRUTE_FORCE_MAX_ATTEMPTS:
            logger.warning("[PAYMENT RETRY] Order %s hit the %d-attempt cap. Blocking further retries.", order_id[:8], PaymentRules.BRUTE_FORCE_MAX_ATTEMPTS)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=PaymentSecurityMessages.TOO_MANY_ATTEMPTS
            )

        try:
            new_intent = await run_in_threadpool(
                self.provider.create_payment_intent, 
                amount_paise, 
                "inr", 
                "AOT_RETRY", 
                user_id, 
                f"retry_pi_{order_id}_{int(time.time())}"
            )
            linked = await self.repo.update_order_payment_intent(order_id, new_intent["id"])
            if not linked:
                # 🔥 FIX: order flipped to a terminal state (cron / another
                # webhook) in the moment between our read and this write.
                # Don't hand back a client_secret for an intent that isn't
                # actually attached to a live order -- cancel it on Stripe
                # too so it can never be confirmed later.
                try:
                    await run_in_threadpool(self.provider.cancel_intent, new_intent["id"])
                except Exception:
                    pass
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=PaymentSecurityMessages.ORDER_NO_LONGER_RETRYABLE
                )

            await run_in_threadpool(self.provider.update_intent_metadata, new_intent["id"], {"order_id": order_id, "user_id": user_id})

            # 🔥 FIX (Problem 1): every retry gets its own payments row too.
            await self.repo.create_or_touch_payment_intent_record(
                order_id, user_id, new_intent["id"], amount_paise / 100,
                ip_address=ip_address, user_agent=user_agent
            )
            
            return {
                "client_secret": new_intent.get("client_secret"), 
                "payment_intent_id": new_intent.get("id"), 
                "order_id": order_id
            }
        except HTTPException:
            raise
        except Exception as exc:
            logger.error("[PAYMENT RETRY] Critical failure creating replacement intent: %s", exc, exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY, 
                detail=PaymentSecurityMessages.PAYMENT_FAILED
            ) from exc

    async def record_client_reported_failure(self, pi_id: str, reason: str) -> None:
        """
        Backs the /notify-failed endpoint. This is a best-effort, client-
        reported signal (the browser saw Stripe.js return an error) -- it
        is NOT authoritative and never touches order status. It just gets
        the failed attempt into the payments table a little faster than
        waiting for the webhook, for support/analytics visibility.
        """
        order = await self.repo.get_order_by_payment_intent(pi_id)
        if not order:
            return
        await self.repo.mark_payment_failed(
            order["id"], order.get("customer_id"), pi_id,
            float(order.get("total_amount") or 0), reason=reason or "Client-reported failure"
        )

    # --------------------------------------------------------------------------
    # WEBHOOK HANDLER
    # --------------------------------------------------------------------------
    async def handle_webhook(self, payload: bytes, sig_header: str) -> None:
        """Handles background events from Stripe (Refunds, Disputes, Failures, Success)."""
        try:
            event = self.provider.verify_webhook(payload, sig_header)
        except Exception as e:
            logger.error("Webhook verification failed: %s", e)
            raise ValueError("Invalid Stripe Signature")

        event_id = event.get("id")
        event_type = event.get("type")
        obj = event.get("data", {}).get("object", {})

        # Find payment intent ID securely
        pi_id = obj.get("id") if obj.get("object") == "payment_intent" else obj.get("payment_intent")
        
        if not pi_id:
            logger.warning("[WEBHOOK] Ignored %s - No Payment Intent ID found in payload.", event_type)
            return

        # 🔥 FIX: idempotency -- Stripe retries webhooks on any non-2xx/timeout
        # response, and can redeliver the same event more than once regardless.
        # claim_webhook_event only returns False for an event that was already
        # marked FULLY PROCESSED -- a delivery for an event that crashed
        # mid-processing last time is correctly let through again.
        if event_id:
            should_process = await self.repo.record_webhook_event(event_id, event_type, pi_id)
            if not should_process:
                logger.info("[WEBHOOK] Duplicate delivery of event %s (%s) ignored (already processed).", event_id, event_type)
                return

        order = await self.repo.get_order_by_payment_intent(pi_id)
        if not order:
            logger.warning("[WEBHOOK] Ignored %s - No order found in database for PI %s", event_type, pi_id)
            if event_id:
                await self.repo.mark_webhook_event_processed(event_id)
            return

        order_id = order["id"]
        current_status = order["status"]
        customer_id = order["customer_id"]

        logger.info("[WEBHOOK] Received %s for Order %s (Current Status: %s)", event_type, order_id[:8], current_status)

        # 🔥 FIX: everything below is the actual processing. If ANY of it
        # raises, we deliberately do NOT mark the event processed -- the
        # exception propagates up, the router answers 500, and Stripe's
        # retry will legitimately be allowed to try again (see
        # claim_webhook_event). Only a clean run marks it done.
        try:
            # EVENT 1: SUCCESS
            if event_type == "payment_intent.succeeded":
                if current_status == OrderStatus.PENDING.value:
                    amount = obj.get("amount", 0) / 100
                    result = await self.repo.settle_order_transaction(order_id, pi_id, amount, customer_id)
                    if result == "ORDER_ALREADY_CANCELLED":
                        # 🔥 FIX (Scenario B, race with the abandoned-checkout sweep):
                        # payment succeeded microseconds after we cancelled + released
                        # stock. Never flip the order back to paid -- refund instead.
                        logger.critical(
                            "🚨 [WEBHOOK ALERT] Payment %s succeeded for already-cancelled Order %s. Issuing auto-refund.",
                            pi_id, order_id
                        )
                        try:
                            await run_in_threadpool(self.provider.process_refund, pi_id)
                        except Exception as refund_exc:
                            logger.error("[WEBHOOK] Auto-refund FAILED for orphaned success %s: %s -- needs manual refund.", pi_id, refund_exc)
                    else:
                        logger.info("[WEBHOOK] Settled pending order %s automatically via webhook.", order_id[:8])
                # else: already paid / terminal -- nothing to do, this is a safe no-op.

            # EVENT 2: PAYMENT FAILED -- record only, DO NOT cancel.
            # 🔥 FIX (Problem 2 & 3, Scenario A): Stripe keeps a declined
            # PaymentIntent alive & confirmable so the customer can retry on the
            # SAME intent. Cancelling the order here would kill that retry path
            # and release stock that the very next attempt might still need.
            elif event_type == "payment_intent.payment_failed":
                if current_status == OrderStatus.PENDING.value:
                    reason = (obj.get("last_payment_error") or {}).get("message", "Payment failed")
                    error_code = (obj.get("last_payment_error") or {}).get("code")
                    amount = obj.get("amount", 0) / 100
                    await self.repo.mark_payment_failed(order_id, customer_id, pi_id, amount, reason=reason, error_code=error_code)
                    logger.info("[WEBHOOK] Recorded failed attempt for Order %s (PI %s): %s", order_id[:8], pi_id, reason)

            # EVENT 3: EXPLICIT CANCELLATION -- THIS is the terminal signal.
            # Fired when our abandoned-checkout cron (or an admin, or Stripe
            # itself) actually cancels the PaymentIntent via the API.
            elif event_type == "payment_intent.canceled":
                if current_status == OrderStatus.PENDING.value:
                    await self.repo.release_abandoned_order(order_id, reason=f"stripe_event:{event_type}")
                    logger.info("[WEBHOOK] Cancelled pending order %s and released stock (PI explicitly canceled).", order_id[:8])

            # EVENT 4: REFUNDED
            elif event_type == "charge.refunded":
                # Only update if not already refunded/cancelled
                if current_status not in [OrderStatus.CANCELLED.value, OrderStatus.REFUNDED.value]:
                    await self.repo.update_order_status_via_rpc(order_id, OrderStatus.REFUNDED.value, f"Webhook Auto-Update: {event_type}")
                    logger.info("[WEBHOOK] Marked order %s as Refunded.", order_id[:8])

            # EVENT 5: DISPUTE (Chargeback via Bank)
            elif event_type == "charge.dispute.created":
                amount_disputed = obj.get('amount', 0) / 100
                logger.error("🚨 [WEBHOOK ALERT] Dispute created for order %s. Amount: %s", order_id, amount_disputed)
                # Add an alert to the order notes, keep the current status
                alert_note = f"🚨 BANK DISPUTE CREATED for Rs. {amount_disputed}! Check Stripe Dashboard immediately."
                await self.repo.update_order_status_via_rpc(order_id, current_status, alert_note)

            # Any other event type (payment_intent.created, .processing,
            # .requires_action, etc.) -- nothing for us to do, falls through
            # here and still gets marked processed below.

        except Exception:
            logger.error("[WEBHOOK] Processing FAILED for event %s (%s) on order %s -- leaving unmarked for retry.", event_id, event_type, order_id[:8], exc_info=True)
            raise

        if event_id:
            await self.repo.mark_webhook_event_processed(event_id)
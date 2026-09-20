"""
Payment Service -- Enterprise Orchestration (With Atomic GST & HSN Snapshots)
=============================================================================
Path: app/domains/payments/service.py
"""
import asyncio
import logging
import time
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Dict, List, Optional
from uuid import UUID

from email_validator import EmailNotValidError, validate_email
from fastapi import HTTPException, status
from nanoid import generate
from starlette.concurrency import run_in_threadpool

from app.constants.payment_messages import PaymentMessages, PaymentRules, PaymentSecurityMessages
from app.core.supabase import get_async_admin_supabase
from app.domains.inventory.service import InventoryService
from app.domains.payments.repository import AsyncPaymentRepository
from app.domains.pricing.service import get_pricing_from_config
from app.enums.order_status import OrderStatus
from app.events.bus import OrderCreatedEvent, OrderFailedEvent, OrderPaidEvent, OrderStatusChangedEvent, get_event_bus
from app.integrations.payments.registry import get_payment_provider
from app.permissions.policies.payment_policies import PaymentPolicy

logger = logging.getLogger(__name__)


class PaymentService:
    def __init__(self) -> None:
        self.repo = AsyncPaymentRepository()
        self.inventory = InventoryService()
        self.provider = get_payment_provider("stripe")

    def _paise(self, amount: Any) -> int:
        return int((Decimal(str(amount)) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))

    def _generate_clean_order_number(self) -> str:
        short_id = generate('23456789ABCDEFGHJKLMNPQRSTUVWXYZ', 8)
        return f"ORD-{short_id[:4]}-{short_id[4:]}"

    async def _reserve_retry(self, order_id: str, user_id: str, pi_id: str) -> int:
        admin_sb = await get_async_admin_supabase()
        try:
            res = await admin_sb.rpc(
                "reserve_payment_retry",
                {
                    "p_order_id": order_id,
                    "p_user_id": user_id,
                    "p_pi_id": pi_id,
                    "p_window_seconds": PaymentRules.BRUTE_FORCE_WINDOW_SEC,
                    "p_max_attempts": PaymentRules.BRUTE_FORCE_MAX_ATTEMPTS,
                },
            ).execute()
            data = getattr(res, "data", None)
            if not data:
                raise RuntimeError("Retry reservation returned no data")
            row = data[0] if isinstance(data, list) else data
            return int(row.get("attempt_number"))
        except Exception as exc:
            message = str(exc)
            if "PAYMENT_RETRY_LIMIT:" in message:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=PaymentSecurityMessages.TOO_MANY_ATTEMPTS,
                ) from exc
            logger.error("[PAYMENT RETRY] Unable to reserve retry slot for order %s", order_id[:8], exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Unable to verify payment retry availability.",
            ) from exc

    async def create_intent(
        self,
        user_id: str,
        client_ip: str,
        idempotency_key: str,
        address_id: str,
        billing_address_id: Optional[str] = None,
        user_agent: Optional[str] = None,
        coupon_code: Optional[str] = None,
    ) -> Dict[str, Any]:
        try:
            clean_idem_key = str(UUID(idempotency_key))
        except ValueError:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=PaymentSecurityMessages.INVALID_IDEMPOTENCY_KEY)

        from app.permissions.action_control import assert_action_enabled

        # These checks are independent. Running them together removes one
        # serialized DB/network round-trip from the new-checkout critical path.
        existing, _ = await asyncio.gather(
            self.repo.get_order_by_idempotency_key(user_id, clean_idem_key),
            assert_action_enabled(
                user_id,
                "checkout",
                "Checkout is currently disabled for your account.",
            ),
        )
        if existing:
            if existing.get("status") == OrderStatus.PENDING.value:
                existing_pi = existing.get("stripe_payment_intent")
                if existing_pi and isinstance(existing_pi, str) and existing_pi.strip():
                    try:
                        intent = await run_in_threadpool(self.provider.retrieve_intent, existing_pi)
                        if intent.get("status") in {"requires_payment_method", "requires_confirmation", "requires_action"}:
                            return {"client_secret": intent.get("client_secret"), "payment_intent_id": intent.get("id"), "order_id": existing["id"], "order_number": existing.get("order_number", "")}
                        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=PaymentSecurityMessages.INTENT_STATE_ERROR.format(status=intent.get('status')))
                    except HTTPException:
                        raise
                    except Exception as exc:
                        logger.error("[PAYMENT ERROR] Stripe retrieval failed for existing order: %s", exc, exc_info=True)
                amount_paise = self._paise(existing.get("total_amount", 0))
                if amount_paise < PaymentRules.MIN_ORDER_AMOUNT_PAISE:
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=PaymentSecurityMessages.ZERO_AMOUNT_RETRY)
                result = await self._create_and_link_replacement_intent(user_id, existing["id"], amount_paise, ip_address=client_ip, user_agent=user_agent)
                result["order_number"] = existing.get("order_number", "")
                return result
            if existing.get("status") == OrderStatus.PAID.value:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=PaymentSecurityMessages.ALREADY_PAID)
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=PaymentSecurityMessages.DUPLICATE_ORDER)

        cart_items, config, addr = await asyncio.gather(
            self.repo.get_cart_items_for_checkout(user_id),
            self.repo.get_pricing_config(),
            self.repo.get_shipping_address(address_id, user_id),
        )
        PaymentPolicy.assert_valid_cart(cart_items)
        subtotal = Decimal("0")
        items_to_deduct: List[Dict[str, Any]] = []
        for item in cart_items:
            prod = item.get("products") or {}
            PaymentPolicy.assert_stock_availability(item["quantity"], prod)
            snapshot = item.get("price_snapshot")
            if snapshot is None:
                logger.error("[PAYMENT] Missing price_snapshot for product %s", item.get("product_id"))
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=PaymentSecurityMessages.RACE_CONDITION)
            locked_price = Decimal(str(snapshot))
            if locked_price < 0:
                logger.error("[PAYMENT] Negative price_snapshot for product %s", item.get("product_id"))
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=PaymentSecurityMessages.RACE_CONDITION)
            lt = locked_price * item["quantity"]
            subtotal += lt
            hsn_code = str(prod.get("hsn_code") or item.get("hsn_code") or "").strip()
            if not hsn_code:
                logger.error("[PAYMENT] Missing HSN snapshot for product %s", item.get("product_id"))
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=PaymentSecurityMessages.RACE_CONDITION)
            gst_raw = prod.get("gst_percentage") if prod.get("gst_percentage") is not None else item.get("gst_percentage")
            if gst_raw is None:
                logger.error("[PAYMENT] Missing GST snapshot for product %s", item.get("product_id"))
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=PaymentSecurityMessages.RACE_CONDITION)
            gst_percentage = int(gst_raw)
            items_to_deduct.append({"product_id": item["product_id"], "product_name": prod.get("name", "Item"), "hsn_code": hsn_code, "gst_percentage": gst_percentage, "unit_price": float(locked_price), "compare_price": float(prod.get("compare_price") or 0.0), "quantity": item["quantity"], "subtotal": float(lt)})

        breakdown = get_pricing_from_config(config).calculate(items=items_to_deduct)
        if not addr:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=PaymentSecurityMessages.ADDRESS_NOT_FOUND)
        try:
            validate_email(addr.get("email") or "", check_deliverability=False)
        except EmailNotValidError:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=PaymentSecurityMessages.ADDRESS_EMAIL_MISSING)

        amount_paise = self._paise(breakdown.total)
        PaymentPolicy.assert_minimum_amount(amount_paise)
        coupon_id, coupon_code_resolved = None, coupon_code
        coupon_discount = Decimal("0")
        goods_subtotal = subtotal
        if coupon_code:
            from app.domains.coupons.service import CouponService
            resolved = await CouponService().resolve_discount_for_checkout(
                coupon_code,
                float(goods_subtotal),
                user_id,
            )
            coupon_discount = Decimal(str(resolved.get("discount") or 0))
            coupon_id = resolved.get("coupon_id")
            coupon_code_resolved = resolved.get("code")
        if coupon_discount > 0:
            amount_paise = self._paise(
                max(breakdown.total - coupon_discount, Decimal("0"))
            )
            PaymentPolicy.assert_minimum_amount(amount_paise)

        billing_addr = addr
        is_same_as_shipping = True
        if billing_address_id and billing_address_id != address_id:
            billing_addr = await self.repo.get_shipping_address(
                billing_address_id,
                user_id,
            )
            if not billing_addr:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=PaymentSecurityMessages.ADDRESS_NOT_FOUND,
                )
            is_same_as_shipping = False
            try:
                validate_email(
                    billing_addr.get("email") or "",
                    check_deliverability=False,
                )
            except EmailNotValidError:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=PaymentSecurityMessages.ADDRESS_EMAIL_MISSING,
                )

        try:
            checkout_attempt_id = await self.repo.create_checkout_payment_attempt(
                user_id, clean_idem_key, amount_paise, "inr"
            )
        except Exception as exc:
            logger.error("[PAYMENT ERROR] Durable checkout-attempt creation failed: %s", exc, exc_info=True)
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=PaymentSecurityMessages.PAYMENT_FAILED) from exc

        try:
            intent = await run_in_threadpool(self.provider.create_payment_intent, amount_paise, "inr", "AOT_PENDING", user_id, f"aot_pi_{clean_idem_key}")
        except Exception as exc:
            logger.error("[PAYMENT ERROR] Initial Stripe Intent creation failed: %s", exc, exc_info=True)
            try:
                await self.repo.update_checkout_payment_attempt(
                    checkout_attempt_id, status="cancelled", last_error=str(exc)[:1000]
                )
            except Exception:
                logger.critical("[PAYMENT ORPHAN RISK] Could not close durable checkout attempt %s", checkout_attempt_id, exc_info=True)
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=PaymentSecurityMessages.PAYMENT_FAILED) from exc

        order_number = self._generate_clean_order_number()
        order_data = {"customer_id": user_id, "status": OrderStatus.PENDING.value, "order_number": order_number, "idempotency_key": clean_idem_key, "stripe_payment_intent": intent["id"], "coupon_id": coupon_id, "coupon_code": coupon_code_resolved, "discount_amount": float(coupon_discount), **breakdown.as_dict(), "total_amount": float(max(breakdown.total - coupon_discount, Decimal("0"))), "shipping_address_id": address_id, "shipping_name": addr.get("full_name"), "shipping_phone": addr.get("phone"), "shipping_email": addr.get("email"), "shipping_line1": addr.get("line1"), "shipping_line2": addr.get("line2"), "shipping_landmark": addr.get("landmark"), "shipping_city": addr.get("city"), "shipping_state": addr.get("state"), "shipping_postal_code": addr.get("postal_code"), "shipping_country": addr.get("country", "IN"), "shipping_company_name": addr.get("company_name"), "shipping_gstin": addr.get("gstin"), "billing_same_as_shipping": is_same_as_shipping, "billing_address_id": billing_addr.get("id"), "billing_name": billing_addr.get("full_name"), "billing_phone": billing_addr.get("phone"), "billing_email": billing_addr.get("email"), "billing_line1": billing_addr.get("line1"), "billing_line2": billing_addr.get("line2"), "billing_landmark": billing_addr.get("landmark"), "billing_city": billing_addr.get("city"), "billing_state": billing_addr.get("state"), "billing_postal_code": billing_addr.get("postal_code"), "billing_country": billing_addr.get("country", "IN"), "billing_company_name": billing_addr.get("company_name"), "billing_gstin": billing_addr.get("gstin")}
        try:
            pending_order = await self.repo.create_pending_order_with_reservation(
                order_data,
                items_to_deduct,
                checkout_attempt_id=checkout_attempt_id,
            )
        except Exception as exc:
            raced = await self.repo.get_order_by_idempotency_key(user_id, clean_idem_key)
            if raced and raced.get("status") == OrderStatus.PENDING.value and raced.get("stripe_payment_intent"):
                logger.info("[PAYMENT] Idempotency race converged to existing order %s", raced["id"])
                existing_pi = raced["stripe_payment_intent"]
                try:
                    existing_intent = await run_in_threadpool(self.provider.retrieve_intent, existing_pi)
                    return {"client_secret": existing_intent.get("client_secret"), "payment_intent_id": existing_pi, "order_id": raced["id"], "order_number": raced.get("order_number", "")}
                except Exception:
                    logger.error("[PAYMENT] Existing idempotent order found but Stripe retrieval failed", exc_info=True)
            logger.error("[CRITICAL DB ERROR] Atomic Reservation Failed: %s", exc, exc_info=True)
            try:
                await self.repo.update_checkout_payment_attempt(
                    checkout_attempt_id, status="cancel_requested", last_error=str(exc)[:1000]
                )
            except Exception:
                logger.critical("[PAYMENT ORPHAN RISK] Could not mark checkout attempt %s cancel_requested", checkout_attempt_id, exc_info=True)
            # Compensation boundary: Stripe created the provider object before the
            # durable order/reservation transaction. If persistence failed and no
            # concurrent idempotent order won the race, cancel the newly-created
            # PaymentIntent so funds are not left attached to a non-existent order.
            try:
                await run_in_threadpool(self.provider.cancel_intent, intent["id"])
                logger.warning(
                    "[PAYMENT COMPENSATION] Cancelled Stripe PaymentIntent %s after order persistence failure",
                    intent["id"],
                )
                await self.repo.update_checkout_payment_attempt(
                    checkout_attempt_id, status="cancelled", last_error=str(exc)[:1000]
                )
            except Exception as cancel_exc:
                # Cancellation failure remains observable and must not be hidden.
                # The existing abandoned-order sweep cannot see an order that was
                # never committed, so this is logged as a high-severity orphan risk.
                logger.critical(
                    "[PAYMENT ORPHAN RISK] Failed to cancel Stripe PaymentIntent %s after order persistence failure: %s",
                    intent["id"],
                    cancel_exc,
                    exc_info=True,
                )
                try:
                    await self.repo.update_checkout_payment_attempt(
                        checkout_attempt_id, status="orphan_risk", last_error=str(cancel_exc)[:1000]
                    )
                except Exception:
                    logger.critical("[PAYMENT ORPHAN RISK] Durable checkout attempt update also failed for %s", checkout_attempt_id, exc_info=True)
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=PaymentSecurityMessages.RACE_CONDITION) from exc

        metadata_result, attempt_result, email_result = await asyncio.gather(
            run_in_threadpool(
                self.provider.update_intent_metadata,
                intent["id"],
                {"order_id": pending_order["id"], "user_id": user_id},
            ),
            self.repo.record_payment_attempt(
                pending_order["id"],
                user_id,
                intent["id"],
                amount_paise / 100,
                status="requires_payment_method",
                ip_address=client_ip,
                user_agent=user_agent,
            ),
            self.repo.get_customer_email(user_id),
            return_exceptions=True,
        )
        if isinstance(metadata_result, Exception):
            raise metadata_result
        if isinstance(attempt_result, Exception):
            raise attempt_result

        if isinstance(email_result, Exception):
            logger.error(
                "Failed to load customer email for OrderCreatedEvent: %s",
                email_result,
            )
        else:
            try:
                get_event_bus().publish(
                    OrderCreatedEvent(
                        order=pending_order,
                        customer_email=email_result,
                        customer_id=user_id,
                    )
                )
            except Exception as event_exc:
                logger.error("Failed to publish OrderCreatedEvent: %s", event_exc)
        return {"client_secret": intent["client_secret"], "payment_intent_id": intent["id"], "order_id": pending_order["id"], "order_number": order_number}

    async def confirm_payment(self, user_id: str, client_ip: str, pi_id: str, email: str) -> Dict[str, Any]:
        if not pi_id or not isinstance(pi_id, str) or not pi_id.strip():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid Payment Intent ID provided.")
        try:
            intent = await run_in_threadpool(self.provider.retrieve_intent, pi_id)
            if intent.get("status") != "succeeded":
                try:
                    fail_order_id = intent.get("metadata", {}).get("order_id", "")
                    get_event_bus().publish(OrderFailedEvent(order={"id": fail_order_id}, customer_email=email, customer_id=user_id, reason="payment_failed"))
                except Exception as event_exc:
                    logger.error("Failed to publish OrderFailedEvent: %s", event_exc)
                raise HTTPException(status_code=status.HTTP_402_PAYMENT_REQUIRED, detail=PaymentSecurityMessages.PAYMENT_FAILED)
        except HTTPException:
            raise
        except Exception as exc:
            logger.error("[PAYMENT] Stripe confirmation retrieval failed", exc_info=True)
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=PaymentSecurityMessages.PAYMENT_FAILED) from exc

        order_id = intent.get("metadata", {}).get("order_id", "")
        if not order_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=PaymentSecurityMessages.INVALID_METADATA)
        existing_order = await self.repo.get_order_by_id(order_id)
        PaymentPolicy.assert_can_confirm(existing_order, user_id)
        try:
            pm_types = intent.get("payment_method_types", [])
            pm_type = pm_types[0] if pm_types else "card"
            result = await self.inventory.commit_reservation(order_id, intent["id"], intent.get("amount", 0) / 100, user_id, payment_method=pm_type, stripe_currency=intent.get("currency"))
        except Exception as exc:
            logger.error("[PAYMENT] Settlement failed for order %s", order_id[:8], exc_info=True)
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=PaymentSecurityMessages.RACE_CONDITION) from exc
        if result == "ALREADY_PAID":
            return {"status": OrderStatus.PAID.value, "order_id": order_id, "message": PaymentMessages.ALREADY_SETTLED}
        if result == "ORDER_ALREADY_CANCELLED":
            try:
                await run_in_threadpool(self.provider.process_refund, pi_id)
            except Exception as refund_exc:
                logger.error("[PAYMENT] Auto-refund FAILED for orphaned success %s: %s", pi_id, refund_exc, exc_info=True)
                raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=PaymentSecurityMessages.ORDER_CANCELLED_REFUND_PENDING) from refund_exc
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=PaymentSecurityMessages.ORDER_CANCELLED_AUTO_REFUNDED)
        if result != "SETTLED":
            logger.error("[PAYMENT SECURITY] Unexpected settlement result %r for order %s", result, order_id[:8])
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=PaymentSecurityMessages.RACE_CONDITION)
        if existing_order:
            existing_order["status"] = OrderStatus.PAID.value
        coupon_id_order = (existing_order or {}).get("coupon_id")
        if coupon_id_order:
            try:
                from app.domains.coupons.repository import AsyncCouponRepository
                await AsyncCouponRepository().record_redemption(coupon_id_order, user_id, order_id, float((existing_order or {}).get("discount_amount") or 0))
            except Exception as coupon_exc:
                logger.error("[PAYMENT] Coupon redemption failed for order %s: %s", order_id, coupon_exc)
        try:
            get_event_bus().publish(OrderPaidEvent(order=existing_order, customer_email=(existing_order or {}).get("shipping_email") or (existing_order or {}).get("billing_email") or email, customer_id=user_id))
        except Exception as e:
            logger.error("Event bus failed: %s", e, exc_info=True)
        return {"status": OrderStatus.PAID.value, "order_id": order_id, "message": PaymentMessages.CONFIRMED}

    async def retry_payment(self, user_id: str, order_id: str, client_ip: Optional[str] = None, user_agent: Optional[str] = None) -> Dict[str, Any]:
        existing_order = await self.repo.get_order_by_id(order_id)
        PaymentPolicy.assert_can_retry(existing_order, user_id)
        current_status = existing_order.get("status") if existing_order else None
        if current_status == OrderStatus.PAID.value:
            return {"status": OrderStatus.PAID.value, "message": PaymentMessages.RETRY_SUCCESSFUL}
        if current_status in (OrderStatus.CANCELLED.value, OrderStatus.REFUNDED.value):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=PaymentSecurityMessages.ORDER_NO_LONGER_RETRYABLE)
        amount_paise = self._paise(existing_order.get("total_amount", 0) if existing_order else 0)
        if amount_paise < PaymentRules.MIN_ORDER_AMOUNT_PAISE:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=PaymentSecurityMessages.ZERO_AMOUNT_RETRY)
        pi_id = existing_order.get("stripe_payment_intent") if existing_order else None
        if not pi_id or not isinstance(pi_id, str) or not pi_id.strip():
            return await self._create_and_link_replacement_intent(user_id, order_id, amount_paise, ip_address=client_ip, user_agent=user_agent)
        try:
            intent = await run_in_threadpool(self.provider.retrieve_intent, pi_id)
            if intent.get("status") == "succeeded":
                pm_types = intent.get("payment_method_types", [])
                pm_type = pm_types[0] if pm_types else "card"
                result = await self.inventory.commit_reservation(order_id, pi_id, intent.get("amount", 0) / 100, user_id, payment_method=pm_type, stripe_currency=intent.get("currency"))
                if result == "ORDER_ALREADY_CANCELLED":
                    try:
                        await run_in_threadpool(self.provider.process_refund, pi_id)
                    except Exception as refund_error:
                        logger.error("[PAYMENT RETRY] Refund failed for cancelled order %s", order_id[:8], exc_info=True)
                        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=PaymentSecurityMessages.ORDER_CANCELLED_REFUND_PENDING) from refund_error
                    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=PaymentSecurityMessages.ORDER_CANCELLED_AUTO_REFUNDED)
                if result not in {"SETTLED", "ALREADY_PAID"}:
                    logger.error("[PAYMENT SECURITY] Unexpected retry settlement result %r for order %s", result, order_id[:8])
                    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=PaymentSecurityMessages.RACE_CONDITION)
                coupon_id_order = (existing_order or {}).get("coupon_id")
                if coupon_id_order:
                    try:
                        from app.domains.coupons.repository import AsyncCouponRepository
                        await AsyncCouponRepository().record_redemption(coupon_id_order, user_id, order_id, float((existing_order or {}).get("discount_amount") or 0))
                    except Exception as coupon_exc:
                        logger.error("[PAYMENT] Coupon redemption failed (retry) for order %s: %s", order_id, coupon_exc)
                return {"status": OrderStatus.PAID.value, "message": PaymentMessages.RETRY_SUCCESSFUL}
            client_secret = intent.get("client_secret")
            if intent.get("status") == "canceled" or not client_secret:
                return await self._create_and_link_replacement_intent(user_id, order_id, amount_paise, ip_address=client_ip, user_agent=user_agent)
            await self._reserve_retry(order_id, user_id, pi_id)
            return {"client_secret": client_secret, "payment_intent_id": intent.get("id"), "order_id": order_id}
        except HTTPException:
            raise
        except Exception as exc:
            logger.warning("[PAYMENT RETRY] Stripe lookup failed for %s (%s). Falling back to new intent...", pi_id, exc)
            return await self._create_and_link_replacement_intent(user_id, order_id, amount_paise, ip_address=client_ip, user_agent=user_agent)

    async def _create_and_link_replacement_intent(self, user_id: str, order_id: str, amount_paise: int, ip_address: Optional[str] = None, user_agent: Optional[str] = None) -> Dict[str, Any]:
        # Reserve the retry slot before touching Stripe. The reservation is
        # bound to the newly-created PaymentIntent only after Stripe succeeds,
        # closing the concurrent replacement-intent race.
        admin_sb = await get_async_admin_supabase()
        try:
            reserved = await admin_sb.rpc(
                "reserve_payment_retry_replacement",
                {
                    "p_order_id": order_id,
                    "p_user_id": user_id,
                    "p_window_seconds": PaymentRules.BRUTE_FORCE_WINDOW_SEC,
                    "p_max_attempts": PaymentRules.BRUTE_FORCE_MAX_ATTEMPTS,
                },
            ).execute()
            data = getattr(reserved, "data", None)
            if not data:
                raise RuntimeError("Replacement retry reservation returned no data")
            reservation = data[0] if isinstance(data, list) else data
            reservation_id = str(reservation["reservation_id"])
        except Exception as exc:
            if "PAYMENT_RETRY_LIMIT:" in str(exc):
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=PaymentSecurityMessages.TOO_MANY_ATTEMPTS,
                ) from exc
            if "PAYMENT_ALREADY_SUCCEEDED" in str(exc):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=PaymentSecurityMessages.ALREADY_PAID,
                ) from exc
            logger.error("[PAYMENT RETRY] Unable to reserve replacement retry slot for order %s", order_id[:8], exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Unable to verify payment retry availability.",
            ) from exc

        try:
            new_intent = await run_in_threadpool(
                self.provider.create_payment_intent,
                amount_paise,
                "inr",
                "AOT_RETRY",
                user_id,
                f"retry_slot_{reservation_id}",
            )

            bound = await admin_sb.rpc(
                "bind_payment_retry_reservation",
                {
                    "p_reservation_id": reservation_id,
                    "p_provider": "stripe",
                    "p_provider_payment_id": new_intent["id"],
                },
            ).execute()
            if not bool(getattr(bound, "data", False)):
                try:
                    await run_in_threadpool(self.provider.cancel_intent, new_intent["id"])
                except Exception:
                    logger.error("[PAYMENT RETRY] Replacement intent cancellation failed for order %s", order_id[:8], exc_info=True)
                await admin_sb.rpc(
                    "release_payment_retry_reservation",
                    {"p_reservation_id": reservation_id},
                ).execute()
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=PaymentSecurityMessages.ORDER_NO_LONGER_RETRYABLE)

            linked = await self.repo.update_order_payment_intent(order_id, new_intent["id"])
            if not linked:
                try:
                    await run_in_threadpool(self.provider.cancel_intent, new_intent["id"])
                except Exception:
                    logger.error("[PAYMENT RETRY] Replacement intent cancellation failed for order %s", order_id[:8], exc_info=True)
                await admin_sb.rpc(
                    "release_payment_retry_reservation",
                    {"p_reservation_id": reservation_id},
                ).execute()
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=PaymentSecurityMessages.ORDER_NO_LONGER_RETRYABLE)

            await run_in_threadpool(
                self.provider.update_intent_metadata,
                new_intent["id"],
                {"order_id": order_id, "user_id": user_id},
            )
            await self.repo.record_payment_attempt(
                order_id,
                user_id,
                new_intent["id"],
                amount_paise / 100,
                status="requires_payment_method",
                ip_address=ip_address,
                user_agent=user_agent,
            )
            return {"client_secret": new_intent.get("client_secret"), "payment_intent_id": new_intent.get("id"), "order_id": order_id}
        except HTTPException:
            raise
        except Exception as exc:
            try:
                await admin_sb.rpc(
                    "release_payment_retry_reservation",
                    {"p_reservation_id": reservation_id},
                ).execute()
            except Exception:
                logger.critical("[PAYMENT RETRY] Failed to release retry reservation %s", reservation_id, exc_info=True)
            logger.error("[PAYMENT RETRY] Critical failure creating replacement intent: %s", exc, exc_info=True)
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=PaymentSecurityMessages.PAYMENT_FAILED) from exc

    async def record_client_reported_failure(self, user_id: str, pi_id: str, reason: str) -> None:
        order = await self.repo.get_order_by_payment_intent(pi_id)
        if not order or str(order.get("customer_id")) != str(user_id):
            return
        await self.repo.record_payment_attempt(order["id"], order.get("customer_id"), pi_id, float(order.get("total_amount") or 0), status="failed", error_message=reason or "Client-reported failure")

    async def handle_webhook(self, payload: bytes, sig_header: str) -> None:
        try:
            event = self.provider.verify_webhook(payload, sig_header)
        except Exception as e:
            logger.error("Webhook verification failed: %s", e)
            raise ValueError("Invalid Stripe Signature")
        event_id = event.get("id")
        event_type = event.get("type")
        obj = event.get("data", {}).get("object", {})
        pi_id = obj.get("id") if obj.get("object") == "payment_intent" else obj.get("payment_intent")
        if not pi_id:
            logger.warning("[WEBHOOK] Ignored %s - No Payment Intent ID found in payload.", event_type)
            return
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
        try:
            if event_type == "payment_intent.succeeded":
                if current_status == OrderStatus.PENDING.value:
                    amount = obj.get("amount", 0) / 100
                    pm_types = obj.get("payment_method_types", [])
                    pm_type = pm_types[0] if pm_types else "card"
                    result = await self.inventory.commit_reservation(order_id, pi_id, amount, customer_id, payment_method=pm_type, stripe_currency=obj.get("currency"))
                    if result == "ORDER_ALREADY_CANCELLED":
                        try:
                            await run_in_threadpool(self.provider.process_refund, pi_id)
                        except Exception as refund_exc:
                            logger.error("[WEBHOOK] Auto-refund FAILED for orphaned success %s", pi_id, exc_info=True)
                            raise RuntimeError("Automatic refund failed; webhook must remain retryable") from refund_exc
                    elif result == "SETTLED":
                        try:
                            get_event_bus().publish(OrderPaidEvent(order=order, customer_email=order.get("shipping_email") or order.get("billing_email") or "", customer_id=customer_id))
                        except Exception:
                            logger.error("[WEBHOOK] OrderPaidEvent publish FAILED for Order %s", order_id[:8], exc_info=True)
                    elif result == "ALREADY_PAID":
                        logger.info("[WEBHOOK] Order %s already settled", order_id[:8])
                    else:
                        raise RuntimeError(f"Unexpected settlement result: {result!r}")
            elif event_type == "payment_intent.payment_failed":
                if current_status == OrderStatus.PENDING.value:
                    reason = (obj.get("last_payment_error") or {}).get("message", "Payment failed")
                    error_code = (obj.get("last_payment_error") or {}).get("code")
                    amount = obj.get("amount", 0) / 100
                    pm_types = obj.get("payment_method_types", [])
                    pm_type = pm_types[0] if pm_types else "card"
                    await self.repo.record_payment_attempt(order_id, customer_id, pi_id, amount, status="failed", payment_method=pm_type, error_code=error_code, error_message=reason)
                    try:
                        get_event_bus().publish(OrderFailedEvent(order=order, customer_email=order.get("shipping_email") or order.get("billing_email") or "", customer_id=customer_id, reason="payment_failed"))
                    except Exception:
                        logger.error("[WEBHOOK] Failed to publish OrderFailedEvent", exc_info=True)
            elif event_type == "payment_intent.canceled":
                if current_status == OrderStatus.PENDING.value:
                    await self.inventory.release_reservation(
                        order_id,
                        reason=f"stripe_event:{event_type}",
                    )
            elif event_type == "charge.refunded":
                refund_rows = ((obj.get("refunds") or {}).get("data") or [])
                latest_refund = max(
                    refund_rows,
                    key=lambda row: int(row.get("created") or 0),
                    default=None,
                )
                if not latest_refund:
                    raise RuntimeError("charge.refunded webhook missing refund object")

                provider_refund_id = str(latest_refund.get("id") or "").strip()
                refund_amount = float(latest_refund.get("amount") or 0) / 100
                refund_status = str(latest_refund.get("status") or "succeeded").lower()
                if not provider_refund_id or refund_amount <= 0:
                    raise RuntimeError("charge.refunded webhook missing refund identity/amount")

                refund_record = await self.repo.record_provider_refund_event(
                    order_id=order_id,
                    provider="stripe",
                    provider_payment_id=pi_id,
                    provider_refund_id=provider_refund_id,
                    amount=refund_amount,
                    currency=str(latest_refund.get("currency") or obj.get("currency") or "INR"),
                    status=refund_status,
                    reason=latest_refund.get("reason"),
                    metadata={
                        "source": "stripe_webhook",
                        "event_id": event_id,
                        "charge_id": obj.get("id"),
                    },
                )

                fully_refunded = bool(refund_record.get("fully_refunded"))
                if refund_status == "succeeded" and fully_refunded and current_status in {OrderStatus.PAID.value, OrderStatus.PROCESSING.value}:
                    from app.domains.inventory.customer_cancellation import release_stock_for_customer_cancellation
                    updated = await release_stock_for_customer_cancellation(order_id, customer_id, "refunded")
                    if not updated:
                        raise RuntimeError("Full refund succeeded but inventory settlement failed")
                    try:
                        get_event_bus().publish(
                            OrderStatusChangedEvent(
                                order=updated,
                                customer_id=customer_id,
                                old_status=current_status,
                                new_status=OrderStatus.REFUNDED.value,
                            )
                        )
                    except Exception:
                        logger.error("[WEBHOOK] Failed to publish refund status event", exc_info=True)
                elif refund_status == "succeeded" and fully_refunded and current_status in {OrderStatus.SHIPPED.value, OrderStatus.DELIVERED.value}:
                    await self.repo.update_order_status_via_rpc(
                        order_id,
                        OrderStatus.REFUNDED.value,
                        f"Webhook Auto-Update: {event_type}",
                    )
                    try:
                        get_event_bus().publish(
                            OrderStatusChangedEvent(
                                order=order,
                                customer_id=customer_id,
                                old_status=current_status,
                                new_status=OrderStatus.REFUNDED.value,
                            )
                        )
                    except Exception:
                        logger.error("[WEBHOOK] Failed to publish refund status event", exc_info=True)
                elif refund_status == "succeeded":
                    logger.info(
                        "[WEBHOOK] Partial refund retained order state: order=%s refund=%s total_refunded=%s",
                        order_id[:8],
                        provider_refund_id,
                        refund_record.get("total_refunded"),
                    )
                logger.info(
                    "[WEBHOOK] Refund reconciled order=%s refund=%s status=%s",
                    order_id[:8],
                    provider_refund_id,
                    refund_record.get("status"),
                )
            elif event_type == "charge.dispute.created":
                amount_disputed = obj.get('amount', 0) / 100
                await self.repo.update_order_status_via_rpc(order_id, current_status, f"Dispute created: Rs. {amount_disputed}")
        except Exception:
            logger.error("[WEBHOOK] Processing FAILED for event %s (%s) on order %s -- leaving unmarked for retry.", event_id, event_type, order_id[:8], exc_info=True)
            raise
        if event_id:
            await self.repo.mark_webhook_event_processed(event_id)
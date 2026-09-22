"""Cash-on-delivery checkout orchestration.

COD intentionally does not create or confirm a Stripe PaymentIntent. It uses the
same server-side cart pricing, stock validation, address ownership and atomic
reservation path as card checkout.
"""
import logging
import os
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Dict, List, Optional

from email_validator import EmailNotValidError, validate_email
from fastapi import HTTPException, status
from nanoid import generate
from starlette.concurrency import run_in_threadpool

from app.constants.payment_messages import PaymentSecurityMessages
from app.domains.checkout.repository import AsyncCheckoutRepository
from app.domains.coupons.service import CouponService
from app.domains.pricing.service import PriceBreakdown, _shipping_tax, get_pricing_from_config
from app.domains.shipping.provider_service import ShippingProviderService
from app.enums.order_status import OrderStatus
from app.events.bus import OrderCreatedEvent, get_event_bus
from app.integrations.payments.registry import get_payment_provider
from app.permissions.policies.payment_policies import PaymentPolicy
from app.utils.phone import InvalidIndianMobile, normalize_indian_mobile

logger = logging.getLogger(__name__)


class CodOrderService:
    """Create a COD order without leaving a Stripe PaymentIntent attached."""

    def __init__(self) -> None:
        self.repo = AsyncCheckoutRepository()
        self.provider = get_payment_provider("stripe")

    @staticmethod
    def _order_number() -> str:
        value = generate("23456789ABCDEFGHJKLMNPQRSTUVWXYZ", 8)
        return f"ORD-{value[:4]}-{value[4:]}"

    async def create_order(
        self,
        user_id: str,
        address_id: str,
        idempotency_key: str,
        billing_address_id: Optional[str] = None,
        coupon_code: Optional[str] = None,
        shipping_courier_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        from app.permissions.action_control import assert_action_enabled

        await assert_action_enabled(
            user_id, "checkout", "Checkout is currently disabled for your account."
        )

        existing = await self.repo.get_order_by_idempotency_key(user_id, idempotency_key)
        if existing:
            if existing.get("status") != OrderStatus.PENDING.value:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=PaymentSecurityMessages.DUPLICATE_ORDER,
                )

            existing_pi = existing.get("stripe_payment_intent")
            if existing_pi:
                try:
                    intent = await run_in_threadpool(self.provider.retrieve_intent, existing_pi)
                    stripe_status = intent.get("status")
                    if stripe_status not in {"canceled", "succeeded"}:
                        await run_in_threadpool(self.provider.cancel_intent, existing_pi)
                    elif stripe_status == "succeeded":
                        raise HTTPException(
                            status_code=status.HTTP_409_CONFLICT,
                            detail="This payment was already completed. Please use the existing paid order.",
                        )
                except HTTPException:
                    raise
                except Exception as exc:
                    logger.error(
                        "[COD] Failed to safely cancel previous Stripe PI %s for order %s",
                        existing_pi,
                        existing.get("id"),
                        exc_info=True,
                    )
                    raise HTTPException(
                        status_code=status.HTTP_502_BAD_GATEWAY,
                        detail="Unable to switch this checkout to COD safely. Please try again.",
                    ) from exc

                cleared = await self.repo.clear_order_payment_intent(existing["id"], existing_pi)
                if not cleared:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="Checkout changed while switching payment method. Please try again.",
                    )

            return {
                "order_id": existing["id"],
                "order_number": existing.get("order_number", ""),
                "payment_method": "cod",
                "status": OrderStatus.PENDING.value,
                "total_amount": float(existing.get("total_amount") or 0),
            }

        PaymentPolicy.assert_no_active_pending_order(
            await self.repo.has_active_pending_order(user_id)
        )
        cart_items = await self.repo.get_cart_items_for_checkout(user_id)
        PaymentPolicy.assert_valid_cart(cart_items)

        items_to_deduct: List[Dict[str, Any]] = []
        subtotal = Decimal("0")
        for item in cart_items:
            product = item.get("products") or {}
            PaymentPolicy.assert_stock_availability(item["quantity"], product)
            snapshot = item.get("price_snapshot")
            if snapshot is None:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=PaymentSecurityMessages.RACE_CONDITION)
            locked_price = Decimal(str(snapshot))
            if locked_price < 0:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=PaymentSecurityMessages.RACE_CONDITION)
            line_total = locked_price * item["quantity"]
            subtotal += line_total
            hsn_code = str(product.get("hsn_code") or item.get("hsn_code") or "").strip()
            if not hsn_code:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=PaymentSecurityMessages.RACE_CONDITION)
            gst_raw = product.get("gst_percentage") if product.get("gst_percentage") is not None else item.get("gst_percentage")
            if gst_raw is None:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=PaymentSecurityMessages.RACE_CONDITION)
            items_to_deduct.append({
                "product_id": item["product_id"],
                "product_name": product.get("name", "Item"),
                "hsn_code": hsn_code,
                "gst_percentage": int(gst_raw),
                "unit_price": float(locked_price),
                "compare_price": float(product.get("compare_price") or 0.0),
                "quantity": item["quantity"],
                "subtotal": float(line_total),
            })

        config = await self.repo.get_pricing_config()
        breakdown = get_pricing_from_config(config).calculate(items=items_to_deduct)

        addr = await self.repo.get_shipping_address(address_id, user_id)
        if not addr:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=PaymentSecurityMessages.ADDRESS_NOT_FOUND)

        total_weight = Decimal("0")
        for item in cart_items:
            product = item.get("products") or {}
            raw_weight = product.get("weight")
            if raw_weight is None:
                continue
            try:
                weight = Decimal(str(raw_weight))
                if str(product.get("weight_unit") or "g").lower() == "g":
                    weight /= Decimal("1000")
                if weight > 0:
                    total_weight += weight * int(item.get("quantity") or 0)
            except (ArithmeticError, ValueError, TypeError):
                raise HTTPException(status_code=409, detail="Product shipping weight is invalid.")
        if total_weight <= 0:
            try:
                total_weight = Decimal(str(os.getenv("SHIPROCKET_RATE_DEFAULT_WEIGHT_KG", "0.5")))
            except (ArithmeticError, ValueError, TypeError):
                raise HTTPException(status_code=503, detail="Shiprocket default rate weight is misconfigured.")
        quote = await ShippingProviderService().quote_for_checkout(
            delivery_postcode=str(addr.get("postal_code") or ""),
            weight_kg=float(total_weight),
            cod=True,
            declared_value=float(subtotal),
            selected_courier_id=shipping_courier_id,
        )
        provider_shipping = Decimal(str(quote["selected"]["shipping_cost"]))
        product_tax = breakdown.tax - breakdown.shipping_tax
        provider_shipping_tax = _shipping_tax(items_to_deduct, provider_shipping, subtotal)
        breakdown = PriceBreakdown(
            subtotal=breakdown.subtotal,
            shipping=provider_shipping,
            tax=product_tax + provider_shipping_tax,
            total=breakdown.subtotal + provider_shipping + product_tax + provider_shipping_tax,
            currency=breakdown.currency,
            shipping_tax=provider_shipping_tax,
        )
        coupon_id = None
        coupon_discount = Decimal("0")
        coupon_resolved = coupon_code
        if coupon_code:
            resolved = await CouponService().resolve_discount_for_checkout(
                coupon_code, float(subtotal), user_id
            )
            coupon_discount = Decimal(str(resolved.get("discount") or 0))
            coupon_id = resolved.get("coupon_id")
            coupon_resolved = resolved.get("code")

        total = max(breakdown.total - coupon_discount, Decimal("0"))
        amount_paise = int((total * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
        PaymentPolicy.assert_minimum_amount(amount_paise)

        customer_email = await self.repo.get_customer_email(user_id)
        shipping_email = addr.get("email") or customer_email
        try:
            validate_email(shipping_email or "", check_deliverability=False)
        except EmailNotValidError as exc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=PaymentSecurityMessages.ADDRESS_EMAIL_MISSING) from exc

        billing = addr
        same_billing = True
        if billing_address_id and billing_address_id != address_id:
            billing = await self.repo.get_shipping_address(billing_address_id, user_id)
            if not billing:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=PaymentSecurityMessages.ADDRESS_NOT_FOUND)
            same_billing = False

        billing_email = billing.get("email") or customer_email
        try:
            validate_email(billing_email or "", check_deliverability=False)
        except EmailNotValidError as exc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=PaymentSecurityMessages.ADDRESS_EMAIL_MISSING) from exc

        try:
            shipping_phone = normalize_indian_mobile(addr.get("phone"))
            billing_phone = normalize_indian_mobile(billing.get("phone"))
        except InvalidIndianMobile as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid checkout phone number: {exc}",
            ) from exc

        order_number = self._order_number()
        order_data = {
            "customer_id": user_id,
            "status": OrderStatus.PENDING.value,
            "order_number": order_number,
            "idempotency_key": idempotency_key,
            "stripe_payment_intent": None,
            "coupon_id": coupon_id,
            "coupon_code": coupon_resolved,
            "discount_amount": float(coupon_discount),
            **breakdown.as_dict(),
            "total_amount": float(total),
            "shipping_provider": "shiprocket",
            "shipping_courier_id": quote["selected"].get("courier_id"),
            "shipping_courier_name": quote["selected"].get("courier_name"),
            "shipping_service_type": quote["selected"].get("service_type") or quote["selected"].get("service"),
            "shipping_delivery_mode": quote["selected"].get("delivery_mode"),
            "shipping_vehicle_type": quote["selected"].get("vehicle_type"),
            "shipping_address_id": address_id,
            "shipping_name": addr.get("full_name"),
            "shipping_phone": shipping_phone,
            "shipping_email": shipping_email,
            "shipping_line1": addr.get("line1"),
            "shipping_line2": addr.get("line2"),
            "shipping_landmark": addr.get("landmark"),
            "shipping_city": addr.get("city"),
            "shipping_state": addr.get("state"),
            "shipping_postal_code": addr.get("postal_code"),
            "shipping_country": addr.get("country", "IN"),
            "shipping_company_name": addr.get("company_name"),
            "shipping_gstin": addr.get("gstin"),
            "billing_same_as_shipping": same_billing,
            "billing_address_id": billing.get("id"),
            "billing_name": billing.get("full_name"),
            "billing_phone": billing_phone,
            "billing_email": billing_email,
            "billing_line1": billing.get("line1"),
            "billing_line2": billing.get("line2"),
            "billing_landmark": billing.get("landmark"),
            "billing_city": billing.get("city"),
            "billing_state": billing.get("state"),
            "billing_postal_code": billing.get("postal_code"),
            "billing_country": billing.get("country", "IN"),
            "billing_company_name": billing.get("company_name"),
            "billing_gstin": billing.get("gstin"),
        }

        try:
            order = await self.repo.create_pending_order_with_reservation(order_data, items_to_deduct)
        except HTTPException:
            raise
        except Exception as exc:
            raced = await self.repo.get_order_by_idempotency_key(user_id, idempotency_key)
            if raced and raced.get("status") == OrderStatus.PENDING.value:
                logger.info("[COD] Idempotency race converged to order %s", raced["id"])
                return {
                    "order_id": raced["id"],
                    "order_number": raced.get("order_number", ""),
                    "payment_method": "cod",
                    "status": OrderStatus.PENDING.value,
                    "total_amount": float(raced.get("total_amount") or 0),
                }
            logger.exception("COD order creation failed for user %s", user_id[:8])
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unable to create COD order. Please try again.") from exc

        try:
            from app.domains.cart.service import CartService
            await CartService().clear_cart(user_id)
        except Exception:
            pass

        try:
            get_event_bus().publish(OrderCreatedEvent(order=order, customer_email=shipping_email, customer_id=user_id))
        except Exception:
            logger.error("[COD] OrderCreatedEvent publish failed", exc_info=True)

        return {
            "order_id": order["id"],
            "order_number": order_number,
            "payment_method": "cod",
            "status": OrderStatus.PENDING.value,
            "total_amount": float(total),
        }

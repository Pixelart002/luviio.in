"""Cash-on-delivery checkout orchestration.

COD intentionally does not create or confirm a Stripe PaymentIntent. It uses the
same server-side cart pricing, stock validation, address ownership and atomic
reservation path as card checkout.
"""
from decimal import Decimal
from typing import Any, Dict, List, Optional
import logging

from email_validator import EmailNotValidError, validate_email
from fastapi import HTTPException, status
from nanoid import generate

from app.constants.payment_messages import PaymentSecurityMessages
from app.domains.coupons.service import CouponService
from app.domains.payments.repository import AsyncPaymentRepository
from app.domains.pricing.service import get_pricing_from_config
from app.enums.order_status import OrderStatus
from app.events.bus import OrderCreatedEvent, get_event_bus
from app.permissions.policies.payment_policies import PaymentPolicy

logger = logging.getLogger(__name__)


class CodOrderService:
    """Create a COD order without involving Stripe."""

    def __init__(self) -> None:
        self.repo = AsyncPaymentRepository()

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
    ) -> Dict[str, Any]:
        from app.permissions.action_control import assert_action_enabled

        await assert_action_enabled(
            user_id, "checkout", "Checkout is currently disabled for your account."
        )

        existing = await self.repo.get_order_by_idempotency_key(user_id, idempotency_key)
        if existing:
            if existing.get("status") == OrderStatus.PENDING.value:
                return {
                    "order_id": existing["id"],
                    "order_number": existing.get("order_number", ""),
                    "payment_method": "cod",
                }
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=PaymentSecurityMessages.DUPLICATE_ORDER,
            )

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
            locked_price = Decimal(str(snapshot if snapshot is not None else product.get("price", 0)))
            line_total = locked_price * item["quantity"]
            subtotal += line_total
            items_to_deduct.append({
                "product_id": item["product_id"],
                "product_name": product.get("name", "Item"),
                "hsn_code": str(product.get("hsn_code") or item.get("hsn_code") or "9988").strip(),
                "gst_percentage": int(
                    product.get("gst_percentage")
                    if product.get("gst_percentage") is not None
                    else (item.get("gst_percentage") if item.get("gst_percentage") is not None else 18)
                ),
                "unit_price": float(locked_price),
                "compare_price": float(product.get("compare_price") or 0.0),
                "quantity": item["quantity"],
                "subtotal": float(line_total),
            })

        config = await self.repo.get_pricing_config()
        breakdown = get_pricing_from_config(config).calculate(items=items_to_deduct)
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
        PaymentPolicy.assert_minimum_amount(int((total * 100).to_integral_value()))

        addr = await self.repo.get_shipping_address(address_id, user_id)
        if not addr:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=PaymentSecurityMessages.ADDRESS_NOT_FOUND,
            )

        # Address email is optional for checkout. Fall back to the authenticated
        # account email because the order schema already stores shipping_email.
        customer_email = await self.repo.get_customer_email(user_id)
        shipping_email = addr.get("email") or customer_email
        if shipping_email:
            try:
                validate_email(shipping_email, check_deliverability=False)
            except EmailNotValidError as exc:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=PaymentSecurityMessages.ADDRESS_EMAIL_MISSING,
                ) from exc

        billing = addr
        same_billing = True
        if billing_address_id and billing_address_id != address_id:
            fetched = await self.repo.get_shipping_address(billing_address_id, user_id)
            if not fetched:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=PaymentSecurityMessages.ADDRESS_NOT_FOUND,
                )
            billing = fetched
            same_billing = False
            billing_email = billing.get("email") or customer_email
            if billing_email:
                try:
                    validate_email(billing_email, check_deliverability=False)
                except EmailNotValidError as exc:
                    raise HTTPException(
                        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                        detail=PaymentSecurityMessages.ADDRESS_EMAIL_MISSING,
                    ) from exc
        else:
            billing_email = shipping_email

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
            "shipping_address_id": address_id,
            "shipping_name": addr.get("full_name"),
            "shipping_phone": addr.get("phone"),
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
            "billing_phone": billing.get("phone"),
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
            order = await self.repo.create_pending_order_with_reservation(
                order_data, items_to_deduct
            )
        except HTTPException:
            raise
        except Exception as exc:
            logger.exception("COD order creation failed for user %s", user_id[:8])
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Unable to create COD order. Please try again.",
            ) from exc

        try:
            from app.domains.cart.service import CartService
            await CartService().clear_cart(user_id)
        except Exception:
            # The order and stock reservation are already committed; cart cleanup
            # must not turn a successful COD order into a client-visible failure.
            pass

        try:
            get_event_bus().publish(
                OrderCreatedEvent(order=order, customer_email=customer_email, customer_id=user_id)
            )
        except Exception:
            pass

        return {
            "order_id": order["id"],
            "order_number": order_number,
            "payment_method": "cod",
            "status": OrderStatus.PENDING.value,
            "total_amount": float(total),
        }

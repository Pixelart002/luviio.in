"""
Payment Attribute-Based Access Control (ABAC) Policies
======================================================
Checkout authorization and invariant validation lives here; payment services
must not silently manufacture financial/legal values when source data is absent.
"""
import logging
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional

from fastapi import HTTPException, status

from app.constants.payment_messages import PaymentRules, PaymentSecurityMessages

logger = logging.getLogger(__name__)


class PaymentPolicy:
    @staticmethod
    def assert_valid_cart(cart_items: List[Dict[str, Any]]) -> None:
        if not cart_items:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=PaymentSecurityMessages.EMPTY_CART)

    @staticmethod
    def assert_stock_availability(quantity: int, product: Dict[str, Any]) -> None:
        if not isinstance(quantity, int) or quantity <= 0:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid cart quantity.")
        if not product.get("is_active") or int(product.get("stock", 0)) < quantity:
            logger.warning("ABAC Block | Checkout failed for out-of-stock item: %s", product.get("name"))
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=PaymentSecurityMessages.OUT_OF_STOCK.format(name=product.get("name", "Item")))
        price = product.get("price")
        hsn_code = product.get("hsn_code")
        gst_percentage = product.get("gst_percentage")
        if price is None or str(price).strip() == "":
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Product pricing data is unavailable. Checkout cannot continue.")
        if hsn_code is None or str(hsn_code).strip() == "":
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Product HSN data is unavailable. Checkout cannot continue.")
        if gst_percentage is None:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Product GST data is unavailable. Checkout cannot continue.")
        try:
            price_decimal = Decimal(str(price))
            gst_decimal = Decimal(str(gst_percentage))
            if not price_decimal.is_finite() or price_decimal < 0 or not gst_decimal.is_finite() or gst_decimal < 0:
                raise InvalidOperation
        except (InvalidOperation, ValueError, TypeError):
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Product financial data is invalid. Checkout cannot continue.")

    @staticmethod
    def assert_minimum_amount(amount_paise: int) -> None:
        if amount_paise < PaymentRules.MIN_ORDER_AMOUNT_PAISE:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=PaymentSecurityMessages.INVALID_AMOUNT.format(min_amount=PaymentRules.MIN_ORDER_AMOUNT_PAISE / 100))

    @staticmethod
    def assert_can_confirm(order: Optional[Dict[str, Any]], user_id: str) -> Dict[str, Any]:
        if not order:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=PaymentSecurityMessages.ORDER_NOT_FOUND)
        if str(order.get("customer_id", "")) != str(user_id):
            logger.warning("ABAC IDOR Block | User %s attempted to pay for Order owned by %s", user_id[:8], order.get("customer_id"))
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=PaymentSecurityMessages.UNAUTHORIZED_ACCESS)
        return order

    @staticmethod
    def assert_no_active_pending_order(has_pending: bool) -> None:
        """Legacy compatibility hook: pending orders do not block new orders.

        Multiple legitimate orders are allowed. Duplicate checkout attempts are
        prevented by the customer/idempotency-key database unique index; stock
        safety is enforced atomically by the reservation RPC.
        """
        return None

    @staticmethod
    def assert_can_retry(order: Optional[Dict[str, Any]], user_id: str) -> Dict[str, Any]:
        if not order or str(order.get("customer_id", "")) != str(user_id):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=PaymentSecurityMessages.ORDER_NOT_FOUND)
        return order

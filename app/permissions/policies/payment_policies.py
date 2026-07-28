"""
Payment Attribute-Based Access Control (ABAC) Policies
======================================================
Path: app/permissions/policies/payment_policies.py
"""
import logging
from typing import Dict, Any, Optional, List
from fastapi import HTTPException, status
from app.constants.payment_messages import PaymentSecurityMessages, PaymentRules

logger = logging.getLogger(__name__)

class PaymentPolicy:
    @staticmethod
    def assert_valid_cart(cart_items: List[Dict[str, Any]]) -> None:
        if not cart_items:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, 
                detail=PaymentSecurityMessages.EMPTY_CART
            )

    @staticmethod
    def assert_stock_availability(quantity: int, product: Dict[str, Any]) -> None:
        if not product.get("is_active") or int(product.get("stock", 0)) < quantity:
            logger.warning("ABAC Block | Checkout failed for out-of-stock item: %s", product.get('name'))
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, 
                detail=PaymentSecurityMessages.OUT_OF_STOCK.format(name=product.get("name", "Item"))
            )

    @staticmethod
    def assert_minimum_amount(amount_paise: int) -> None:
        if amount_paise < PaymentRules.MIN_ORDER_AMOUNT_PAISE:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, 
                detail=PaymentSecurityMessages.INVALID_AMOUNT.format(min_amount=PaymentRules.MIN_ORDER_AMOUNT_PAISE / 100)
            )

    @staticmethod
    def assert_can_confirm(order: Optional[Dict[str, Any]], user_id: str) -> Dict[str, Any]:
        if not order:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, 
                detail=PaymentSecurityMessages.ORDER_NOT_FOUND
            )

        if str(order.get("customer_id", "")) != str(user_id):
            logger.warning("ABAC IDOR Block | User %s attempted to pay for Order owned by %s", user_id[:8], order.get('customer_id'))
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, 
                detail=PaymentSecurityMessages.UNAUTHORIZED_ACCESS
            )

        return order

    @staticmethod
    def assert_no_active_pending_order(has_pending: bool) -> None:
        if has_pending:
            logger.warning("ABAC Block | Blocked attempt to create multiple pending orders (Inventory Hold Attack).")
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=PaymentSecurityMessages.ACTIVE_PENDING_EXISTS
            )

    @staticmethod
    def assert_can_retry(order: Optional[Dict[str, Any]], user_id: str) -> Dict[str, Any]:
        if not order or str(order.get("customer_id", "")) != str(user_id):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, 
                detail=PaymentSecurityMessages.ORDER_NOT_FOUND
            )
        return order
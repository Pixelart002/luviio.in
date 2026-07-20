"""
Payment Attribute-Based Access Control (ABAC) Policies
======================================================
Path: app/permissions/policies/payment_policies.py
"""
import logging
from typing import Dict, Any, Optional, List
from fastapi import HTTPException, status
from app.constants.payment_messages import PaymentSecurityMessages, PaymentRules
from app.enums.order_status import OrderStatus

logger = logging.getLogger(__name__)

class PaymentPolicy:

    @staticmethod
    def assert_valid_cart(cart_items: List[Dict[str, Any]]) -> None:
        """ABAC Guard: Prevents checkout on empty carts."""
        if not cart_items:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=PaymentSecurityMessages.EMPTY_CART)

    @staticmethod
    def assert_stock_availability(quantity: int, product: Dict[str, Any]) -> None:
        """ABAC Guard: Checks stock and active status before allowing payment."""
        if not product.get("is_active") or product.get("stock", 0) < quantity:
            logger.warning(f"ABAC Block | Checkout failed for out-of-stock item: {product.get('name')}")
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, 
                detail=PaymentSecurityMessages.OUT_OF_STOCK.format(name=product.get("name", "Item"))
            )

    @staticmethod
    def assert_minimum_amount(amount_paise: int) -> None:
        """ABAC Guard: Enforces minimum order transaction value."""
        if amount_paise < PaymentRules.MIN_ORDER_AMOUNT_PAISE:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, 
                detail=PaymentSecurityMessages.INVALID_AMOUNT.format(min_amount=PaymentRules.MIN_ORDER_AMOUNT_PAISE / 100)
            )

    @staticmethod
    def assert_can_confirm(order: Optional[Dict[str, Any]], user_id: str) -> Dict[str, Any]:
        """ABAC Guard: Verify order ownership and state before confirmation."""
        if not order:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=PaymentSecurityMessages.ORDER_NOT_FOUND)

        if str(order.get("customer_id", "")) != str(user_id):
            logger.warning(f"ABAC IDOR Block | User {user_id[:8]} attempted to pay for Order owned by {order.get('customer_id')}")
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=PaymentSecurityMessages.UNAUTHORIZED_ACCESS)

        return order
        
        
    # PaymentPolicy class ke andar ye naya method add karo:

    @staticmethod
    def assert_no_active_pending_order(has_pending: bool) -> None:
        """ABAC Guard: Enforces single active checkout session per user to prevent inventory exhaustion attacks."""
        if has_pending:
            logger.warning("ABAC Block | Blocked attempt to create multiple pending orders (Inventory Hold Attack).")
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=PaymentSecurityMessages.ACTIVE_PENDING_EXISTS
            )

    @staticmethod
    def assert_can_retry(order: Optional[Dict[str, Any]], user_id: str) -> None:
        """ABAC Guard: Ensures order belongs to user and is eligible for retry."""
        if not order or str(order.get("customer_id", "")) != str(user_id):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=PaymentSecurityMessages.ORDER_NOT_FOUND)
        
        if not order.get("stripe_payment_intent"):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=PaymentSecurityMessages.NO_INTENT_LINKED)
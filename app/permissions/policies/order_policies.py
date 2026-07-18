"""
Order Attribute-Based Access Control (ABAC) Policies
====================================================
Path: app/permissions/policies/order_policies.py
"""
import logging
from typing import Dict, Any, Optional
from fastapi import HTTPException, status
from app.enums.order_status import OrderStatus
from app.enums.roles import UserRole
from app.constants.order_messages import OrderSecurityMessages

logger = logging.getLogger(__name__)

class OrderPolicy:
    """Enforces strict ownership, tenancy, and state machine rules on orders."""

    @staticmethod
    def assert_can_view(order: Optional[Dict[str, Any]], current_user_id: str, is_admin: bool = False) -> Dict[str, Any]:
        """ABAC Guard: Enforces that regular users can only view their own orders."""
        if not order:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=OrderSecurityMessages.ORDER_NOT_FOUND)

        order_owner = str(order.get("customer_id", ""))
        if not is_admin and order_owner != str(current_user_id):
            logger.warning(f"ABAC IDOR Block | User {current_user_id[:8]} attempted to read Order owned by {order_owner[:8]}")
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=OrderSecurityMessages.UNAUTHORIZED_ACCESS)

        return order

    @staticmethod
    def assert_can_cancel(order: Dict[str, Any], current_user_id: str, is_admin: bool = False) -> None:
        """ABAC Guard: Enforces ownership and ensures order is in a cancellable state."""
        order_owner = str(order.get("customer_id", ""))
        if not is_admin and order_owner != str(current_user_id):
            logger.warning(f"ABAC IDOR Block | User {current_user_id[:8]} attempted to cancel Order owned by {order_owner[:8]}")
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=OrderSecurityMessages.UNAUTHORIZED_ACCESS)

        current_status = order.get("status", "")
        if current_status not in [OrderStatus.PENDING.value, OrderStatus.PAID.value]:
            logger.warning(f"ABAC State Block | Order status '{current_status}' cannot be cancelled")
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=OrderSecurityMessages.INVALID_CANCEL_STATE)

    @staticmethod
    def assert_can_download_invoice(order: Dict[str, Any], current_user_id: str, is_admin: bool = False) -> None:
        """ABAC Guard: Enforces ownership and verifies order is eligible for invoicing."""
        order_owner = str(order.get("customer_id", ""))
        if not is_admin and order_owner != str(current_user_id):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=OrderSecurityMessages.UNAUTHORIZED_ACCESS)

        valid_invoice_states = {OrderStatus.PAID.value, OrderStatus.SHIPPED.value, OrderStatus.DELIVERED.value, OrderStatus.REFUNDED.value}
        if order.get("status") not in valid_invoice_states:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=OrderSecurityMessages.INVOICE_UNAVAILABLE)
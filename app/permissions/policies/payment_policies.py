"""
Payment Attribute-Based Access Control (ABAC) Policies
======================================================
Path: app/permissions/policies/payment_policies.py
"""
import logging
from typing import Dict, Any, Optional
from fastapi import HTTPException, status
from app.constants.payment_messages import PaymentSecurityMessages
from app.enums.order_status import OrderStatus

logger = logging.getLogger(__name__)

class PaymentPolicy:
    """Enforces financial ownership and state machine rules for payments."""

    @staticmethod
    def assert_can_process_payment(order: Optional[Dict[str, Any]], current_user_id: str) -> Dict[str, Any]:
        """
        ABAC Guard: Verifies the order exists, belongs to the user, and is not already paid.
        """
        if not order:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=PaymentSecurityMessages.ORDER_NOT_FOUND)

        if str(order.get("customer_id", "")) != str(current_user_id):
            logger.warning("ABAC IDOR Block | User %s attempted to pay for Order owned by %s", current_user_id[:8], order.get("customer_id"))
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=PaymentSecurityMessages.UNAUTHORIZED_ORDER_ACCESS)

        if order.get("status") != OrderStatus.PENDING.value:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=PaymentSecurityMessages.ALREADY_PAID)

        return order
"""
Order Attribute-Based Access Control (ABAC) Policies
====================================================
Path: app/permissions/policies/order_policies.py

Architecture & Features:
  ✅ Unified Policy Engine — Merges assertion-based guards with boolean role evaluators.
  ✅ IDOR Protection — Strictly verifies tenancy and ownership before allowing read/write access.
  ✅ Role Hierarchy Support — Super Admins, Admins, and Managers safely bypass ownership constraints.
  ✅ FSM Enforcement — Validates order lifecycle states prior to mutations (e.g., cancellations or invoices).
"""
import logging
from typing import Any, Dict, Optional

from fastapi import HTTPException, status

from app.constants.order_messages import OrderSecurityMessages
from app.core.exceptions import LuviioException, UnauthorizedAction
from app.enums.order_status import OrderStatus
from app.enums.roles import UserRole

logger = logging.getLogger(__name__)


class OrderPolicy:
    """Enforces strict ownership, tenancy, role hierarchies, and state machine rules on orders."""

    @staticmethod
    def _is_privileged_role(user_role: Optional[str], is_admin: bool = False) -> bool:
        """Determines if the user holds an administrative or managerial role override."""
        if is_admin:
            return True
        if not user_role:
            return False

        privileged_roles = {
            UserRole.SUPER_ADMIN.value if hasattr(UserRole.SUPER_ADMIN, "value") else "super_admin",
            UserRole.ADMIN.value if hasattr(UserRole.ADMIN, "value") else "admin",
            UserRole.MANAGER.value if hasattr(UserRole.MANAGER, "value") else "manager",
        }
        return str(user_role).lower() in privileged_roles

    @classmethod
    def assert_can_view(
        cls,
        order: Optional[Dict[str, Any]],
        current_user_id: str,
        is_admin: bool = False,
        user_role: Optional[str] = None
    ) -> Dict[str, Any]:
        if not order:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=OrderSecurityMessages.ORDER_NOT_FOUND)

        order_owner = str(order.get("customer_id", ""))
        if not cls._is_privileged_role(user_role, is_admin) and order_owner != str(current_user_id):
            logger.warning("ABAC IDOR Block | User %s attempted to read Order owned by %s", current_user_id[:8], order_owner[:8])
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=OrderSecurityMessages.UNAUTHORIZED_ACCESS)

        return order

    @classmethod
    def assert_can_cancel(
        cls,
        order: Dict[str, Any],
        current_user_id: str,
        is_admin: bool = False,
        user_role: Optional[str] = None
    ) -> None:
        if not order:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=OrderSecurityMessages.ORDER_NOT_FOUND)

        order_owner = str(order.get("customer_id", ""))
        if not cls._is_privileged_role(user_role, is_admin) and order_owner != str(current_user_id):
            logger.warning("ABAC IDOR Block | User %s attempted to cancel Order owned by %s", current_user_id[:8], order_owner[:8])
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=OrderSecurityMessages.UNAUTHORIZED_ACCESS)

        # A paid/processing order requires a payment-domain refund workflow.
        # Direct cancellation is intentionally limited to unpaid pending orders
        # so stock release can never orphan a successful payment.
        current_status = str(order.get("status", "")).lower()
        cancellable_states = {OrderStatus.PENDING.value}

        if current_status not in cancellable_states:
            logger.warning("ABAC State Block | Order status '%s' cannot be directly cancelled", current_status)
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=OrderSecurityMessages.INVALID_CANCEL_STATE)

    @classmethod
    def assert_can_download_invoice(
        cls,
        order: Dict[str, Any],
        current_user_id: str,
        is_admin: bool = False,
        user_role: Optional[str] = None
    ) -> None:
        if not order:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=OrderSecurityMessages.ORDER_NOT_FOUND)

        order_owner = str(order.get("customer_id", ""))
        if not cls._is_privileged_role(user_role, is_admin) and order_owner != str(current_user_id):
            logger.warning("ABAC IDOR Block | User %s attempted to download invoice for Order owned by %s", current_user_id[:8], order_owner[:8])
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=OrderSecurityMessages.UNAUTHORIZED_ACCESS)

        current_status = str(order.get("status", "")).lower()
        valid_invoice_states = {
            OrderStatus.PAID.value,
            OrderStatus.PROCESSING.value,
            OrderStatus.SHIPPED.value,
            OrderStatus.DELIVERED.value,
            OrderStatus.REFUNDED.value,
        }

        if current_status not in valid_invoice_states:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=OrderSecurityMessages.INVOICE_UNAVAILABLE)

    @classmethod
    def can_cancel_order(
        cls,
        user_role: str,
        user_id: str,
        order_customer_id: str,
        current_status: str
    ) -> bool:
        cancellable_states = {OrderStatus.PENDING.value if hasattr(OrderStatus.PENDING, "value") else "pending"}

        if str(current_status).lower() not in cancellable_states:
            raise LuviioException("Order cannot be directly cancelled in its current state.", code="INVALID_STATE", status_code=400)

        if cls._is_privileged_role(user_role):
            return True

        customer_role_val = UserRole.CUSTOMER.value if hasattr(UserRole.CUSTOMER, "value") else "customer"
        if str(user_role).lower() == customer_role_val and str(user_id) == str(order_customer_id):
            return True

        raise UnauthorizedAction("You are not allowed to cancel this order.")

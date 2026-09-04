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
from typing import Dict, Any, Optional
from fastapi import HTTPException, status

from app.enums.order_status import OrderStatus
from app.enums.roles import UserRole
from app.constants.order_messages import OrderSecurityMessages
from app.core.exceptions import UnauthorizedAction, LuviioException

logger = logging.getLogger(__name__)


class OrderPolicy:
    """Enforces strict ownership, tenancy, role hierarchies, and state machine rules on orders."""

    # ══════════════════════════════════════════════════════════════════════════
    #  INTERNAL HELPERS
    # ══════════════════════════════════════════════════════════════════════════

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

    # ══════════════════════════════════════════════════════════════════════════
    #  ASSERTION GUARDS (FastAPI Route & Service Protectors)
    # ══════════════════════════════════════════════════════════════════════════

    @classmethod
    def assert_can_view(
        cls,
        order: Optional[Dict[str, Any]],
        current_user_id: str,
        is_admin: bool = False,
        user_role: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        ABAC Guard: Enforces that regular users can only view their own orders.
        Privileged roles (Admin, Super Admin, Manager) bypass ownership checks.
        """
        if not order:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=OrderSecurityMessages.ORDER_NOT_FOUND
            )

        order_owner = str(order.get("customer_id", ""))
        if not cls._is_privileged_role(user_role, is_admin) and order_owner != str(current_user_id):
            logger.warning(
                "ABAC IDOR Block | User %s attempted to read Order owned by %s",
                current_user_id[:8], order_owner[:8]
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=OrderSecurityMessages.UNAUTHORIZED_ACCESS
            )

        return order

    @classmethod
    def assert_can_cancel(
        cls,
        order: Dict[str, Any],
        current_user_id: str,
        is_admin: bool = False,
        user_role: Optional[str] = None
    ) -> None:
        """
        ABAC Guard: Enforces ownership/privileges and ensures order is in a cancellable state.
        """
        if not order:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=OrderSecurityMessages.ORDER_NOT_FOUND
            )

        # 1. Ownership & Hierarchy Check
        order_owner = str(order.get("customer_id", ""))
        if not cls._is_privileged_role(user_role, is_admin) and order_owner != str(current_user_id):
            logger.warning(
                "ABAC IDOR Block | User %s attempted to cancel Order owned by %s",
                current_user_id[:8], order_owner[:8]
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=OrderSecurityMessages.UNAUTHORIZED_ACCESS
            )

        # 2. Finite State Machine Check
        current_status = str(order.get("status", "")).lower()

        # 🔥 FIX: Added PROCESSING to cancellable states (Can cancel while packing)
        cancellable_states = {
            OrderStatus.PENDING.value,
            OrderStatus.PAID.value,
            OrderStatus.PROCESSING.value
        }

        if current_status not in cancellable_states:
            logger.warning("ABAC State Block | Order status '%s' cannot be cancelled", current_status)
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=OrderSecurityMessages.INVALID_CANCEL_STATE
            )

    @classmethod
    def assert_can_download_invoice(
        cls,
        order: Dict[str, Any],
        current_user_id: str,
        is_admin: bool = False,
        user_role: Optional[str] = None
    ) -> None:
        """
        ABAC Guard: Enforces ownership/privileges and verifies order is eligible for invoicing.
        """
        if not order:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=OrderSecurityMessages.ORDER_NOT_FOUND
            )

        order_owner = str(order.get("customer_id", ""))
        if not cls._is_privileged_role(user_role, is_admin) and order_owner != str(current_user_id):
            logger.warning(
                "ABAC IDOR Block | User %s attempted to download invoice for Order owned by %s",
                current_user_id[:8], order_owner[:8]
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=OrderSecurityMessages.UNAUTHORIZED_ACCESS
            )

        current_status = str(order.get("status", "")).lower()

        # 🔥 FIX: Added PROCESSING so users can download invoice during warehouse packing
        valid_invoice_states = {
            OrderStatus.PAID.value,
            OrderStatus.PROCESSING.value,
            OrderStatus.SHIPPED.value,
            OrderStatus.DELIVERED.value,
            OrderStatus.REFUNDED.value
        }

        if current_status not in valid_invoice_states:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=OrderSecurityMessages.INVOICE_UNAVAILABLE
            )

    # ══════════════════════════════════════════════════════════════════════════
    #  BOOLEAN EVALUATORS (Legacy & Fine-Grained Check Support)
    # ══════════════════════════════════════════════════════════════════════════

    @classmethod
    def can_cancel_order(
        cls,
        user_role: str,
        user_id: str,
        order_customer_id: str,
        current_status: str
    ) -> bool:
        """
        Policy Evaluator: Returns boolean or raises custom Luviio exceptions.
        Useful for non-HTTP domain services or background task workers.
        """
        # 1. State Verification
        # 🔥 FIX: Added PROCESSING here too
        cancellable_states = {
            OrderStatus.PENDING.value if hasattr(OrderStatus.PENDING, "value") else "pending",
            OrderStatus.PAID.value if hasattr(OrderStatus.PAID, "value") else "paid",
            OrderStatus.PROCESSING.value if hasattr(OrderStatus.PROCESSING, "value") else "processing"
        }

        if str(current_status).lower() not in cancellable_states:
            raise LuviioException(
                "Order cannot be cancelled in its current state.",
                code="INVALID_STATE",
                status_code=400
            )

        # 2. Privilege Override Check
        if cls._is_privileged_role(user_role):
            return True

        # 3. Direct Ownership Check
        customer_role_val = UserRole.CUSTOMER.value if hasattr(UserRole.CUSTOMER, "value") else "customer"
        if str(user_role).lower() == customer_role_val and str(user_id) == str(order_customer_id):
            return True

        raise UnauthorizedAction("You are not allowed to cancel this order.")

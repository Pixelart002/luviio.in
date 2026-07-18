"""
User Profile Attribute-Based Access Control (ABAC) Policies
===========================================================
Path: app/permissions/policies/user_policies.py
"""
import logging
from typing import Dict, Any
from fastapi import HTTPException, status
from app.constants.user_messages import UserSecurityMessages
from app.enums.roles import UserRole

logger = logging.getLogger(__name__)

class UserPolicy:
    """Enforces boundaries on addresses, account states, and admin self-modification."""

    @staticmethod
    def assert_address_limit(current_count: int, max_allowed: int = 10) -> None:
        """ABAC Guard: Prevents database bloat by limiting total user addresses."""
        if current_count >= max_allowed:
            logger.warning(f"ABAC Block | User reached address limit ({max_allowed}).")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, 
                detail=UserSecurityMessages.ADDRESS_LIMIT_EXCEEDED.format(limit=max_allowed)
            )

    @staticmethod
    def assert_address_not_locked(is_locked: bool) -> None:
        """ABAC Guard: Prevents deleting addresses currently attached to active fulfillment cycles."""
        if is_locked:
            logger.warning("ABAC Block | Attempted to delete a locked address tied to an active order.")
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, 
                detail=UserSecurityMessages.ADDRESS_LOCKED
            )

    @staticmethod
    def assert_admin_not_downgrading_self(admin_id: str, target_user_id: str, payload: Dict[str, Any]) -> None:
        """ABAC Guard: Prevents an admin from accidentally deactivating themselves or revoking their own admin role."""
        if str(admin_id) == str(target_user_id):
            target_role = payload.get("role")
            is_active = payload.get("is_active")

            if (target_role and target_role != UserRole.ADMIN.value) or is_active is False:
                logger.warning(f"ABAC Block | Admin {admin_id[:8]} attempted to demote or deactivate themselves.")
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN, 
                    detail=UserSecurityMessages.SELF_DEMOTION_PREVENTED
                )
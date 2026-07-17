"""
Authentication Attribute-Based Access Control (ABAC) Policies
=============================================================
Path: app/permissions/policies/auth_policies.py
"""
import logging
from typing import Dict, Any
from fastapi import HTTPException, status
from app.enums.roles import UserRole
from app.constants.auth_messages import AuthSecurityMessages

logger = logging.getLogger(__name__)

class AuthPolicy:
    """Enforces resource ownership and identity overrides for sensitive auth actions."""

    @staticmethod
    def assert_can_reset_password(current_user: Dict[str, Any], target_user_id: str) -> bool:
        """
        ABAC Guard: Prevents users from resetting passwords of other users.
        Allows override only if the actor is a Super Admin or System Admin.
        """
        actor_id = str(current_user.get("sub") or current_user.get("profile", {}).get("id", ""))
        actor_role = current_user.get("profile", {}).get("role", UserRole.CUSTOMER.value)

        # 1. Self-Ownership Check (User resetting their own password)
        if actor_id == str(target_user_id):
            return True

        # 2. Administrative Override Check
        if actor_role in [UserRole.SUPER_ADMIN.value, UserRole.ADMIN.value]:
            logger.info("Admin override granted for password reset | Actor: %s | Target: %s", actor_id[:8], target_user_id[:8])
            return True

        logger.warning("ABAC Violation | Actor: %s attempted to reset password for Target: %s", actor_id[:8], target_user_id[:8])
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=AuthSecurityMessages.UNAUTHORIZED_RESET
        )
"""
Admin Attribute-Based Access Control (ABAC) Policies
====================================================
Path: app/permissions/policies/admin_policies.py
"""
import logging
from typing import Dict, Any, Optional
from fastapi import HTTPException, status
from app.constants.admin_messages import AdminSecurityMessages
from app.enums.roles import UserRole

logger = logging.getLogger(__name__)

class AdminPolicy:
    @staticmethod
    def assert_is_active_admin(profile: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """ABAC Guard: Strictly verifies if the user profile exists, is active, and holds the Admin role."""
        if not profile:
            logger.warning("ABAC Block | Admin verification failed: No profile found.")
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=AdminSecurityMessages.PROFILE_NOT_FOUND)

        user_role = profile.get("role", "")
        is_active = profile.get("is_active", False)

        # Robust role check against Enum
        admin_role_val = UserRole.ADMIN.value if hasattr(UserRole.ADMIN, "value") else "admin"

        if user_role != admin_role_val or not is_active:
            logger.warning(f"ABAC Block | Unauthorized admin access attempt. Role: {user_role}, Active: {is_active}")
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=AdminSecurityMessages.UNAUTHORIZED_ROLE)

        return profile
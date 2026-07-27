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
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, 
                detail=AdminSecurityMessages.PROFILE_NOT_FOUND
            )

        user_role = profile.get("role", "")
        is_active = profile.get("is_active", False)

        admin_role_val = UserRole.ADMIN.value if hasattr(UserRole.ADMIN, "value") else "admin"
        super_admin_val = UserRole.SUPER_ADMIN.value if hasattr(UserRole, "SUPER_ADMIN") else "super_admin"

        if user_role not in {admin_role_val, super_admin_val} or not is_active:
            logger.warning("ABAC Block | Unauthorized admin access attempt. Role: %s, Active: %s", user_role, is_active)
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, 
                detail=AdminSecurityMessages.UNAUTHORIZED_ROLE
            )

        return profile
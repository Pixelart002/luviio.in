"""
Admin Attribute-Based Access Control (ABAC) Policies
====================================================
Path: app/permissions/policies/admin_policies.py
"""
import logging
from typing import Any, Dict, Optional

from fastapi import HTTPException, status

from app.constants.admin_messages import AdminSecurityMessages
from app.enums.roles import UserRole

logger = logging.getLogger(__name__)

class AdminPolicy:
    @staticmethod
    def assert_is_active_admin(profile: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """ABAC Guard: verifies that an active staff profile may enter the admin workspace."""
        if not profile:
            logger.warning("ABAC Block | Admin verification failed: No profile found.")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, 
                detail=AdminSecurityMessages.PROFILE_NOT_FOUND
            )

        user_role = profile.get("role", "")
        is_active = profile.get("is_active", False)

        staff_roles = {
            UserRole.ADMIN.value if hasattr(UserRole.ADMIN, "value") else "admin",
            UserRole.SUPER_ADMIN.value if hasattr(UserRole, "SUPER_ADMIN") else "super_admin",
            UserRole.MANAGER.value if hasattr(UserRole.MANAGER, "value") else "manager",
            UserRole.SUPPORT.value if hasattr(UserRole, "SUPPORT") else "support",
        }

        if user_role not in staff_roles or not is_active:
            logger.warning("ABAC Block | Unauthorized staff-console access attempt. Role: %s, Active: %s", user_role, is_active)
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, 
                detail=AdminSecurityMessages.UNAUTHORIZED_ROLE
            )

        return profile
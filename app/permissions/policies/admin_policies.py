"""
Admin Attribute-Based Access Control (ABAC) Policies
====================================================
Path: app/permissions/policies/admin_policies.py
"""
import logging
from typing import Dict, Any, Optional
from fastapi import HTTPException, status
from app.enums.roles import UserRole
from app.constants.messages import SecurityMessages

logger = logging.getLogger(__name__)

class AdminPolicy:
    """Enforces fine-grained attribute rules on live DB profiles."""
    
    @staticmethod
    def assert_can_access_portal(profile: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """
        ABAC Guard: Verifies account state and hierarchy before serving sensitive telemetry.
        Raises HTTP 403 if attributes do not satisfy security policies.
        """
        if not profile:
            logger.warning("ABAC Block | Reason: Profile missing in DB")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=SecurityMessages.PROFILE_NOT_FOUND
            )

        is_active = profile.get("is_active", False)
        if not is_active:
            logger.warning(f"ABAC Block | Reason: Deactivated account | UID: {profile.get('id')}")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=SecurityMessages.ACCOUNT_DEACTIVATED
            )

        role_str = profile.get("role", "")
        allowed_roles = [UserRole.SUPER_ADMIN.value, UserRole.ADMIN.value, UserRole.MANAGER.value]
        
        if role_str not in allowed_roles:
            logger.warning(f"ABAC Block | Reason: Insufficient role elevation ({role_str}) | UID: {profile.get('id')}")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=SecurityMessages.UNAUTHORIZED_ACCESS
            )

        return profile
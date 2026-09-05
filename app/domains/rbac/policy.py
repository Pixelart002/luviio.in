"""
RBAC Domain — Policy
====================
Path: app/domains/rbac/policy.py
"""
import logging

from fastapi import HTTPException, status

from app.enums.roles import UserRole

logger = logging.getLogger(__name__)


class RbacPolicy:
    @staticmethod
    def assert_role_manageable(actor_role: str, target_role: str) -> None:
        """
        God-Mode rule: only a super_admin may toggle permissions that belong to
        another super_admin. A regular admin can manage every other role but
        can never lock themselves out of the wildcard.
        """
        actor = str(actor_role).lower()
        target = str(target_role).lower()
        is_super_actor = actor == UserRole.SUPER_ADMIN.value
        if target == UserRole.SUPER_ADMIN.value and not is_super_actor:
            logger.warning("RBAC Block | non-super-admin '%s' tried to edit super_admin perms", actor_role)
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only a super_admin can modify super_admin permissions.",
            )

    @staticmethod
    def assert_not_self_lockout(actor_id: str, target_user_id: str, action: str, enabled: bool) -> None:
        """An admin should not be able to disable their OWN access — foot-gun guard."""
        if enabled:
            return
        if actor_id and actor_id == target_user_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"You cannot disable the '{action}' action on your own account.",
            )

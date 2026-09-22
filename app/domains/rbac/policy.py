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
        """Prevent RBAC self-escalation while preserving super-admin control.

        Rules:
        - super_admin may manage every role.
        - admin may manage only manager/support/customer permissions.
        - admin may not alter admin or super_admin role permissions.
        """
        actor = str(actor_role).lower()
        target = str(target_role).lower()

        if actor == UserRole.SUPER_ADMIN.value:
            return

        if actor == UserRole.ADMIN.value:
            if target in {
                UserRole.MANAGER.value,
                UserRole.SUPPORT.value,
                UserRole.CUSTOMER.value,
            }:
                return
            logger.warning(
                "RBAC Block | admin '%s' tried to edit privileged role '%s'",
                actor_role,
                target_role,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admins may only modify manager, support, or customer permissions.",
            )

        logger.warning(
            "RBAC Block | non-admin '%s' tried to edit role '%s'",
            actor_role,
            target_role,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only an admin or super_admin can modify role permissions.",
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

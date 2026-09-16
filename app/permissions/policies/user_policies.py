"""
User Profile Attribute-Based Access Control (ABAC) Policies
===========================================================
Path: app/permissions/policies/user_policies.py
"""
import logging
from typing import Any, Dict

from fastapi import HTTPException, status

from app.constants.user_messages import UserRules, UserSecurityMessages
from app.enums.roles import UserRole

logger = logging.getLogger(__name__)


class UserPolicy:
    """Enforces boundaries on addresses, account states, and role administration."""

    _ROLE_RANK = {
        UserRole.CUSTOMER.value: 10,
        UserRole.SUPPORT.value: 20,
        UserRole.MANAGER.value: 30,
        UserRole.ADMIN.value: 40,
        UserRole.SUPER_ADMIN.value: 50,
    }

    @classmethod
    def _role_name(cls, role: Any) -> str:
        if isinstance(role, UserRole):
            return role.value
        return str(role or UserRole.CUSTOMER.value).lower()

    @classmethod
    def assert_role_change_allowed(
        cls,
        actor_role: Any,
        current_target_role: Any,
        new_target_role: Any,
    ) -> None:
        """ABAC hierarchy guard for administrative role changes.

        Rules:
        - super_admin may manage every role.
        - admin may manage only roles below admin (manager/support/customer).
        - admin cannot create, promote, or modify super_admin/admin roles.
        - lower roles never reach this method because they lack users.update.
        """
        actor = cls._role_name(actor_role)
        current_target = cls._role_name(current_target_role)
        new_target = cls._role_name(new_target_role)

        if actor not in cls._ROLE_RANK or current_target not in cls._ROLE_RANK or new_target not in cls._ROLE_RANK:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Unknown user role.",
            )

        if actor == UserRole.SUPER_ADMIN.value:
            return

        actor_rank = cls._ROLE_RANK[actor]
        current_rank = cls._ROLE_RANK[current_target]
        new_rank = cls._ROLE_RANK[new_target]

        # An admin may only administer users strictly below its own tier.
        if actor == UserRole.ADMIN.value and (current_rank >= actor_rank or new_rank >= actor_rank):
            logger.warning(
                "ABAC Block | admin attempted role transition %s -> %s",
                current_target,
                new_target,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admins may only assign manager, support, or customer roles.",
            )

        # Defensive rule for any future privileged role with users.update.
        if actor_rank <= current_rank or actor_rank <= new_rank:
            logger.warning(
                "ABAC Block | role hierarchy violation actor=%s target=%s new=%s",
                actor,
                current_target,
                new_target,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You cannot modify a user at or above your role level.",
            )

    @staticmethod
    def assert_address_limit(current_count: int) -> None:
        """ABAC Guard: Prevents database bloat by limiting total user addresses."""
        if current_count >= UserRules.MAX_ADDRESSES_PER_USER:
            logger.warning("ABAC Block | User reached address limit (%d).", UserRules.MAX_ADDRESSES_PER_USER)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=UserSecurityMessages.ADDRESS_LIMIT_EXCEEDED.format(limit=UserRules.MAX_ADDRESSES_PER_USER),
            )

    # Address deletion intentionally uses soft-delete when an active order
    # references the address, so historical order snapshots remain safe.

    @staticmethod
    def assert_admin_not_downgrading_self(admin_id: str, target_user_id: str, payload: Dict[str, Any]) -> None:
        """ABAC Guard: Prevents an admin from accidentally deactivating themselves or revoking admin access."""
        if str(admin_id) == str(target_user_id):
            target_role = payload.get("role")
            is_active = payload.get("is_active")

            if (
                target_role is not None
                and UserPolicy._role_name(target_role) != UserRole.ADMIN.value
            ) or is_active is False:
                logger.warning("ABAC Block | Admin %s attempted to demote or deactivate themselves.", admin_id[:8])
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=UserSecurityMessages.SELF_DEMOTION_PREVENTED,
                )

"""
RBAC Domain — Service
======================
Path: app/domains/rbac/service.py
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List

from app.constants.rbac_messages import USER_ACTION_NOTES, USER_ACTIONS
from app.domains.rbac.action_control_repository import UserActionControlRepository
from app.domains.rbac.repository import AsyncRbacRepository
from app.enums.roles import UserRole
from app.permissions.action_control import invalidate_action_control_cache
from app.permissions.base import ROLE_PERMISSIONS
from app.permissions.overrides import (
    get_effective_permissions,
    invalidate_overrides_cache,
    static_descriptions,
)

logger = logging.getLogger(__name__)


class RolePermissionService:
    """Manages per-role permission toggles (the static matrix + DB overrides)."""

    def __init__(self) -> None:
        self.repo = AsyncRbacRepository()

    @staticmethod
    def roles() -> List[str]:
        return [r.value if hasattr(r, "value") else str(r) for r in UserRole]

    async def effective_matrix(self) -> Dict[str, List[str]]:
        matrix: Dict[str, List[str]] = {}
        for role in self.roles():
            base = set(ROLE_PERMISSIONS.get(role, []))
            effective = await get_effective_permissions(role, base)
            matrix[role] = ["*"] if "*" in effective else sorted(effective)
        return matrix

    async def list_overrides(self) -> List[Dict[str, Any]]:
        return await self.repo.list_role_overrides()

    async def set_override(self, role: str, permission: str, enabled: bool) -> Dict[str, Any]:
        if role not in self.roles():
            raise ValueError(f"Unknown role: {role}")
        saved = await self.repo.upsert_role_override(role, permission, enabled)
        invalidate_overrides_cache()
        return {"role": role, "permission": permission, "enabled": enabled, "saved": bool(saved)}

    async def remove_override(self, role: str, permission: str) -> Dict[str, Any]:
        await self.repo.delete_role_override(role, permission)
        invalidate_overrides_cache()
        return {"role": role, "permission": permission, "overridden": False}

    async def catalogue(self) -> Dict[str, Any]:
        return static_descriptions()


class UserActionControlService:
    """Per-user capability CRUD; persistence is encapsulated in its repository."""

    def __init__(self) -> None:
        self.repo = UserActionControlRepository()

    @staticmethod
    def action_catalogue() -> List[Dict[str, str]]:
        return [
            {"action": action, "note": USER_ACTION_NOTES[action]}
            for action in USER_ACTIONS
        ]

    @staticmethod
    def validate_action(action: str) -> None:
        if action not in USER_ACTION_NOTES:
            raise ValueError(f"Unknown user action: {action}")

    async def list_for_user(self, user_id: str) -> List[Dict[str, Any]]:
        return await self.repo.list(user_id)

    async def get_for_user(self, user_id: str, action: str) -> Dict[str, Any] | None:
        self.validate_action(action)
        return await self.repo.get(user_id, action)

    async def set_for_user(
        self,
        user_id: str,
        action: str,
        enabled: bool,
        actor_id: str,
        reason: str = "",
    ) -> Dict[str, Any]:
        self.validate_action(action)
        saved = await self.repo.create_or_update(user_id, action, enabled, actor_id, reason)
        invalidate_action_control_cache()
        return {
            "user_id": user_id,
            "action": action,
            "note": USER_ACTION_NOTES[action],
            "enabled": enabled,
            "saved": bool(saved),
        }

    async def remove_for_user(self, user_id: str, action: str) -> Dict[str, Any]:
        self.validate_action(action)
        await self.repo.delete(user_id, action)
        invalidate_action_control_cache()
        return {
            "user_id": user_id,
            "action": action,
            "note": USER_ACTION_NOTES[action],
            "enabled": True,
        }

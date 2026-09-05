"""
RBAC Domain — Service
======================
Path: app/domains/rbac/service.py
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List

from app.domains.rbac.repository import AsyncRbacRepository
from app.enums.roles import UserRole
from app.permissions.base import ROLE_PERMISSIONS
from app.permissions.overrides import get_effective_permissions, invalidate_overrides_cache, static_descriptions
from app.permissions.action_control import invalidate_action_control_cache

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
        invalidate_overrides_cache()  # next require_permission re-reads the table
        return {"role": role, "permission": permission, "enabled": enabled, "saved": bool(saved)}

    async def remove_override(self, role: str, permission: str) -> Dict[str, Any]:
        await self.repo.delete_role_override(role, permission)
        invalidate_overrides_cache()
        return {"role": role, "permission": permission, "overridden": False}

    async def catalogue(self) -> Dict[str, Any]:
        return static_descriptions()


class UserActionControlService:
    """Manages per-user capability gating (disable/enable a specific user's actions)."""

    def __init__(self) -> None:
        self.repo = AsyncRbacRepository()

    async def list_for_user(self, user_id: str) -> List[Dict[str, Any]]:
        return await self.repo.list_user_controls(user_id)

    async def set_for_user(self, user_id: str, action: str, enabled: bool,
                           actor_id: str, reason: str = "") -> Dict[str, Any]:
        saved = await self.repo.upsert_user_control(user_id, action, enabled, actor_id, reason)
        invalidate_action_control_cache()
        return {"user_id": user_id, "action": action, "enabled": enabled, "saved": bool(saved)}

    async def remove_for_user(self, user_id: str, action: str) -> Dict[str, Any]:
        await self.repo.delete_user_control(user_id, action)
        invalidate_action_control_cache()
        return {"user_id": user_id, "action": action, "enabled": True}

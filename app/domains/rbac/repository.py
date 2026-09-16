"""
RBAC Domain — Repository
=========================
Path: app/domains/rbac/repository.py

Role permission persistence only. Per-user action-control CRUD is encapsulated
in `action_control_repository.py`.
"""
import logging
from typing import Any, List, Optional

from app.core.supabase import get_async_admin_supabase

logger = logging.getLogger(__name__)


class AsyncRbacRepository:
    """Persistence boundary for role-level permission overrides."""

    async def list_role_overrides(self) -> List[dict[str, Any]]:
        sb = await get_async_admin_supabase()
        try:
            res = await sb.table("role_permissions").select("*").order("role").execute()
            return res.data if res and res.data else []
        except Exception as exc:
            logger.error("[RBAC:REPO] list_role_overrides failed: %s", exc)
            return []

    async def upsert_role_override(
        self,
        role: str,
        permission: str,
        enabled: bool,
    ) -> Optional[dict[str, Any]]:
        sb = await get_async_admin_supabase()
        try:
            res = await (
                sb.table("role_permissions")
                .upsert(
                    {"role": role, "permission": permission, "enabled": enabled},
                    on_conflict="role,permission",
                )
                .maybe_single()
                .execute()
            )
            return res.data if res else None
        except Exception as exc:
            logger.error("[RBAC:REPO] upsert_role_override failed: %s", exc)
            return None

    async def delete_role_override(self, role: str, permission: str) -> bool:
        sb = await get_async_admin_supabase()
        try:
            await (
                sb.table("role_permissions")
                .delete()
                .eq("role", role)
                .eq("permission", permission)
                .execute()
            )
            return True
        except Exception as exc:
            logger.error("[RBAC:REPO] delete_role_override failed: %s", exc)
            return False

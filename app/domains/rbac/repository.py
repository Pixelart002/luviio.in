"""
RBAC Domain — Repository
=========================
Path: app/domains/rbac/repository.py
"""
import logging
from typing import Any, List, Optional

from app.core.supabase import get_async_admin_supabase

logger = logging.getLogger(__name__)


class AsyncRbacRepository:
    """Reads/writes role_permissions overrides and user_action_controls."""

    # ── Role-level overrides ───────────────────────────────────────────────
    async def list_role_overrides(self) -> List[dict[str, Any]]:
        sb = await get_async_admin_supabase()
        try:
            res = await sb.table("role_permissions").select("*").order("role").execute()
            return res.data if res and res.data else []
        except Exception as exc:
            logger.error("[RBAC:REPO] list_role_overrides failed: %s", exc)
            return []

    async def upsert_role_override(self, role: str, permission: str, enabled: bool) -> Optional[dict[str, Any]]:
        sb = await get_async_admin_supabase()
        try:
            res = await (
                sb.table("role_permissions")
                .upsert({"role": role, "permission": permission, "enabled": enabled},
                        on_conflict="role,permission")
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
                sb.table("role_permissions").delete().eq("role", role).eq("permission", permission).execute()
            )
            return True
        except Exception as exc:
            logger.error("[RBAC:REPO] delete_role_override failed: %s", exc)
            return False

    # ── User-level action controls ─────────────────────────────────────────
    async def list_user_controls(self, user_id: str) -> List[dict[str, Any]]:
        sb = await get_async_admin_supabase()
        try:
            res = await (
                sb.table("user_action_controls").select("*").eq("user_id", user_id)
                .order("created_at", desc=True).execute()
            )
            return res.data if res and res.data else []
        except Exception as exc:
            logger.error("[RBAC:REPO] list_user_controls failed: %s", exc)
            return []

    async def upsert_user_control(self, user_id: str, action: str, enabled: bool,
                                  actor_id: str, reason: str = "") -> Optional[dict[str, Any]]:
        sb = await get_async_admin_supabase()
        try:
            res = await (
                sb.table("user_action_controls")
                .upsert({"user_id": user_id, "action": action, "enabled": enabled,
                         "reason": reason, "updated_by": actor_id},
                        on_conflict="user_id,action")
                .maybe_single()
                .execute()
            )
            return res.data if res else None
        except Exception as exc:
            logger.error("[RBAC:REPO] upsert_user_control failed: %s", exc)
            return None

    async def delete_user_control(self, user_id: str, action: str) -> bool:
        sb = await get_async_admin_supabase()
        try:
            await (
                sb.table("user_action_controls").delete().eq("user_id", user_id).eq("action", action).execute()
            )
            return True
        except Exception as exc:
            logger.error("[RBAC:REPO] delete_user_control failed: %s", exc)
            return False

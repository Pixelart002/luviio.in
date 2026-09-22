"""
RBAC User Action Control Repository
===================================
Path: app/domains/rbac/action_control_repository.py

Encapsulates CRUD access for per-user action controls so the RBAC service
never talks to Supabase directly.
"""
from __future__ import annotations

import logging
from typing import Any, List, Optional

from app.core.supabase import get_async_admin_supabase

logger = logging.getLogger(__name__)


class UserActionControlRepository:
    """Persistence boundary for user_action_controls CRUD operations."""

    async def list(self, user_id: str) -> List[dict[str, Any]]:
        sb = await get_async_admin_supabase()
        try:
            res = await (
                sb.table("user_action_controls")
                .select("*")
                .eq("user_id", user_id)
                .order("created_at", desc=True)
                .execute()
            )
            return res.data if res and res.data else []
        except Exception:
            logger.exception("[RBAC:ACTION_REPO] list failed for user %s", user_id)
            raise

    async def get(self, user_id: str, action: str) -> Optional[dict[str, Any]]:
        sb = await get_async_admin_supabase()
        try:
            res = await (
                sb.table("user_action_controls")
                .select("*")
                .eq("user_id", user_id)
                .eq("action", action)
                .maybe_single()
                .execute()
            )
            return res.data if res else None
        except Exception:
            logger.exception(
                "[RBAC:ACTION_REPO] get failed for user=%s action=%s",
                user_id,
                action,
            )
            raise

    async def create_or_update(
        self,
        user_id: str,
        action: str,
        enabled: bool,
        actor_id: str,
        reason: str = "",
    ) -> Optional[dict[str, Any]]:
        sb = await get_async_admin_supabase()
        try:
            res = await (
                sb.table("user_action_controls")
                .upsert(
                    {
                        "user_id": user_id,
                        "action": action,
                        "enabled": enabled,
                        "reason": reason,
                        "updated_by": actor_id,
                    },
                    on_conflict="user_id,action",
                )
                .maybe_single()
                .execute()
            )
            return res.data if res else None
        except Exception:
            logger.exception(
                "[RBAC:ACTION_REPO] create_or_update failed for user=%s action=%s",
                user_id,
                action,
            )
            raise

    async def delete(self, user_id: str, action: str) -> bool:
        sb = await get_async_admin_supabase()
        try:
            res = await (
                sb.table("user_action_controls")
                .delete()
                .eq("user_id", user_id)
                .eq("action", action)
                .execute()
            )
            return bool(res)
        except Exception:
            logger.exception(
                "[RBAC:ACTION_REPO] delete failed for user=%s action=%s",
                user_id,
                action,
            )
            raise

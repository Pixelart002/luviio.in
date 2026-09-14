"""
Shipping Domain — Repository
=============================
"""
import logging
from typing import Any, List, Optional

from app.core.supabase import get_async_admin_supabase

logger = logging.getLogger(__name__)


class AsyncShippingRepository:
    async def list_active_methods(self) -> List[dict[str, Any]]:
        sb = await get_async_admin_supabase()
        try:
            res = await (
                sb.table("shipping_methods")
                .select("*")
                .eq("is_active", True)
                .order("sort_order")
                .execute()
            )
            return res.data or []
        except Exception as exc:
            logger.error("[REPO:SHIPPING] list_active failed: %s", exc)
            return []

    async def list_all(self) -> List[dict[str, Any]]:
        sb = await get_async_admin_supabase()
        try:
            res = await sb.table("shipping_methods").select("*").order("sort_order").execute()
            return res.data or []
        except Exception as exc:
            logger.error("[REPO:SHIPPING] list_all failed: %s", exc)
            return []

    async def get_by_id(self, method_id: str) -> Optional[dict[str, Any]]:
        sb = await get_async_admin_supabase()
        try:
            res = await (
                sb.table("shipping_methods")
                .select("*")
                .eq("id", method_id)
                .maybe_single()
                .execute()
            )
            return res.data if res else None
        except Exception as exc:
            logger.error("[REPO:SHIPPING] get_by_id failed: %s", exc)
            return None

    async def create(self, data: dict[str, Any]) -> Optional[dict[str, Any]]:
        sb = await get_async_admin_supabase()
        try:
            res = await sb.table("shipping_methods").insert(data).maybe_single().execute()
            return res.data if res else None
        except Exception as exc:
            logger.error("[REPO:SHIPPING] create failed: %s", exc)
            return None

    async def update(self, method_id: str, data: dict[str, Any]) -> Optional[dict[str, Any]]:
        sb = await get_async_admin_supabase()
        try:
            res = await (
                sb.table("shipping_methods")
                .update(data)
                .eq("id", method_id)
                .maybe_single()
                .execute()
            )
            return res.data if res else None
        except Exception as exc:
            logger.error("[REPO:SHIPPING] update failed: %s", exc)
            return None

    async def activate_atomic(self, method_id: str) -> Optional[dict[str, Any]]:
        """Switch the active method in one Postgres transaction."""
        sb = await get_async_admin_supabase()
        try:
            res = await sb.rpc("activate_shipping_method", {"p_method_id": method_id}).execute()
            data = getattr(res, "data", None)
            if isinstance(data, list):
                return data[0] if data else None
            return data if isinstance(data, dict) else None
        except Exception as exc:
            logger.error("[REPO:SHIPPING] activate_atomic failed: %s", exc)
            return None

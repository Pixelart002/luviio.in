"""
User Repository — Async Hardened Production Grade
=================================================
Path: app/repositories/user_repo.py
"""
import logging
from typing import Any, Dict, List, Optional, Tuple
from app.core.supabase import get_async_admin_supabase

logger = logging.getLogger(__name__)

class AsyncUserRepository:
    def __init__(self) -> None:
        pass

    # ── Profile Management ───────────────────────────────────────────────
    async def upsert_profile(self, user_id: str, email: str, full_name: str, phone: str = "") -> Optional[Dict[str, Any]]:
        admin_sb = await get_async_admin_supabase()
        try:
            await admin_sb.table("users").upsert({
                "id": user_id, "email": email, "full_name": full_name, "phone": phone,
            }, on_conflict="id").execute()
            return await self.get_user_by_id(user_id)
        except Exception as e:
            logger.error("Failed to upsert user profile | id=%s: %s", user_id[:8], e, exc_info=True)
            raise

    async def get_user_by_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        admin_sb = await get_async_admin_supabase()
        try:
            res = await admin_sb.table("users").select("id, email, full_name, phone, role, is_active, created_at").eq("id", user_id).limit(1).execute()
            data_list = getattr(res, "data", None)
            return data_list[0] if data_list else None
        except Exception as e:
            logger.error("Error fetching user %s: %s", user_id[:8], e)
            return None

    async def get_profile(self, user_id: str) -> Optional[Dict[str, Any]]:
        return await self.get_user_by_id(user_id)

    async def update_profile(self, user_id: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        admin_sb = await get_async_admin_supabase()
        res = await admin_sb.table("users").update(data).eq("id", user_id).execute()
        data_list = getattr(res, "data", None)
        return data_list[0] if data_list else None

    # ── Address Management ───────────────────────────────────────────────
    async def get_user_addresses(self, user_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        admin_sb = await get_async_admin_supabase()
        res = await admin_sb.table("addresses").select("*").eq("user_id", user_id).order("is_default", desc=True).order("created_at", desc=True).limit(limit).execute()
        return getattr(res, "data", None) or []

    async def count_user_addresses(self, user_id: str) -> int:
        admin_sb = await get_async_admin_supabase()
        res = await admin_sb.table("addresses").select("id", count="exact").eq("user_id", user_id).limit(1).execute()
        return res.count or 0

    async def unset_default_address(self, user_id: str) -> None:
        admin_sb = await get_async_admin_supabase()
        await admin_sb.table("addresses").update({"is_default": False}).eq("user_id", user_id).execute()

    async def create_address(self, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        admin_sb = await get_async_admin_supabase()
        res = await admin_sb.table("addresses").insert(data).execute()
        data_list = getattr(res, "data", None)
        return data_list[0] if data_list else None

    async def get_address(self, address_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        admin_sb = await get_async_admin_supabase()
        res = await admin_sb.table("addresses").select("id, is_default").eq("id", address_id).eq("user_id", user_id).limit(1).execute()
        data_list = getattr(res, "data", None)
        return data_list[0] if data_list else None

    async def is_address_in_active_order(self, address_id: str) -> bool:
        admin_sb = await get_async_admin_supabase()
        res = await admin_sb.table("orders").select("id").eq("shipping_address_id", address_id).in_("status", ["pending", "paid", "shipped"]).limit(1).execute()
        return bool(getattr(res, "data", None))

    async def delete_address(self, address_id: str) -> None:
        admin_sb = await get_async_admin_supabase()
        await admin_sb.table("addresses").delete().eq("id", address_id).execute()

    async def set_new_default_address(self, user_id: str) -> None:
        admin_sb = await get_async_admin_supabase()
        res = await admin_sb.table("addresses").select("id").eq("user_id", user_id).limit(1).execute()
        data_list = getattr(res, "data", None)
        if data_list:
            await admin_sb.table("addresses").update({"is_default": True}).eq("id", data_list[0]["id"]).execute()

    # ── Admin Functions ──────────────────────────────────────────────────
    async def get_users_paginated(self, page: int, page_size: int, search: Optional[str], role_filter: Optional[str]) -> Tuple[List[Dict[str, Any]], int]:
        admin_sb = await get_async_admin_supabase()
        q = admin_sb.table("users").select("id, email, full_name, phone, role, is_active, created_at", count="exact").order("created_at", desc=True)
        if search: 
            q = q.or_(f"email.ilike.%{search}%,full_name.ilike.%{search}%")
        if role_filter: 
            q = q.eq("role", role_filter)
        
        offset = (page - 1) * page_size
        res = await q.range(offset, offset + page_size - 1).execute()
        return getattr(res, "data", None) or [], res.count or 0

    async def count_user_orders(self, user_id: str) -> int:
        admin_sb = await get_async_admin_supabase()
        res = await admin_sb.table("orders").select("id", count="exact").eq("customer_id", user_id).limit(1).execute()
        return res.count or 0
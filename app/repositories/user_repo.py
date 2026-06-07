"""
User Repository
================
Path: app/repositories/user_repo.py
"""
import logging
from typing import Any
from .base import BaseRepository

logger = logging.getLogger(__name__)

class UserRepository(BaseRepository):
    
    # ── Profile Management ───────────────────────────────────────────────────
    def upsert_profile(self, user_id: str, email: str, full_name: str) -> None:
        try:
            self.admin_sb.table("users").upsert(
                {"id": user_id, "email": email, "full_name": full_name},
                on_conflict="id"
            ).execute()
        except Exception as e:
            logger.error("Failed to upsert user profile | id=%s: %s", user_id[:8], e)
            raise

    def get_user_by_id(self, user_id: str) -> dict[str, Any] | None:
        res = self.admin_sb.table("users").select("id, email, full_name, phone, role, is_active, created_at").eq("id", user_id).limit(1).execute()
        return res.data[0] if getattr(res, "data", None) else None

    def update_profile(self, user_id: str, data: dict) -> dict[str, Any] | None:
        res = self.admin_sb.table("users").update(data).eq("id", user_id).execute()
        return res.data[0] if getattr(res, "data", None) else None

    # ── Address Management ───────────────────────────────────────────────────
    def get_user_addresses(self, user_id: str, limit: int = 10) -> list[dict[str, Any]]:
        res = self.admin_sb.table("addresses").select("*").eq("user_id", user_id).order("is_default", desc=True).order("created_at", desc=True).limit(limit).execute()
        return getattr(res, "data", None) or []

    def count_user_addresses(self, user_id: str) -> int:
        res = self.admin_sb.table("addresses").select("id", count="exact").eq("user_id", user_id).limit(1).execute()
        return res.count or 0

    def unset_default_address(self, user_id: str) -> None:
        self.admin_sb.table("addresses").update({"is_default": False}).eq("user_id", user_id).execute()

    def create_address(self, data: dict) -> dict[str, Any] | None:
        res = self.admin_sb.table("addresses").insert(data).execute()
        return res.data[0] if getattr(res, "data", None) else None

    def get_address(self, address_id: str, user_id: str) -> dict[str, Any] | None:
        res = self.admin_sb.table("addresses").select("id, is_default").eq("id", address_id).eq("user_id", user_id).limit(1).execute()
        return res.data[0] if getattr(res, "data", None) else None

    def is_address_in_active_order(self, address_id: str) -> bool:
        res = self.admin_sb.table("orders").select("id").eq("shipping_address_id", address_id).in_("status", ["pending", "paid", "shipped"]).limit(1).execute()
        return bool(getattr(res, "data", None))

    def delete_address(self, address_id: str) -> None:
        self.admin_sb.table("addresses").delete().eq("id", address_id).execute()

    def set_new_default_address(self, user_id: str) -> None:
        res = self.admin_sb.table("addresses").select("id").eq("user_id", user_id).limit(1).execute()
        if getattr(res, "data", None):
            self.admin_sb.table("addresses").update({"is_default": True}).eq("id", res.data[0]["id"]).execute()

    # ── Admin Functions ──────────────────────────────────────────────────────
    def get_users_paginated(self, page: int, page_size: int, search: str | None, role_filter: str | None) -> tuple[list, int]:
        q = self.admin_sb.table("users").select("id, email, full_name, phone, role, is_active, created_at", count="exact").order("created_at", desc=True)
        if search: q = q.or_(f"email.ilike.%{search}%,full_name.ilike.%{search}%")
        if role_filter: q = q.eq("role", role_filter)
        
        offset = (page - 1) * page_size
        res = q.range(offset, offset + page_size - 1).execute()
        return getattr(res, "data", None) or [], res.count or 0

    def count_user_orders(self, user_id: str) -> int:
        res = self.admin_sb.table("orders").select("id", count="exact").eq("customer_id", user_id).limit(1).execute()
        return res.count or 0
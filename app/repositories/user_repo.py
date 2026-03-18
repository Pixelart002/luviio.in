"""
User Repository — Repository Pattern
Fix: maybe_single() + Supabase 406 → execute() returns None → AttributeError
Solution: Use .limit(1).execute() instead — always returns a result object,
          never None. data=[] if not found, data=[{...}] if found.
"""
from __future__ import annotations

import logging
from typing import Any

from supabase import Client

logger = logging.getLogger(__name__)


class UserRepository:

    def __init__(self, sb: Client) -> None:
        self._sb = sb

    def get_profile(self, user_id: str) -> dict[str, Any] | None:
        """
        FIX: Replaced maybe_single() with limit(1).execute()
        
        WHY: maybe_single() sends Accept: application/vnd.pgrst.object+json
             Supabase returns 406 Not Acceptable in some cases
             → supabase-py execute() returns None → AttributeError on .data
        
        limit(1).execute() always returns a result object with .data list
             data = []      → user not found → return None
             data = [{...}] → user found     → return dict
        """
        try:
            result = (
                self._sb.table("users")
                .select("id, email, full_name, phone, role, is_active, created_at")
                .eq("id", user_id)
                .limit(1)
                .execute()
            )
            if result is None or not result.data:
                return None
            return result.data[0]
        except Exception as e:
            logger.error("get_profile failed for user %s: %s", user_id, e)
            return None

    def upsert_profile(self, user_id: str, email: str, full_name: str = "") -> dict[str, Any]:
        try:
            result = (
                self._sb.table("users")
                .upsert(
                    {
                        "id":        user_id,
                        "email":     email,
                        "full_name": full_name,
                        "role":      "customer",
                        "is_active": True,
                    },
                    on_conflict="id",
                    ignore_duplicates=True,
                )
                .execute()
            )
            if result and result.data:
                return result.data[0]
            # upsert did nothing (duplicate) — fetch existing
            return self.get_profile(user_id) or {}
        except Exception as e:
            logger.error("upsert_profile failed for user %s: %s", user_id, e)
            return self.get_profile(user_id) or {}

    def update_profile(self, user_id: str, data: dict[str, Any]) -> dict[str, Any] | None:
        try:
            result = (
                self._sb.table("users")
                .update(data)
                .eq("id", user_id)
                .execute()
            )
            if result and result.data:
                return result.data[0]
            return None
        except Exception as e:
            logger.error("update_profile failed for user %s: %s", user_id, e)
            return None

    def get_by_id_admin(self, user_id: str) -> dict[str, Any] | None:
        return self.get_profile(user_id)
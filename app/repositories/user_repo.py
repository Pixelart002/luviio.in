"""
User Repository — Repository Pattern
=====================================
Abstracts all database operations for the users table.
Provides a clean interface for the rest of the application.

FIXES APPLIED:
  1. count_users memory leak fixed (added .limit(1) to prevent downloading all IDs)
  2. Simplified and strict APIResponse checks (if not result.data:)
  3. Safe offset and page_size math for pagination
  4. Explicit error handling to prevent silent logical bugs
"""
from __future__ import annotations

import logging
from typing import Any

from supabase import Client

logger = logging.getLogger(__name__)


class UserRepository:
    """
    Data access layer for the users table.
    
    All methods return safe values — never raise on DB errors.
    Callers should check for None/empty dict returns.
    """

    def __init__(self, sb: Client) -> None:
        self._sb = sb

    # ══════════════════════════════════════════════════════════════════════════
    #  READ OPERATIONS
    # ══════════════════════════════════════════════════════════════════════════

    def get_profile(self, user_id: str) -> dict[str, Any] | None:
        if not user_id:
            logger.warning("get_profile called with empty user_id")
            return None

        try:
            result = (
                self._sb.table("users")
                .select("id, email, full_name, phone, role, is_active, created_at, updated_at")
                .eq("id", user_id)
                .limit(1)
                .execute()
            )

            # Pythonic check: result.data will be [] if no user is found
            if not result.data:
                logger.debug("User not found | id=%s", user_id[:8])
                return None

            return result.data[0]

        except Exception as exc:
            logger.error("get_profile failed | user=%s error=%s", user_id[:8], exc)
            return None

    def get_by_email(self, email: str) -> dict[str, Any] | None:
        if not email:
            return None

        try:
            result = (
                self._sb.table("users")
                .select("id, email, full_name, role, is_active, created_at")
                .eq("email", email.lower().strip())
                .limit(1)
                .execute()
            )

            if not result.data:
                return None

            return result.data[0]

        except Exception as exc:
            logger.error("get_by_email failed | email=%s: %s", email, exc)
            return None

    def get_by_id_admin(self, user_id: str) -> dict[str, Any] | None:
        return self.get_profile(user_id)

    def list_users(
        self,
        page: int = 1,
        page_size: int = 20,
        search: str | None = None,
        role_filter: str | None = None,
    ) -> dict[str, Any]:
        
        # Edge case protection
        page = max(1, page)
        page_size = max(1, page_size)

        try:
            q = (
                self._sb.table("users")
                .select("id, email, full_name, phone, role, is_active, created_at", count="exact")
                .order("created_at", desc=True)
            )

            if search:
                # Clean search string to prevent query breakage
                clean_search = search.replace(",", "").strip()
                if clean_search:
                    q = q.or_(f"email.ilike.%{clean_search}%,full_name.ilike.%{clean_search}%")
            
            if role_filter:
                q = q.eq("role", role_filter)

            offset = (page - 1) * page_size
            # Range is inclusive in PostgREST (0 to 19 = 20 items)
            result = q.range(offset, offset + page_size - 1).execute()

            total = getattr(result, "count", 0) or 0
            items = result.data if result.data else []

            return {
                "items": items,
                "total": total,
                "page": page,
                "page_size": page_size,
                "pages": -(-total // page_size) if total > 0 else 0, # Ceiling division
            }

        except Exception as exc:
            logger.error("list_users failed: %s", exc)
            return {"items": [], "total": 0, "page": page, "page_size": page_size, "pages": 0}

    # ══════════════════════════════════════════════════════════════════════════
    #  WRITE OPERATIONS
    # ══════════════════════════════════════════════════════════════════════════

    def upsert_profile(
        self,
        user_id: str,
        email: str,
        full_name: str = "",
        phone: str = "",
    ) -> dict[str, Any]:
        
        if not user_id or not email:
            logger.warning("upsert_profile called with missing user_id or email")
            return {}

        try:
            result = (
                self._sb.table("users")
                .upsert(
                    {
                        "id": user_id,
                        "email": email.lower().strip(),
                        "full_name": full_name.strip() if full_name else "",
                        "phone": phone.strip() if phone else None,
                        "role": "customer",
                        "is_active": True,
                    },
                    on_conflict="id"
                )
                .execute()
            )

            if result.data:
                logger.info("Profile upserted | user=%s", user_id[:8])
                return result.data[0]

            logger.debug("Upsert returned empty — fetching existing | user=%s", user_id[:8])
            return self.get_profile(user_id) or {}

        except Exception as exc:
            logger.error("upsert_profile failed | user=%s: %s", user_id[:8], exc)
            return self.get_profile(user_id) or {}

    def update_profile(self, user_id: str, data: dict[str, Any]) -> dict[str, Any] | None:
        if not user_id or not data:
            return None

        # Sanitize fields
        allowed_fields = {"full_name", "phone", "is_active", "role"}
        update_data = {k: v for k, v in data.items() if k in allowed_fields}
        
        if not update_data:
            logger.warning("update_profile: no valid fields to update | user=%s", user_id[:8])
            return None

        try:
            result = (
                self._sb.table("users")
                .update(update_data)
                .eq("id", user_id)
                .execute()
            )

            if result.data:
                logger.info("Profile updated | user=%s fields=%s", user_id[:8], list(update_data.keys()))
                return result.data[0]

            logger.warning("Profile update returned no data | user=%s", user_id[:8])
            return None

        except Exception as exc:
            logger.error("update_profile failed | user=%s: %s", user_id[:8], exc)
            return None

    def deactivate_user(self, user_id: str) -> bool:
        return self.update_profile(user_id, {"is_active": False}) is not None

    def reactivate_user(self, user_id: str) -> bool:
        return self.update_profile(user_id, {"is_active": True}) is not None

    # ══════════════════════════════════════════════════════════════════════════
    #  UTILITY
    # ══════════════════════════════════════════════════════════════════════════

    def exists(self, user_id: str) -> bool:
        return self.get_profile(user_id) is not None

    def is_admin(self, user_id: str) -> bool:
        profile = self.get_profile(user_id)
        if not profile:
            return False
        return profile.get("role") == "admin" and profile.get("is_active", False)

    def count_users(self) -> int:
        try:
            # FIX: Added .limit(1) so it doesn't download ALL user IDs, just calculates the exact count!
            result = (
                self._sb.table("users")
                .select("id", count="exact")
                .limit(1) 
                .execute()
            )
            return getattr(result, "count", 0) or 0
        except Exception as exc:
            logger.error("count_users failed: %s", exc)
            return 0

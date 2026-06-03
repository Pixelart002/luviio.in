"""
User Repository — Repository Pattern
=====================================
Abstracts all database operations for the users table.
Provides a clean interface for the rest of the application.

FIXES:
  1. maybe_single() → limit(1).execute() (avoids 406 errors)
  2. Safe NoneType checks on all Supabase responses
  3. Consistent error handling with fallbacks
  4. Structured logging with user context
  5. updated_at column included (now exists in DB)
  6. EXACT COUNT RAM LEAK FIXED in count_users()

LLD Concepts:
  Repository Pattern  → separates data access from business logic
  Single Responsibility → one class, one table (users)
  Fail-Safe           → returns None/{} instead of crashing
"""
from __future__ import annotations

import logging
from typing import Any

from supabase import Client

logger = logging.getLogger(__name__)

# Columns that exist in the users table
_USER_SELECT = "id, email, full_name, phone, role, is_active, created_at, updated_at"


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
        """
        Fetch a single user profile by ID.
        
        Returns:
            dict: User profile if found
            None: User not found or DB error
        
        FIX: Uses limit(1).execute() instead of maybe_single()
             maybe_single() sends Accept: application/vnd.pgrst.object+json
             Supabase can return 406 Not Acceptable → execute() returns None
             → AttributeError on .data
             
             limit(1).execute() always returns a result object:
               data = []      → user not found → return None
               data = [{...}] → user found     → return dict
        """
        if not user_id:
            logger.warning("get_profile called with empty user_id")
            return None

        try:
            result = (
                self._sb.table("users")
                .select(_USER_SELECT)
                .eq("id", user_id)
                .limit(1)
                .execute()
            )

            if not result or not hasattr(result, "data") or not result.data:
                logger.debug("User not found | id=%s", user_id[:8])
                return None

            return result.data[0]

        except Exception as exc:
            logger.error("get_profile failed | user=%s error=%s", user_id[:8], exc)
            return None

    def get_by_email(self, email: str) -> dict[str, Any] | None:
        """
        Fetch user by email address.
        
        Returns:
            dict: User profile if found
            None: User not found or DB error
        """
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

            if not result or not hasattr(result, "data") or not result.data:
                return None

            return result.data[0]

        except Exception as exc:
            logger.error("get_by_email failed | email=%s: %s", email, exc)
            return None

    def get_by_id_admin(self, user_id: str) -> dict[str, Any] | None:
        """
        Admin: Get user by ID (same as get_profile, separate for clarity).
        """
        return self.get_profile(user_id)

    def list_users(
        self,
        page: int = 1,
        page_size: int = 20,
        search: str | None = None,
        role_filter: str | None = None,
    ) -> dict[str, Any]:
        """
        List users with pagination and optional filters.
        
        Returns:
            {
                "items": [...],
                "total": int,
                "page": int,
                "page_size": int,
                "pages": int
            }
        """
        try:
            # Here .range() limits the data download, so count="exact" is safe
            q = (
                self._sb.table("users")
                .select(_USER_SELECT, count="exact")
                .order("created_at", desc=True)
            )

            if search:
                q = q.or_(f"email.ilike.%{search}%,full_name.ilike.%{search}%")
            if role_filter:
                q = q.eq("role", role_filter)

            offset = (page - 1) * page_size
            result = q.range(offset, offset + page_size - 1).execute()

            total = result.count if result and hasattr(result, "count") and result.count else 0
            items = result.data if result and hasattr(result, "data") and result.data else []

            return {
                "items": items,
                "total": total,
                "page": page,
                "page_size": page_size,
                "pages": -(-total // page_size) if page_size > 0 else 0,
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
        """
        Create or update user profile.
        
        Used for:
          • New user registration (creates profile)
          • First login after auth (syncs profile)
          • Profile updates from auth webhook
        
        Returns:
            dict: The created/updated profile
            {}: Empty dict on failure (caller handles)
        """
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
                    on_conflict="id",
                )
                .execute()
            )

            if result and hasattr(result, "data") and result.data:
                logger.info("Profile upserted | user=%s", user_id[:8])
                return result.data[0]

            # Upsert returned empty — fetch existing
            logger.debug("Upsert returned empty — fetching existing | user=%s", user_id[:8])
            return self.get_profile(user_id) or {}

        except Exception as exc:
            logger.error("upsert_profile failed | user=%s: %s", user_id[:8], exc)
            return self.get_profile(user_id) or {}

    def update_profile(self, user_id: str, data: dict[str, Any]) -> dict[str, Any] | None:
        """
        Update specific fields on a user profile.
        
        Args:
            user_id: User UUID
            data: Dict of fields to update (e.g., {"full_name": "New Name"})
        
        Returns:
            dict: Updated profile if successful
            None: User not found or update failed
        """
        if not user_id or not data:
            return None

        # Sanitize: only allow safe fields
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

            if result and hasattr(result, "data") and result.data:
                logger.info(
                    "Profile updated | user=%s fields=%s",
                    user_id[:8], list(update_data.keys())
                )
                return result.data[0]

            logger.warning("Profile update returned no data | user=%s", user_id[:8])
            return None

        except Exception as exc:
            logger.error("update_profile failed | user=%s: %s", user_id[:8], exc)
            return None

    def deactivate_user(self, user_id: str) -> bool:
        """Soft-delete: set is_active=False."""
        result = self.update_profile(user_id, {"is_active": False})
        return result is not None

    def reactivate_user(self, user_id: str) -> bool:
        """Reactivate a deactivated user."""
        result = self.update_profile(user_id, {"is_active": True})
        return result is not None

    # ══════════════════════════════════════════════════════════════════════════
    #  UTILITY
    # ══════════════════════════════════════════════════════════════════════════

    def exists(self, user_id: str) -> bool:
        """Check if a user exists by ID."""
        profile = self.get_profile(user_id)
        return profile is not None

    def is_admin(self, user_id: str) -> bool:
        """Check if a user has admin role."""
        profile = self.get_profile(user_id)
        if not profile:
            return False
        return profile.get("role") == "admin" and profile.get("is_active", False)

    def count_users(self) -> int:
        """Get total count of users."""
        try:
            # [FIX] RAM Memory Leak Fix: Added limit(1) to exact count query
            result = (
                self._sb.table("users")
                .select("id", count="exact")
                .limit(1)
                .execute()
            )
            return result.count if result and hasattr(result, "count") and result.count else 0
        except Exception as exc:
            logger.error("count_users failed: %s", exc)
            return 0

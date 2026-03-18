"""
User Repository — Repository Pattern
=======================================
Pattern: Repository (abstraction layer over data access)
Why: Business logic (dependencies.py, routers) should not know about Supabase
     internals. Swap Supabase for Postgres direct / Redis cache without
     touching a single router.

LLD concepts applied:
  Repository Pattern      → data access behind a clean interface
  Single Responsibility   → this module's only job: read/write user rows
  Abstraction             → callers use get_profile(), not .table().select()...
  Designing for Testability → mock this class in unit tests, no real DB needed
"""
from __future__ import annotations

import logging
from typing import Any

from supabase import Client

logger = logging.getLogger(__name__)


class UserRepository:
    """All user-table operations live here. Routers never touch .table("users") directly."""

    def __init__(self, sb: Client) -> None:
        self._sb = sb

    def get_profile(self, user_id: str) -> dict[str, Any] | None:
        """
        Fetch user profile row.
        Uses maybe_single() — returns None (not raises) when 0 rows found.
        This is THE fix for the PGRST116 / 500 bug.
        """
        result = (
            self._sb.table("users")
            .select("id, email, full_name, phone, role, is_active, created_at")
            .eq("id", user_id)
            .maybe_single()   # ← KEY FIX: None on 0 rows, not exception
            .execute()
        )
        return result.data  # None if not found, dict if found

    def upsert_profile(self, user_id: str, email: str, full_name: str = "") -> dict[str, Any]:
        """
        Create profile if missing, return existing if present.
        Idempotent — safe to call multiple times (ON CONFLICT DO NOTHING).
        Used as fallback when auth trigger fails or for legacy users.
        """
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
                ignore_duplicates=True,   # ON CONFLICT DO NOTHING
            )
            .execute()
        )
        # If upsert did nothing (duplicate), fetch existing row
        if not result.data:
            return self.get_profile(user_id) or {}
        return result.data[0]

    def update_profile(self, user_id: str, data: dict[str, Any]) -> dict[str, Any] | None:
        result = (
            self._sb.table("users")
            .update(data)
            .eq("id", user_id)
            .execute()
        )
        return result.data[0] if result.data else None

    def get_by_id_admin(self, user_id: str) -> dict[str, Any] | None:
        """Admin view — includes all fields."""
        result = (
            self._sb.table("users")
            .select("id, email, full_name, phone, role, is_active, created_at")
            .eq("id", user_id)
            .maybe_single()
            .execute()
        )
        return result.data
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
    def upsert_profile(self, user_id: str, email: str, full_name: str) -> None:
        """Create or update a user profile after registration."""
        try:
            self.admin_sb.table("users").upsert(
                {
                    "id": user_id,
                    "email": email,
                    "full_name": full_name,
                },
                on_conflict="id"
            ).execute()
        except Exception as e:
            logger.error("Failed to upsert user profile | id=%s: %s", user_id[:8], e)
            raise

    def get_user_by_id(self, user_id: str) -> dict[str, Any] | None:
        """Fetch user profile."""
        try:
            res = self.admin_sb.table("users").select("*").eq("id", user_id).limit(1).execute()
            return res.data[0] if res and hasattr(res, "data") and res.data else None
        except Exception as e:
            logger.error("Failed to fetch user | id=%s: %s", user_id[:8], e)
            return None
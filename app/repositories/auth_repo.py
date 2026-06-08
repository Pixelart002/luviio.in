"""
Auth Repository — Async Enterprise Grade
========================================
Path: app/repositories/auth_repo.py
"""
import logging
from typing import Any, Dict, Optional
from app.core.supabase import get_async_supabase, get_async_admin_supabase

logger = logging.getLogger(__name__)

class AsyncAuthRepository:
    def __init__(self):
        self.sb = get_async_supabase()
        self.admin_sb = get_async_admin_supabase()

    async def sign_up(self, email: str, password: str, full_name: str) -> Optional[str]:
        res = await self.sb.auth.sign_up({
            "email": email, 
            "password": password,
            "options": {"data": {"full_name": full_name}}
        })
        if res and hasattr(res, "user") and res.user:
            return res.user.id
        return None

    async def sign_in(self, email: str, password: str) -> Optional[Dict[str, Any]]:
        res = await self.sb.auth.sign_in_with_password({"email": email, "password": password})
        if res and getattr(res, "user", None) and getattr(res, "session", None):
            return {
                "user_id": res.user.id,
                "email": res.user.email,
                "access_token": res.session.access_token,
                "refresh_token": res.session.refresh_token,
                "expires_in": res.session.expires_in
            }
        return None

    async def refresh_session(self, refresh_token: str) -> Optional[Dict[str, Any]]:
        res = await self.sb.auth.refresh_session(refresh_token)
        if res and getattr(res, "session", None):
            return {
                "user_id": res.user.id if getattr(res, "user", None) else None,
                "email": res.user.email if getattr(res, "user", None) else None,
                "access_token": res.session.access_token,
                "refresh_token": res.session.refresh_token,
                "expires_in": res.session.expires_in
            }
        return None

    async def sign_out(self) -> None:
        await self.sb.auth.sign_out()

    async def reset_password_email(self, email: str) -> None:
        await self.sb.auth.reset_password_email(email)

    async def admin_update_password(self, user_id: str, new_password: str) -> None:
        await self.admin_sb.auth.admin.update_user_by_id(user_id, {"password": new_password})
"""
Auth Repository — Async Enterprise Grade
========================================
Path: app/repositories/auth_repo.py
"""
import logging
from typing import Any, Dict, Optional
import httpx
from app.core.supabase import get_async_supabase, get_async_admin_supabase
from app.core.config import settings

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
        # Call Supabase token endpoint directly to avoid the shared singleton
        # AsyncClient's in-memory session overwriting the provided refresh token.
        url = f"{settings.SB_URL}/auth/v1/token?grant_type=refresh_token"
        headers = {
            "apikey": settings.SB_KEY,
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient() as client:
            response = await client.post(url, headers=headers, json={"refresh_token": refresh_token})
        if response.status_code != 200:
            data = response.json()
            msg = data.get("error_description") or data.get("msg") or response.text
            raise Exception(f"Invalid Refresh Token: {msg}")
        data = response.json()
        user = data.get("user") or {}
        return {
            "user_id": user.get("id"),
            "email": user.get("email"),
            "access_token": data["access_token"],
            "refresh_token": data["refresh_token"],
            "expires_in": data.get("expires_in"),
        }

    async def sign_out_with_token(self, refresh_token: str) -> None:
        """Sign out by calling Supabase /auth/v1/logout directly via httpx,
        avoiding the shared singleton client and its in-memory session state."""
        url = f"{settings.SB_URL}/auth/v1/logout"
        headers = {
            "apikey": settings.SB_KEY,
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient() as client:
            await client.post(url, headers=headers, json={"refresh_token": refresh_token})

    async def reset_password_email(self, email: str) -> None:
        await self.sb.auth.reset_password_email(email)

    async def admin_update_password(self, user_id: str, new_password: str) -> None:
        await self.admin_sb.auth.admin.update_user_by_id(user_id, {"password": new_password})
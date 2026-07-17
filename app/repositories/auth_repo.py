"""
Auth Repository — Hardened Async Stateless Grade
================================================
Path: app/repositories/auth_repo.py
"""
import logging
from typing import Any, Dict, Optional
import httpx
from gotrue.errors import AuthApiError
from app.core.supabase import get_async_supabase, get_async_admin_supabase
from app.core.config import settings

logger = logging.getLogger(__name__)

class AsyncAuthRepository:
    """Stateless execution preventing coroutine state crashes and thread locks."""
    
    async def sign_up(self, email: str, password: str, full_name: str) -> Optional[str]:
        sb = await get_async_supabase()
        res = await sb.auth.sign_up({
            "email": email, 
            "password": password,
            "options": {"data": {"full_name": full_name}}
        })
        return res.user.id if res and getattr(res, "user", None) else None

    async def sign_in(self, email: str, password: str) -> Optional[Dict[str, Any]]:
        sb = await get_async_supabase()
        res = await sb.auth.sign_in_with_password({"email": email, "password": password})
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
        """Direct HTTP call to avoid singleton session mutations."""
        url = f"{settings.SB_URL}/auth/v1/token?grant_type=refresh_token"
        headers = {"apikey": settings.SB_KEY, "Content-Type": "application/json"}
        
        async with httpx.AsyncClient() as client:
            response = await client.post(url, headers=headers, json={"refresh_token": refresh_token})
            
        if response.status_code != 200:
            logger.warning("Supabase Token Refresh Failed: %s", response.text)
            return None
            
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
        url = f"{settings.SB_URL}/auth/v1/logout"
        headers = {"apikey": settings.SB_KEY, "Content-Type": "application/json"}
        async with httpx.AsyncClient() as client:
            await client.post(url, headers=headers, json={"refresh_token": refresh_token})

    async def reset_password_email(self, email: str) -> None:
        sb = await get_async_supabase()
        await sb.auth.reset_password_email(email)

    async def admin_update_password(self, user_id: str, new_password: str) -> None:
        admin_sb = await get_async_admin_supabase()
        await admin_sb.auth.admin.update_user_by_id(user_id, {"password": new_password})
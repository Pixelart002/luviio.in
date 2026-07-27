"""
Auth Repository — Async Hardened Production Grade
=================================================
Path: app/repositories/auth_repo.py
"""
import logging
from typing import Any, Dict, Optional
import httpx
from app.core.supabase import get_async_supabase
from app.core.config import settings

logger = logging.getLogger(__name__)

class AsyncAuthRepository:
    def __init__(self):
        pass

    async def sign_up(self, email: str, password: str, full_name: str) -> Optional[str]:
        sb = await get_async_supabase()
        res = await sb.auth.sign_up({
            "email": email, 
            "password": password,
            "options": {"data": {"full_name": full_name}}
        })
        if res and hasattr(res, "user") and res.user:
            return res.user.id
        return None

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
        url = f"{settings.SB_URL}/auth/v1/token?grant_type=refresh_token"
        headers = {
            "apikey": settings.SB_KEY,
            "Content-Type": "application/json",
        }
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(url, headers=headers, json={"refresh_token": refresh_token})
                
            if response.status_code != 200:
                data = response.json()
                msg = data.get("error_description") or data.get("msg") or response.text
                logger.warning("Session refresh failed: %s", msg)
                raise ValueError(f"Invalid Refresh Token: {msg}")
                
            data = response.json()
            user = data.get("user") or {}
            return {
                "user_id": user.get("id"),
                "email": user.get("email"),
                "access_token": data["access_token"],
                "refresh_token": data["refresh_token"],
                "expires_in": data.get("expires_in"),
            }
        except httpx.RequestError as exc:
            logger.error("Network error during token refresh: %s", exc)
            raise RuntimeError("Authentication server currently unreachable.") from exc

    async def sign_out_with_token(self, refresh_token: str) -> None:
        url = f"{settings.SB_URL}/auth/v1/logout"
        headers = {
            "apikey": settings.SB_KEY,
            "Content-Type": "application/json",
        }
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                await client.post(url, headers=headers, json={"refresh_token": refresh_token})
        except httpx.RequestError as exc:
            logger.warning("Network timeout while invalidating token: %s", exc)

    async def reset_password_email(self, email: str) -> None:
        sb = await get_async_supabase()
        await sb.auth.reset_password_email(email)

    async def update_password_with_token(self, access_token: str, new_password: str) -> None:
        url = f"{settings.SB_URL}/auth/v1/user"
        headers = {
            "apikey": settings.SB_KEY,
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.put(url, headers=headers, json={"password": new_password})
                
            if response.status_code != 200:
                data = response.json()
                msg = data.get("error_description") or data.get("msg") or "Token is invalid or expired."
                logger.warning("Password reset update rejected: %s", msg)
                raise ValueError(msg)
        except httpx.RequestError as exc:
            logger.error("Network error during password update: %s", exc)
            raise RuntimeError("Authentication server currently unreachable.") from exc
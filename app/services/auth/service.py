"""
Auth Service — Enterprise Business Logic & Brute-Force Shield
=============================================================
Path: app/services/auth_service.py
"""
import logging
import time
from typing import Any, Dict
from fastapi import HTTPException, status
from gotrue.errors import AuthApiError
from starlette.concurrency import run_in_threadpool

from app.repositories.user_repo import AsyncUserRepository
from app.repositories.auth_repo import AsyncAuthRepository
from app.integrations.email.registry import get_email_provider
from app.constants.auth_messages import AuthSecurityMessages

logger = logging.getLogger(__name__)

# In-Memory Brute Force Protection State
_MAX_LOGIN_ATTEMPTS = 5
_LOGIN_WINDOW_SECONDS = 300
_LOGIN_COOLDOWN_SECONDS = 900
_login_attempts: Dict[str, list[float]] = {}
_blocked_ips: Dict[str, float] = {}

class AuthService:
    def __init__(self):
        self.auth_repo = AsyncAuthRepository()
        self.user_repo = AsyncUserRepository()

    def _check_brute_force(self, ip: str, email: str = "") -> None:
        """Evaluates attempt window and blocks IPs or emails exceeding threshold."""
        now = time.time()
        global _login_attempts, _blocked_ips
        
        # Clean expired attempts
        _login_attempts = {k: [t for t in v if now - t < _LOGIN_WINDOW_SECONDS] for k, v in _login_attempts.items()}
        _login_attempts = {k: v for k, v in _login_attempts.items() if v}
        _blocked_ips = {k: v for k, v in _blocked_ips.items() if v > now}
        
        if ip in _blocked_ips or (email and f"email:{email}" in _blocked_ips):
            logger.warning("Brute force block triggered | IP: %s | Email: %s", ip, email)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=AuthSecurityMessages.TOO_MANY_ATTEMPTS
            )
        
        ip_attempts = len(_login_attempts.get(ip, []))
        email_attempts = len(_login_attempts.get(f"email:{email}", [])) if email else 0
        
        if ip_attempts >= _MAX_LOGIN_ATTEMPTS or email_attempts >= _MAX_LOGIN_ATTEMPTS:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=AuthSecurityMessages.TOO_MANY_ATTEMPTS
            )

    def _record_attempt(self, ip: str, email: str = "") -> None:
        now = time.time()
        _login_attempts.setdefault(ip, []).append(now)
        if email: _login_attempts.setdefault(f"email:{email}", []).append(now)
        
        if len(_login_attempts[ip]) >= _MAX_LOGIN_ATTEMPTS:
            _blocked_ips[ip] = now + _LOGIN_COOLDOWN_SECONDS
        if email and len(_login_attempts.get(f"email:{email}", [])) >= _MAX_LOGIN_ATTEMPTS:
            _blocked_ips[f"email:{email}"] = now + _LOGIN_COOLDOWN_SECONDS

    def _reset_attempts(self, ip: str, email: str = "") -> None:
        _login_attempts.pop(ip, None); _blocked_ips.pop(ip, None)
        if email: _login_attempts.pop(f"email:{email}", None); _blocked_ips.pop(f"email:{email}", None)

    async def register_user(self, email: str, password: str, full_name: str, client_ip: str) -> bool:
        self._check_brute_force(client_ip)
        try:
            auth_user_id = await self.auth_repo.sign_up(email, password, full_name)
        except AuthApiError:
            self._record_attempt(client_ip)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=AuthSecurityMessages.EMAIL_IN_USE
            )
            
        if auth_user_id:
            await self.user_repo.upsert_profile(user_id=auth_user_id, email=email, full_name=full_name)
            try:
                email_service = get_email_provider("resend")
                await run_in_threadpool(email_service.send_welcome_email, email, full_name)
            except Exception as e:
                logger.warning("Welcome email dispatch failed: %s", e)
        return True

    async def login_user(self, email: str, password: str, client_ip: str) -> Dict[str, Any]:
        self._check_brute_force(client_ip, email)
        try:
            session_data = await self.auth_repo.sign_in(email, password)
            if not session_data:
                self._record_attempt(client_ip, email)
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail=AuthSecurityMessages.INVALID_CREDENTIALS
                )
            self._reset_attempts(client_ip, email)
            return session_data
        except AuthApiError:
            self._record_attempt(client_ip, email)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=AuthSecurityMessages.INVALID_CREDENTIALS
            )

    async def refresh_user_session(self, refresh_token: str) -> Dict[str, Any]:
        session_data = await self.auth_repo.refresh_session(refresh_token)
        if not session_data:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=AuthSecurityMessages.INVALID_REFRESH
            )
        return session_data

    async def logout_user(self, refresh_token: str) -> None:
        if refresh_token:
            try:
                await self.auth_repo.sign_out_with_token(refresh_token)
            except Exception as e:
                logger.error("Error revoking token during logout: %s", e)

    async def process_forgot_password(self, email: str, client_ip: str) -> None:
        self._check_brute_force(client_ip)
        try:
            await self.auth_repo.reset_password_email(email)
        except Exception as e:
            logger.error("Forgot password dispatch error: %s", e)

    async def process_reset_password(self, user_id: str, new_password: str) -> None:
        try:
            await self.auth_repo.admin_update_password(user_id, new_password)
        except AuthApiError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Password reset failed: {e.message}"
            )
"""
Auth Service — Enterprise Orchestration
=======================================
Path: app/services/auth/service.py
"""
import logging
from typing import Any, Dict
from fastapi import HTTPException, status
from supabase import AuthApiError
from starlette.concurrency import run_in_threadpool

from app.repositories.user_repo import AsyncUserRepository
from app.repositories.auth_repo import AsyncAuthRepository
from app.permissions.policies.auth_policies import AuthPolicy
from app.integrations.email.registry import get_email_provider
from app.constants.auth_messages import AuthSecurityMessages

logger = logging.getLogger(__name__)

class AuthService:
    def __init__(self):
        self.auth_repo = AsyncAuthRepository()
        self.user_repo = AsyncUserRepository()

    async def register_user(self, email: str, password: str, full_name: str, client_ip: str) -> bool:
        AuthPolicy.assert_safe_attempt(client_ip, email)
        try:
            auth_user_id = await self.auth_repo.sign_up(email, password, full_name)
        except AuthApiError as exc:
            AuthPolicy.record_failed_attempt(client_ip, email)
            logger.warning("Supabase registration rejected for %s: %s", email, exc)
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=AuthSecurityMessages.REGISTRATION_FAILED) from exc
            
        if not auth_user_id:
            AuthPolicy.record_failed_attempt(client_ip, email)
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=AuthSecurityMessages.REGISTRATION_FAILED)

        # Sync profile to custom DB ledger
        try:
            await self.user_repo.upsert_profile(user_id=auth_user_id, email=email, full_name=full_name)
        except Exception as exc:
            logger.error("Critical: Profile ledger sync failed for auth ID %s: %s", auth_user_id, exc, exc_info=True)
            # We do not rollback Supabase user here as confirmation link is already dispatched

        # Send welcome email asynchronously without blocking registration response
        try:
            email_service = get_email_provider("resend")
            await run_in_threadpool(email_service.send_welcome_email, email, full_name)
        except Exception as exc:
            logger.warning("Welcome email dispatch failed for %s: %s", email, exc)

        return True

    async def login_user(self, email: str, password: str, client_ip: str) -> Dict[str, Any]:
        AuthPolicy.assert_safe_attempt(client_ip, email)
        try:
            session_data = await self.auth_repo.sign_in(email, password)
            if not session_data:
                AuthPolicy.record_failed_attempt(client_ip, email)
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=AuthSecurityMessages.INVALID_CREDENTIALS)
                
            AuthPolicy.reset_attempts(client_ip, email)
            return session_data
        except AuthApiError as exc:
            AuthPolicy.record_failed_attempt(client_ip, email)
            logger.info("Login failed for %s from IP %s", email, client_ip)
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=AuthSecurityMessages.INVALID_CREDENTIALS) from exc

    async def refresh_user_session(self, refresh_token: str) -> Dict[str, Any]:
        if not refresh_token:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=AuthSecurityMessages.INVALID_REFRESH_TOKEN)
            
        try:
            session_data = await self.auth_repo.refresh_session(refresh_token)
            if not session_data:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=AuthSecurityMessages.INVALID_REFRESH_TOKEN)
            return session_data
        except (ValueError, RuntimeError) as exc:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=AuthSecurityMessages.INVALID_REFRESH_TOKEN) from exc

    async def logout_user(self, refresh_token: str | None) -> None:
        if refresh_token:
            try:
                await self.auth_repo.sign_out_with_token(refresh_token)
            except Exception as exc:
                logger.error("Error during session logout: %s", exc)

    async def process_forgot_password(self, email: str, client_ip: str) -> None:
        AuthPolicy.assert_safe_attempt(client_ip)
        try:
            await self.auth_repo.reset_password_email(email)
        except Exception as exc:
            logger.warning("Password reset email trigger failed for %s: %s", email, exc)

    async def process_reset_password(self, access_token: str, new_password: str) -> None:
        if not access_token:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=AuthSecurityMessages.MISSING_AUTH_HEADER)
            
        try:
            await self.auth_repo.update_password_with_token(access_token, new_password)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, 
                detail=AuthSecurityMessages.RESET_FAILED.format(reason=str(exc))
            ) from exc
        except RuntimeError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=AuthSecurityMessages.RESET_FAILED.format(reason="Service unreachable")
            ) from exc
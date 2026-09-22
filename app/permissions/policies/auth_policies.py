"""
Auth Policies & Brute Force Guard
=================================
Shared database-backed throttling so limits remain consistent across workers
and restarts. The DB functions are service-role-only infrastructure.
"""
import hashlib
import logging

from fastapi import HTTPException, status

from app.constants.auth_messages import AuthRules, AuthSecurityMessages
from app.core.supabase import get_async_admin_supabase

logger = logging.getLogger(__name__)


def _key(value: str, kind: str) -> str:
    normalized = (value or "").strip().lower()
    if not normalized:
        return ""
    return hashlib.sha256(f"auth:{kind}:{normalized}".encode("utf-8")).hexdigest()


class AuthPolicy:
    @staticmethod
    async def assert_safe_attempt(ip: str, email: str = "") -> None:
        ip_key = _key(ip, "ip")
        email_key = _key(email, "email")
        try:
            sb = await get_async_admin_supabase()
            result = await sb.rpc(
                "auth_throttle_check",
                {
                    "p_ip_key": ip_key,
                    "p_email_key": email_key,
                    "p_window_seconds": AuthRules.LOGIN_WINDOW_SECONDS,
                    "p_max_attempts": AuthRules.MAX_LOGIN_ATTEMPTS,
                },
            ).execute()
            allowed = bool(getattr(result, "data", False))
        except Exception as exc:
            logger.error("Auth throttle check failed; failing closed: %s", exc, exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Authentication protection is temporarily unavailable. Please retry shortly.",
            ) from exc

        if not allowed:
            logger.warning("Auth throttle blocked attempt | ip_key=%s", ip_key[:12])
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=AuthSecurityMessages.TOO_MANY_REQUESTS,
            )

    @staticmethod
    async def record_failed_attempt(ip: str, email: str = "") -> None:
        ip_key = _key(ip, "ip")
        email_key = _key(email, "email")
        try:
            sb = await get_async_admin_supabase()
            await sb.rpc(
                "auth_throttle_record_failure",
                {
                    "p_ip_key": ip_key,
                    "p_email_key": email_key,
                    "p_window_seconds": AuthRules.LOGIN_WINDOW_SECONDS,
                    "p_max_attempts": AuthRules.MAX_LOGIN_ATTEMPTS,
                    "p_cooldown_seconds": AuthRules.LOGIN_COOLDOWN_SECONDS,
                },
            ).execute()
        except Exception as exc:
            logger.error("Auth throttle failure recording failed: %s", exc, exc_info=True)

    @staticmethod
    async def reset_attempts(ip: str, email: str = "") -> None:
        ip_key = _key(ip, "ip")
        email_key = _key(email, "email")
        try:
            sb = await get_async_admin_supabase()
            await sb.rpc(
                "auth_throttle_reset",
                {"p_ip_key": ip_key, "p_email_key": email_key},
            ).execute()
        except Exception as exc:
            logger.error("Auth throttle reset failed: %s", exc, exc_info=True)

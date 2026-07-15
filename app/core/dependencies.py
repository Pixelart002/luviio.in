"""
Dependencies — Async Hardened Production Grade (Luviio SSOT)
============================================================
Path: app/core/dependencies.py
"""
import base64
import json
import logging
from typing import Any, Dict

from cachetools import TTLCache
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from gotrue.errors import AuthApiError

# Utility imports
from app.utils.timestamp import ts_to_iso
from app.repositories.user_repo import AsyncUserRepository
from app.core.supabase import get_async_admin_supabase, get_async_supabase
from app.core.exceptions import UnauthorizedAction, UnauthenticatedUser
from app.permissions.base import ROLE_PERMISSIONS
from app.enums.roles import UserRole

logger = logging.getLogger(__name__)
bearer_scheme = HTTPBearer(auto_error=False)

_token_cache: TTLCache = TTLCache(maxsize=512, ttl=60)
_profile_cache: TTLCache = TTLCache(maxsize=512, ttl=60)


# ══════════════════════════════════════════════════════════════════════════════
#  JWT PAYLOAD DECODER
# ══════════════════════════════════════════════════════════════════════════════

def _decode_jwt(token: str) -> dict[str, Any]:
    try:
        parts = token.split('.')
        if len(parts) != 3:
            return {}
        payload_b64 = parts[1]
        payload_b64 += '=' * (-len(payload_b64) % 4)
        payload_bytes = base64.urlsafe_b64decode(payload_b64)
        return json.loads(payload_bytes)
    except Exception as e:
        logger.debug("JWT payload extraction failed: %s", e)
        return {}


def _build_context(auth_user: Any, profile: dict[str, Any], claims: dict[str, Any]) -> dict[str, Any]:
    return {
        "auth_user": auth_user,
        "profile": profile,
        "exp": ts_to_iso(claims.get("exp")),
        "sub": claims.get("sub"),
        "iat": ts_to_iso(claims.get("iat")),
        "jwt_role": claims.get("role"),
    }


# ══════════════════════════════════════════════════════════════════════════════
#  CORE VALIDATION
# ══════════════════════════════════════════════════════════════════════════════

async def _validate_token(token: str) -> Any:
    if not token:
        raise UnauthenticatedUser()
    if token in _token_cache:
        return _token_cache[token]

    sb = await get_async_admin_supabase()
    try:
        result = await sb.auth.get_user(token)
        user = getattr(result, "user", result)
        if not user or not hasattr(user, "id"):
            raise UnauthenticatedUser("Invalid token structure")

        _token_cache[token] = user
        return user
    except AuthApiError:
        raise UnauthenticatedUser("Invalid or expired token")
    except Exception as e:
        logger.error("Token validation error: %s", e)
        raise UnauthenticatedUser("Authentication failed")


async def _get_or_create_profile(auth_user: Any) -> dict[str, Any]:
    repo = AsyncUserRepository()
    auth_user_id = str(getattr(auth_user, "id", ""))
    
    if not auth_user_id:
        return {}
    if auth_user_id in _profile_cache:
        return _profile_cache[auth_user_id]

    try:
        profile = await repo.get_profile(auth_user_id)
    except Exception:
        profile = None

    if not profile:
        user_meta = getattr(auth_user, "user_metadata", None) or {}
        try:
            profile = await repo.upsert_profile(
                user_id=auth_user_id,
                email=getattr(auth_user, "email", "") or "",
                full_name=user_meta.get("full_name", "") or "",
                phone=getattr(auth_user, "phone", "") or "",
            )
        except Exception as e:
            logger.error("Profile auto-create failed for %.8s: %s", auth_user_id, e)
            return {}

    result = profile or {}
    if result:
        _profile_cache[auth_user_id] = result
    return result


# ══════════════════════════════════════════════════════════════════════════════
#  FASTAPI DEPENDENCIES
# ══════════════════════════════════════════════════════════════════════════════

async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> dict[str, Any]:
    token = None
    if not credentials:
        refresh_token = request.cookies.get("refresh_token")
        if refresh_token:
            try:
                sb = await get_async_supabase()
                result = await sb.auth.refresh_session(refresh_token)
                if result and hasattr(result, "session") and result.session:
                    token = result.session.access_token
                    auth_user = await _validate_token(token)
                    profile = await _get_or_create_profile(auth_user)
                    if profile and profile.get("is_active", True):
                        request.state.user_id = profile.get("id") or getattr(auth_user, "id", "N/A")
                        claims = _decode_jwt(token)
                        return _build_context(auth_user, profile, claims)
            except Exception:
                pass
        raise UnauthenticatedUser()
    else:
        token = credentials.credentials

    auth_user = await _validate_token(token)
    profile = await _get_or_create_profile(auth_user)

    if not profile.get("is_active", True):
        raise UnauthorizedAction("Account deactivated")

    request.state.user_id = profile.get("id") or getattr(auth_user, "id", "N/A")
    claims = _decode_jwt(token)
    return _build_context(auth_user, profile, claims)


async def get_user_id_strict(current_user: dict[str, Any] = Depends(get_current_user)) -> str:
    user_id = current_user.get("profile", {}).get("id") or current_user.get("sub") or getattr(current_user.get("auth_user"), "id", "")
    if not user_id:
        raise UnauthenticatedUser("User identity missing for scope resolution.")
    return str(user_id)


# ══════════════════════════════════════════════════════════════════════════════
#  ENTERPRISE PBAC GUARDS
# ══════════════════════════════════════════════════════════════════════════════

def require_permission(required_perm: str):
    async def permission_checker(current_user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
        role = current_user.get("profile", {}).get("role", UserRole.CUSTOMER)
        user_perms = ROLE_PERMISSIONS.get(role, [])
        if "*" in user_perms:
            return current_user
        if required_perm not in user_perms:
            raise UnauthorizedAction(f"Missing permission: {required_perm}")
        return current_user
    return permission_checker


async def require_admin(current: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    sb = await get_async_admin_supabase()
    user_id = current.get("profile", {}).get("id", "")
    if not user_id:
        raise UnauthorizedAction("Access denied")
    
    result = await sb.table("users").select("role, is_active").eq("id", user_id).limit(1).maybe_single().execute()
    if not result or not result.data or result.data.get("role") != "admin" or not result.data.get("is_active"):
        raise UnauthorizedAction("Admin access required")
    
    current["profile"].update({"role": result.data["role"], "is_active": result.data["is_active"]})
    return current
import asyncio
import logging
from typing import Any, Dict

from cachetools import TTLCache
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from gotrue.errors import AuthApiError

from app.repositories.user_repo import AsyncUserRepository
from app.core.supabase import get_async_admin_supabase, get_async_supabase
from app.core.exceptions import UnauthorizedAction, UnauthenticatedUser
from app.permissions.base import ROLE_PERMISSIONS
from app.enums.roles import UserRole
from app.permissions.admin import AdminPermissions

logger = logging.getLogger(__name__)
bearer_scheme = HTTPBearer(auto_error=False)

_token_cache: TTLCache = TTLCache(maxsize=512, ttl=60)
_profile_cache: TTLCache = TTLCache(maxsize=512, ttl=60)


async def _validate_token(token: str) -> Any:
    if not token:
        raise UnauthenticatedUser()
    if token in _token_cache:
        return _token_cache[token]

    sb = get_async_admin_supabase()
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


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> dict[str, Any]:
    
    if not credentials:
        refresh_token = request.cookies.get("refresh_token")
        if refresh_token:
            try:
                sb = get_async_supabase()
                result = await sb.auth.refresh_session(refresh_token)
                if result and hasattr(result, "session") and result.session:
                    token = result.session.access_token
                    auth_user = await _validate_token(token)
                    profile = await _get_or_create_profile(auth_user)
                    if profile and profile.get("is_active", True):
                        request.state.user_name = profile.get("full_name") or profile.get("email") or "Unknown"
                        request.state.user_id = profile.get("id") or getattr(auth_user, "id", "N/A")
                        return {"auth_user": auth_user, "profile": profile}
            except Exception:
                pass
        raise UnauthenticatedUser()

    auth_user = await _validate_token(credentials.credentials)
    profile = await _get_or_create_profile(auth_user)

    if not profile.get("is_active", True):
        raise UnauthorizedAction("Account deactivated")

    request.state.user_name = profile.get("full_name") or profile.get("email") or "Unknown"
    request.state.user_id = profile.get("id") or getattr(auth_user, "id", "N/A")

    return {"auth_user": auth_user, "profile": profile}


async def get_optional_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> dict[str, Any] | None:
    if not credentials:
        return None
    try:
        auth_user = await _validate_token(credentials.credentials)
        profile = await _get_or_create_profile(auth_user)
        if profile and profile.get("is_active", True):
            request.state.user_name = profile.get("full_name") or profile.get("email") or "Unknown"
            request.state.user_id = profile.get("id") or getattr(auth_user, "id", "N/A")
            return {"auth_user": auth_user, "profile": profile}
    except Exception:
        pass
    return None


async def get_user_id_strict(current_user: dict[str, Any] = Depends(get_current_user)) -> str:
    """
    ABAC (Attribute-Based Access Control) guard.
    Extracts the securely verified `user_id` from the JWT token.
    """
    user_id = current_user.get("profile", {}).get("id") or getattr(current_user.get("auth_user"), "id", "")
    if not user_id:
        raise UnauthenticatedUser("User identity missing for scope resolution.")
    return str(user_id)


def require_permission(required_perm: str):
    """
    Enterprise PBAC Guard. Checks if the user's role has the requested permission in the registry.
    Usage: @router.post("/", dependencies=[Depends(require_permission(ProductPermissions.CREATE))])
    """
    async def permission_checker(current_user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
        role = current_user.get("profile", {}).get("role", UserRole.CUSTOMER)
        
        user_perms = ROLE_PERMISSIONS.get(role, [])
        
        if "*" in user_perms:
            return current_user # Super Admin God Mode
            
        if required_perm not in user_perms:
            logger.warning("PBAC Denied | User: %.8s | Role: %s | Missing Perm: %s", current_user.get("profile", {}).get("id"), role, required_perm)
            raise UnauthorizedAction(f"Missing required permission: {required_perm}")
            
        return current_user
        
    return permission_checker

# Backward compatibility wrapper for existing routes
require_admin = require_permission(AdminPermissions.MANAGE_SETTINGS)


def get_client_ip(request: Request) -> str:
    """Extract real client IP considering proxies."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip.strip()
    cf_ip = request.headers.get("CF-Connecting-IP")
    if cf_ip:
        return cf_ip.strip()
    return request.client.host if request.client else "unknown"
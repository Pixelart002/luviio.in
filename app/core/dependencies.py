"""
Dependencies — Async Hardened Production Grade (Luviio SSOT)
============================================================
Path: app/core/dependencies.py
"""
import json
import base64
import logging
from typing import Any, Dict, Optional, Callable

from cachetools import TTLCache
from fastapi import Depends, Request, status, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from gotrue.errors import AuthApiError

from app.core.supabase import get_async_admin_supabase
from app.repositories.user_repo import AsyncUserRepository
from app.core.exceptions import UnauthorizedAction, UnauthenticatedUser
from app.permissions.base import ROLE_PERMISSIONS
from app.enums.roles import UserRole
from app.utils.timestamp import ts_to_iso  # 🔥 FIX: Imported your Timestamp Utility

logger = logging.getLogger(__name__)

bearer_scheme = HTTPBearer(auto_error=False)

_token_cache: TTLCache = TTLCache(maxsize=1024, ttl=60)
_profile_cache: TTLCache = TTLCache(maxsize=1024, ttl=300)

def _extract_token(request: Request, credentials: Optional[HTTPAuthorizationCredentials]) -> str:
    """Strictly extracts JWT from Authorization Header OR Secure HttpOnly Cookie."""
    if credentials and credentials.credentials:
        return credentials.credentials
    
    token = request.cookies.get("access_token")
    if token:
        return token
        
    raise UnauthenticatedUser("Authentication credentials missing.")

def _extract_jwt_payload(token: str) -> dict:
    """Safely extracts JWT payload (like 'exp') without verifying signature."""
    try:
        parts = token.split('.')
        if len(parts) != 3: return {}
        payload_b64 = parts[1] + '=' * (-len(parts[1]) % 4)
        return json.loads(base64.urlsafe_b64decode(payload_b64))
    except Exception:
        return {}

async def _validate_token_natively(token: str) -> Any:
    """Uses Supabase Native Client to automatically handle RS256/HS256 algorithms securely."""
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
    except AuthApiError as e:
        logger.warning(f"Native Auth Block: {e}")
        raise UnauthenticatedUser("Token is invalid or expired.")
    except Exception as e:
        logger.error(f"Token validation error: {e}")
        raise UnauthenticatedUser("Authentication failed.")

async def _get_or_create_profile(user_id: str, email: str, user_metadata: dict) -> Dict[str, Any]:
    if user_id in _profile_cache:
        return _profile_cache[user_id]

    repo = AsyncUserRepository()
    profile = await repo.get_profile(user_id)

    if not profile:
        try:
            profile = await repo.upsert_profile(
                user_id=user_id, email=email,
                full_name=user_metadata.get("full_name", ""), phone=""
            )
        except Exception as e:
            logger.error(f"Profile auto-create failed for {user_id}: {e}")
            return {}

    if profile:
        _profile_cache[user_id] = profile
    return profile or {}

# ══════════════════════════════════════════════════════════════════════════════
#  FASTAPI DEPENDENCY INJECTIONS
# ══════════════════════════════════════════════════════════════════════════════

async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
) -> Dict[str, Any]:
    token = _extract_token(request, credentials)
    
    # 1. Native Supabase Validation (Handles RS256 safely)
    auth_user = await _validate_token_natively(token)
    user_id = str(getattr(auth_user, "id", ""))
    email = getattr(auth_user, "email", "")
    user_metadata = getattr(auth_user, "user_metadata", {}) or {}

    # Fast extraction for expiry time
    payload = _extract_jwt_payload(token)

    # 2. Bind Profile & State
    profile = await _get_or_create_profile(user_id, email, user_metadata)
    
    if profile and not profile.get("is_active", True):
        raise UnauthorizedAction("Account has been deactivated.")

    request.state.user_id = user_id
    request.state.user_name = profile.get("full_name") or email.split('@')[0] if email else "User"

    return {
        "sub": user_id,
        "email": email,
        "profile": profile,
        "jwt_role": profile.get("role", "customer"),
        "exp": ts_to_iso(payload.get("exp")),  # 🔥 FIX: Formatted to readable ISO-8601 string
        "auth_user": auth_user
    }

async def get_user_id_strict(current_user: Dict[str, Any] = Depends(get_current_user)) -> str:
    user_id = current_user.get("sub")
    if not user_id:
        raise UnauthenticatedUser("User identity missing for scope resolution.")
    return str(user_id)

def require_permission(required_perm: str) -> Callable:
    async def permission_checker(current_user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
        role = current_user.get("profile", {}).get("role", UserRole.CUSTOMER.value if hasattr(UserRole.CUSTOMER, "value") else "customer")
        user_perms = ROLE_PERMISSIONS.get(role, [])
        
        if "*" in user_perms: 
            return current_user
            
        if required_perm not in user_perms:
            logger.warning(f"PBAC Block | User {current_user.get('sub')} missing perm: {required_perm}")
            raise UnauthorizedAction(f"Missing required permission: {required_perm}")
            
        return current_user
    return permission_checker
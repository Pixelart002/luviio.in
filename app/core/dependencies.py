"""
Dependencies — Offline JWT Cryptographic Validation (Amazon-Grade SSOT)
=======================================================================
Path: app/core/dependencies.py
"""
import logging
from typing import Any, Dict, Optional, Callable

from cachetools import TTLCache
from fastapi import Depends, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import jwt, JWTError  # 🔥 pip install python-jose

# Utility imports
from app.core.config import settings
from app.repositories.user_repo import AsyncUserRepository
from app.core.exceptions import UnauthorizedAction, UnauthenticatedUser
from app.permissions.base import ROLE_PERMISSIONS
from app.enums.roles import UserRole

logger = logging.getLogger(__name__)

# Security scheme enables the 🔒 Lock icon in Swagger UI
bearer_scheme = HTTPBearer(auto_error=False)

# Profile caching saves DB hits for RBAC checks
_profile_cache: TTLCache = TTLCache(maxsize=1024, ttl=300)

# ══════════════════════════════════════════════════════════════════════════════
#  OFFLINE JWT VALIDATION (ZERO NETWORK HOP)
# ══════════════════════════════════════════════════════════════════════════════

def _extract_token(request: Request, credentials: Optional[HTTPAuthorizationCredentials]) -> str:
    """Extracts JWT from Authorization Header OR Secure HttpOnly Cookie."""
    if credentials and credentials.credentials:
        return credentials.credentials
    
    token = request.cookies.get("access_token")
    if token:
        return token
        
    raise UnauthenticatedUser("Authentication credentials missing.")

def _verify_and_decode_jwt(token: str) -> Dict[str, Any]:
    """
    Cryptographically verifies the Supabase JWT offline.
    0 Latency. 0 Network Requests. 100% Secure.
    """
    if not settings.SUPABASE_JWT_SECRET:
        logger.error("CRITICAL: SUPABASE_JWT_SECRET is missing from environment variables.")
        raise UnauthenticatedUser("Server misconfiguration.")

    try:
        payload = jwt.decode(
            token, 
            settings.SUPABASE_JWT_SECRET, 
            algorithms=["HS256"],
            audience="authenticated"
        )
        return payload
    except JWTError as e:
        logger.warning(f"Auth Block | Invalid/Expired JWT: {e}")
        raise UnauthenticatedUser("Token is invalid or expired.")

async def _get_or_create_profile(user_id: str, email: str, user_metadata: dict) -> Dict[str, Any]:
    """Fetches user profile from Cache or DB."""
    if user_id in _profile_cache:
        return _profile_cache[user_id]

    repo = AsyncUserRepository()
    profile = await repo.get_profile(user_id)

    if not profile:
        try:
            profile = await repo.upsert_profile(
                user_id=user_id,
                email=email,
                full_name=user_metadata.get("full_name", ""),
                phone=""
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
    """Main Auth Dependency for Private Routes."""
    token = _extract_token(request, credentials)
    
    # 1. Cryptographic Offline Validation
    claims = _verify_and_decode_jwt(token)
    user_id = claims.get("sub")
    email = claims.get("email", "")
    
    if not user_id:
        raise UnauthenticatedUser("Invalid token structure: Missing Subject (sub)")

    # 2. Bind Profile & State
    profile = await _get_or_create_profile(user_id, email, claims.get("user_metadata", {}))
    
    if profile and not profile.get("is_active", True):
        raise UnauthorizedAction("Account has been deactivated.")

    # Attach to request state for the Logger Middleware
    request.state.user_id = user_id
    request.state.user_name = profile.get("full_name") or email.split('@')[0] if email else "User"

    return {
        "sub": user_id,
        "email": email,
        "profile": profile,
        "jwt_role": claims.get("role"),
        "exp": claims.get("exp")
    }

async def get_user_id_strict(current_user: Dict[str, Any] = Depends(get_current_user)) -> str:
    """Convenience dependency when only the User ID is needed."""
    return str(current_user["sub"])


# ══════════════════════════════════════════════════════════════════════════════
#  ENTERPRISE PBAC GUARDS
# ══════════════════════════════════════════════════════════════════════════════

def require_permission(required_perm: str) -> Callable:
    async def permission_checker(current_user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
        role = current_user.get("profile", {}).get("role", UserRole.CUSTOMER.value if hasattr(UserRole.CUSTOMER, "value") else "customer")
        
        user_perms = ROLE_PERMISSIONS.get(role, [])
        if "*" in user_perms:  # God mode (Admin)
            return current_user
            
        if required_perm not in user_perms:
            logger.warning(f"PBAC Block | User {current_user['sub']} missing perm: {required_perm}")
            raise UnauthorizedAction(f"Missing required permission: {required_perm}")
            
        return current_user
    return permission_checker
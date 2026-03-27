"""
Dependencies — Authentication & Authorization
===============================================
Changes from original:
  1. CRITICAL FIX: .single() → repo.get_profile() which uses maybe_single()
     This eliminates the PGRST116 → 500 error when profile row is missing
  2. Auto-creates missing profile (handles users registered before trigger was added)
  3. Separated concerns: UserRepository handles all DB access (Repository Pattern)
  4. get_current_user is now a clean composition of:
       validate_token() → fetch_profile() → guard_active()
  5. ADDED SAFETY: Prevent AttributeError if auth_user.user_metadata is strictly None
  6. ADDED SAFETY: Robust response parsing for sb.auth.get_user()

LLD concepts applied:
  Repository Pattern    → no raw DB calls here
  Separation of Concerns → token validation ≠ profile fetching ≠ authorization
  Single Responsibility  → each helper does exactly one thing
  Proxy Pattern          → require_admin wraps get_current_user, adds authz layer
"""
import logging
from typing import Any

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from gotrue.errors import AuthApiError

from app.supabase_client import get_admin_supabase
from app.repositories.user_repo import UserRepository

logger = logging.getLogger(__name__)
bearer_scheme = HTTPBearer()


def _validate_token(token: str) -> Any:
    """
    Step 1: Validate JWT with Supabase Auth.
    Returns auth user object or raises 401.
    """
    sb = get_admin_supabase()
    try:
        result = sb.auth.get_user(token)
        
        # SAFE CHECK: Handle different Supabase Python SDK response shapes
        if not result or not hasattr(result, "user") or not result.user:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
            
        return result.user
        
    except HTTPException:
        raise
    except AuthApiError as e:
        logger.warning(f"Auth API Error during token validation: {e.message}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )
    except Exception as e:
        logger.warning("Token validation failed unexpectedly: %s", e)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )


def _get_or_create_profile(auth_user: Any) -> dict[str, Any]:
    """
    Step 2: Fetch profile row from users table.

    CRITICAL FIX: Original code used .single() which throws PGRST116 when
    0 rows exist → 500 Internal Server Error.

    New flow:
      1. Try get_profile() — uses maybe_single(), returns None on miss (not exception)
      2. If None → auto-create via upsert_profile() using auth user data
         (handles users registered before the DB trigger was added)
      3. Return the profile dict

    This is Idempotency in action: safe to call on every request regardless
    of whether the profile row exists.
    """
    sb = get_admin_supabase()
    repo = UserRepository(sb)

    # Safe extraction of user ID
    auth_user_id = str(getattr(auth_user, "id", ""))
    if not auth_user_id:
        return {}

    profile = repo.get_profile(auth_user_id)

    if profile is None:
        # Profile missing — defensive auto-create
        # Case 1: User registered before handle_new_user trigger was added
        # Case 2: Trigger failed silently during registration
        logger.warning(
            "Profile missing for auth user %s — auto-creating. "
            "Run migrations.sql Section 6 to prevent this permanently.",
            auth_user_id,
        )
        
        # SAFE CHECK: user_metadata might be strictly None instead of {}
        user_meta = getattr(auth_user, "user_metadata", None) or {}
        email = getattr(auth_user, "email", "") or ""
        
        profile = repo.upsert_profile(
            user_id=auth_user_id,
            email=email,
            full_name=user_meta.get("full_name", "") or "",
        )

    return profile or {}


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> dict[str, Any]:
    """
    Composed dependency: validate → fetch/create → guard.

    Returns {"auth_user": ..., "profile": ...} — same shape as before,
    so all existing routers work without changes.
    """
    auth_user = _validate_token(credentials.credentials)
    profile   = _get_or_create_profile(auth_user)

    if not profile:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not retrieve or create user profile",
        )

    if not profile.get("is_active", True):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account deactivated",
        )

    return {"auth_user": auth_user, "profile": profile}


def require_admin(current: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    """
    Proxy Pattern — wraps get_current_user and adds admin authorization layer.
    All existing admin routers work unchanged.
    """
    if current.get("profile", {}).get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return current
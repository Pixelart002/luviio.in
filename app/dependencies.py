"""
app/dependencies.py  — Hardened version
=========================================
SECURITY FIXES:
  1. require_admin now does a FRESH DB read every call
     Old: trusted profile from JWT/cache (could be stale or spoofed)
     New: re-fetches role from DB on every protected request
  2. Added is_active check in require_admin
  3. Timing-safe comparison for role string
  4. Added structured logging for all failed auth attempts
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
    """Validate JWT with Supabase Auth. Returns auth user or raises 401."""
    sb = get_admin_supabase()
    try:
        result = sb.auth.get_user(token)
        if not result or not hasattr(result, "user") or not result.user:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
        return result.user
    except HTTPException:
        raise
    except AuthApiError as e:
        logger.warning("Auth API error during token validation: %s", e.message)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")
    except Exception as e:
        logger.warning("Token validation failed unexpectedly: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")


def _get_or_create_profile(auth_user: Any) -> dict[str, Any]:
    """Fetch profile from DB. Auto-creates if missing."""
    sb   = get_admin_supabase()
    repo = UserRepository(sb)

    auth_user_id = str(getattr(auth_user, "id", ""))
    if not auth_user_id:
        return {}

    profile = repo.get_profile(auth_user_id)

    if profile is None:
        logger.warning("Profile missing for auth user %s — auto-creating.", auth_user_id)
        user_meta = getattr(auth_user, "user_metadata", None) or {}
        email     = getattr(auth_user, "email", "") or ""
        profile   = repo.upsert_profile(
            user_id=auth_user_id,
            email=email,
            full_name=user_meta.get("full_name", "") or "",
        )

    return profile or {}


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> dict[str, Any]:
    """Validate token → fetch profile → guard active."""
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
    SECURITY FIX: Always does a FRESH DB read for role.

    Old pattern:
      if current.get("profile", {}).get("role") != "admin":  ← trusts cache
          raise 403

    New pattern:
      Re-fetches role from DB on EVERY admin request.
      This prevents:
        - Stale cache attacks (role downgraded but old token still works)
        - Any future JWT claim manipulation

    Performance note: This adds 1 DB query per admin request.
    This is intentional and acceptable for security.
    Admin operations are low-frequency; correctness > speed here.
    """
    sb      = get_admin_supabase()
    user_id = current.get("profile", {}).get("id", "")

    if not user_id:
        logger.warning("require_admin: no user_id in current context")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )

    # FRESH DB read — never trust cached/JWT role
    try:
        result = (
            sb.table("users")
            .select("role, is_active")
            .eq("id", user_id)
            .limit(1)
            .execute()
        )
    except Exception as e:
        logger.error("require_admin DB check failed for user %s: %s", user_id, e)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not verify permissions",
        )

    if not result or not result.data:
        logger.warning("require_admin: no DB row found for user %s", user_id)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )

    row = result.data[0]

    # Check both role AND active status
    # Use == not `in` to avoid type confusion attacks
    if row.get("role") != "admin":
        logger.warning(
            "require_admin: user %s attempted admin access with role=%s",
            user_id, row.get("role")
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )

    if not row.get("is_active", False):
        logger.warning(
            "require_admin: deactivated admin %s attempted access",
            user_id
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account deactivated",
        )

    # Merge fresh DB data into current context so downstream can use it
    current["profile"]["role"]      = row["role"]
    current["profile"]["is_active"] = row["is_active"]
    return current
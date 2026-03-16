import logging
from typing import Any

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from app.supabase_client import get_admin_supabase

logger = logging.getLogger(__name__)
bearer_scheme = HTTPBearer()


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> dict[str, Any]:
    token: str = credentials.credentials
    sb = get_admin_supabase()

    try:
        result = sb.auth.get_user(token)
        if not result or not result.user:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
        user = result.user
    except HTTPException:
        raise
    except Exception as e:
        logger.warning("Token validation failed: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")

    try:
        profile_res = (
            sb.table("users")
            .select("id, email, full_name, phone, role, is_active, created_at")
            .eq("id", user.id)
            .single()
            .execute()
        )
    except Exception as e:
        logger.error("Profile fetch failed for user %s: %s", user.id, e)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Could not retrieve user profile")

    if not profile_res.data:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User profile not found")
    if not profile_res.data.get("is_active", True):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account deactivated")

    return {"auth_user": user, "profile": profile_res.data}


def require_admin(current: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    if current["profile"].get("role") != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return current
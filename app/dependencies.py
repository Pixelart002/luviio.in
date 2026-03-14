from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.supabase_client import get_admin_supabase

bearer_scheme = HTTPBearer()


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
):
    """
    Validates the Supabase JWT and returns the user dict.
    Works with tokens issued by Supabase Auth (sign-in / sign-up).
    """
    token = credentials.credentials
    sb = get_admin_supabase()
    try:
        result = sb.auth.get_user(token)
        if not result or not result.user:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
        user = result.user
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")

    # Fetch profile (role, is_active) from public.users
    profile = sb.table("users").select("*").eq("id", user.id).single().execute()
    if not profile.data:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User profile not found")
    if not profile.data.get("is_active", True):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account deactivated")

    return {"auth_user": user, "profile": profile.data}


def require_admin(current: dict = Depends(get_current_user)):
    if current["profile"].get("role") != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return current

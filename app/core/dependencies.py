"""
Dependencies — Hardened Production Grade
=========================================
SECURITY FIXES:
  1. require_admin: FRESH DB read every call (no cache trust)
  2. require_admin: is_active double-check
  3. Token validation with proper error isolation
  4. Auto-profile creation for new users
  5. Structured logging for all auth failures
  6. Timing-safe role comparison

LOGGER INTEGRATION:
  Automatically injects user_name and user_id into request.state 
  for the Pure Window Logger Middleware.

Architecture:
  get_current_user → validate JWT → fetch/create profile → check active → update logger state
  require_admin    → get_current_user → FRESH DB role check → guard active
"""
import hmac
import logging
from typing import Any

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from gotrue.errors import AuthApiError

from app.repositories.user_repo import UserRepository
from app.core.supabase import get_admin_supabase, get_supabase

logger = logging.getLogger(__name__)
bearer_scheme = HTTPBearer(auto_error=False)  # Don't auto-raise — we handle manually


# ══════════════════════════════════════════════════════════════════════════════
#  TOKEN VALIDATION
# ══════════════════════════════════════════════════════════════════════════════

def _validate_token(token: str) -> Any:
    """
    Validate JWT with Supabase Auth.
    Returns auth user object or raises 401.
    
    Security: Never reveals WHY token is invalid (anti-enumeration).
    """
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )

    sb = get_admin_supabase()
    try:
        result = sb.auth.get_user(token)
        if not result or not hasattr(result, "user") or not result.user:
            logger.warning("Token validated but no user object returned")
            raise HTTPException(401, "Invalid token")
        return result.user

    except HTTPException:
        raise
    except AuthApiError as e:
        # Don't leak specific error to client
        logger.warning("Auth API error: %s", e.message)
        raise HTTPException(401, "Invalid or expired token")
    except Exception as e:
        logger.error("Unexpected token validation error: %s", e)
        raise HTTPException(401, "Invalid or expired token")


# ══════════════════════════════════════════════════════════════════════════════
#  PROFILE MANAGEMENT
# ══════════════════════════════════════════════════════════════════════════════

def _get_or_create_profile(auth_user: Any) -> dict[str, Any]:
    """
    Fetch profile from DB. Auto-creates if missing (first login).
    
    Returns empty dict on failure — caller handles.
    """
    sb = get_admin_supabase()
    repo = UserRepository(sb)

    auth_user_id = str(getattr(auth_user, "id", ""))
    if not auth_user_id:
        logger.error("Auth user has no ID")
        return {}

    try:
        profile = repo.get_profile(auth_user_id)
    except Exception as e:
        logger.error("Profile fetch failed for %s: %s", auth_user_id[:8], e)
        return {}

    if profile is None:
        logger.info("Profile missing for user %.8s — auto-creating", auth_user_id)
        user_meta = getattr(auth_user, "user_metadata", None) or {}
        email = getattr(auth_user, "email", "") or ""
        phone = getattr(auth_user, "phone", "") or ""

        try:
            profile = repo.upsert_profile(
                user_id=auth_user_id,
                email=email,
                full_name=user_meta.get("full_name", "") or "",
                phone=phone,
            )
            if profile:
                logger.info("Profile auto-created for user %.8s", auth_user_id)
        except Exception as e:
            logger.error("Profile auto-create failed for %.8s: %s", auth_user_id, e)
            return {}

    return profile or {}


# ══════════════════════════════════════════════════════════════════════════════
#  CURRENT USER DEPENDENCY
# ══════════════════════════════════════════════════════════════════════════════

async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> dict[str, Any]:
    """
    Validate token → fetch/create profile → check active.
    
    Used by: All authenticated endpoints.
    
    Returns:
        {"auth_user": SupabaseUser, "profile": dict}
    """
    # ── Check if token present ────────────────────────────────────────────
    if not credentials:
        # Try cookie-based auth for browser refresh
        refresh_token = request.cookies.get("refresh_token")
        if refresh_token:
            try:
                sb = get_supabase()
                result = sb.auth.refresh_session(refresh_token)
                if result and hasattr(result, "session") and result.session:
                    token = result.session.access_token
                    auth_user = _validate_token(token)
                    profile = _get_or_create_profile(auth_user)
                    if profile and profile.get("is_active", True):
                        
                        # Update Logger State
                        if hasattr(request.state, "user_name"):
                            request.state.user_name = profile.get("full_name") or profile.get("email") or "Unknown"
                            request.state.user_id = profile.get("id") or getattr(auth_user, "id", "N/A")
                            
                        return {"auth_user": auth_user, "profile": profile}
            except Exception:
                pass
        
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )

    # ── Validate token ─────────────────────────────────────────────────────
    auth_user = _validate_token(credentials.credentials)
    profile = _get_or_create_profile(auth_user)

    if not profile:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not retrieve user profile",
        )

    # ── Active check ───────────────────────────────────────────────────────
    if not profile.get("is_active", True):
        logger.warning("Deactivated account access attempt | user=%.8s", profile.get("id", "?"))
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account deactivated",
        )

    # ── Update Logger State ────────────────────────────────────────────────
    if hasattr(request.state, "user_name"):
        request.state.user_name = profile.get("full_name") or profile.get("email") or "Unknown"
        request.state.user_id = profile.get("id") or getattr(auth_user, "id", "N/A")

    return {"auth_user": auth_user, "profile": profile}


# ══════════════════════════════════════════════════════════════════════════════
#  OPTIONAL USER (doesn't fail if not logged in)
# ══════════════════════════════════════════════════════════════════════════════

async def get_optional_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> dict[str, Any] | None:
    """
    Like get_current_user but returns None instead of 401.
    Used by: Public endpoints that show different content for logged-in users.
    """
    if not credentials:
        return None
    
    try:
        auth_user = _validate_token(credentials.credentials)
        profile = _get_or_create_profile(auth_user)
        if profile and profile.get("is_active", True):
            
            # ── Update Logger State ────────────────────────────────────────
            if hasattr(request.state, "user_name"):
                request.state.user_name = profile.get("full_name") or profile.get("email") or "Unknown"
                request.state.user_id = profile.get("id") or getattr(auth_user, "id", "N/A")
                
            return {"auth_user": auth_user, "profile": profile}
    except Exception:
        pass
    
    return None


# ══════════════════════════════════════════════════════════════════════════════
#  ADMIN GUARD — FRESH DB READ EVERY TIME
# ══════════════════════════════════════════════════════════════════════════════

def require_admin(
    current: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """
    FRESH DB read for admin role — NEVER trusts cache or JWT claims.
    """
    sb = get_admin_supabase()
    user_id = current.get("profile", {}).get("id", "")

    if not user_id:
        logger.warning("require_admin: no user_id in context")
        raise HTTPException(403, "Access denied")

    # ── FRESH DB READ ──────────────────────────────────────────────────────
    try:
        result = (
            sb.table("users")
            .select("role, is_active")
            .eq("id", user_id)
            .limit(1)
            .maybe_single()
            .execute()
        )
    except Exception as e:
        logger.error("require_admin DB check failed | user=%.8s: %s", user_id, e)
        raise HTTPException(503, "Could not verify permissions")

    if not result or not result.data:
        logger.warning("require_admin: no DB row | user=%.8s", user_id)
        raise HTTPException(403, "Access denied")

    row = result.data

    # ── Role check (exact string comparison) ───────────────────────────────
    db_role = row.get("role", "")
    
    # Timing-safe comparison to prevent timing attacks
    if not hmac.compare_digest(db_role, "admin"):
        logger.warning(
            "require_admin: non-admin access attempt | user=%.8s role=%s",
            user_id, db_role
        )
        raise HTTPException(403, "Admin access required")

    # ── Active check ───────────────────────────────────────────────────────
    if not row.get("is_active", False):
        logger.warning(
            "require_admin: deactivated admin | user=%.8s",
            user_id
        )
        raise HTTPException(403, "Account deactivated")

    # ── Merge fresh DB data into current context ───────────────────────────
    current["profile"]["role"] = db_role
    current["profile"]["is_active"] = row["is_active"]

    return current


# ══════════════════════════════════════════════════════════════════════════════
#  RATE LIMIT KEY EXTRACTOR
# ══════════════════════════════════════════════════════════════════════════════

def get_client_ip(request: Request) -> str:
    """
    Extract real client IP considering proxies.
    Used by slowapi rate limiter.
    """
    # Check common proxy headers
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip.strip()
    
    cf_ip = request.headers.get("CF-Connecting-IP")  # Cloudflare
    if cf_ip:
        return cf_ip.strip()
    
    return request.client.host if request.client else "unknown"

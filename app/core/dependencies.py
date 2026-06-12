"""
Dependencies — Async Hardened Production Grade
==============================================
Path: app/core/dependencies.py

SECURITY & ARCHITECTURE FIXES:
  1. ALL Supabase Auth and DB calls converted to async/await (Zero Blocking).
  2. require_admin: FRESH DB read every call (no cache trust)
  3. require_admin: is_active double-check
  4. Token validation with proper error isolation
  5. Auto-profile creation for new users
  6. Structured logging for all auth failures
  7. Timing-safe role comparison

LOGGER INTEGRATION:
  Automatically injects user_name and user_id into request.state 
  for the Pure Window Logger Middleware.
"""
import asyncio
import hmac
import logging
from typing import Any

from cachetools import TTLCache
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from gotrue.errors import AuthApiError

# 🔥 ARCHITECTURE IMPORTS (Async)
from app.repositories.user_repo import AsyncUserRepository
from app.core.supabase import get_async_admin_supabase, get_async_supabase

logger = logging.getLogger(__name__)
bearer_scheme = HTTPBearer(auto_error=False)  # Don't auto-raise — we handle manually

# ── Auth caches (TTL=60s) to avoid redundant Supabase HTTP calls per request ──
_token_cache: TTLCache = TTLCache(maxsize=512, ttl=60)
_profile_cache: TTLCache = TTLCache(maxsize=512, ttl=60)
_cache_lock = asyncio.Lock()


# ══════════════════════════════════════════════════════════════════════════════
#  TOKEN VALIDATION
# ══════════════════════════════════════════════════════════════════════════════

async def _validate_token(token: str) -> Any:
    """Validate JWT with Supabase Auth asynchronously. Result is cached for 60s."""
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )

    # Return cached result if available (avoids ~800ms Supabase Auth HTTP call)
    if token in _token_cache:
        return _token_cache[token]

    sb = get_async_admin_supabase()
    try:
        result = await sb.auth.get_user(token)
        
        # 🔥 FIX: Handle both v1.0+ UserResponse and older direct User objects
        user = getattr(result, "user", result)
        if not user or not hasattr(user, "id"):
            logger.warning("Token validated but no user object returned")
            raise HTTPException(401, "Invalid token")

        _token_cache[token] = user
        return user

    except HTTPException:
        raise
    except AuthApiError as e:
        logger.warning("Auth API error: %s", e.message)
        raise HTTPException(401, "Invalid or expired token")
    except Exception as e:
        logger.error("Unexpected token validation error: %s", e)
        raise HTTPException(401, "Invalid or expired token")


# ══════════════════════════════════════════════════════════════════════════════
#  PROFILE MANAGEMENT
# ══════════════════════════════════════════════════════════════════════════════

async def _get_or_create_profile(auth_user: Any) -> dict[str, Any]:
    """Fetch profile from DB asynchronously. Auto-creates if missing. Result cached 60s."""
    repo = AsyncUserRepository()

    auth_user_id = str(getattr(auth_user, "id", ""))
    if not auth_user_id:
        logger.error("Auth user has no ID")
        return {}

    # Return cached profile if available (avoids ~700ms Supabase DB HTTP call)
    if auth_user_id in _profile_cache:
        return _profile_cache[auth_user_id]

    try:
        profile = await repo.get_profile(auth_user_id)
    except Exception as e:
        logger.error("Profile fetch failed for %s: %s", auth_user_id[:8], e)
        return {}

    if not profile:
        logger.info("Profile missing for user %.8s — auto-creating", auth_user_id)
        user_meta = getattr(auth_user, "user_metadata", None) or {}
        email = getattr(auth_user, "email", "") or ""
        phone = getattr(auth_user, "phone", "") or ""

        try:
            profile = await repo.upsert_profile(
                user_id=auth_user_id,
                email=email,
                full_name=user_meta.get("full_name", "") or "",
                phone=phone,
            )
            if not profile:
                logger.error("Profile upsert returned no data for user %.8s", auth_user_id)
        except Exception as e:
            logger.error("Profile auto-create failed for %.8s: %s", auth_user_id, e)
            return {}

    result = profile or {}
    if result:
        _profile_cache[auth_user_id] = result
    return result


# ══════════════════════════════════════════════════════════════════════════════
#  CURRENT USER DEPENDENCY
# ══════════════════════════════════════════════════════════════════════════════

async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> dict[str, Any]:
    """Validate token → fetch/create profile → check active."""
    
    # ── Check if token present ────────────────────────────────────────────
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
                        
                        # 🔥 FIX: Directly assign to state (Removed hasattr block)
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
    auth_user = await _validate_token(credentials.credentials)
    profile = await _get_or_create_profile(auth_user)

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

    # 🔥 FIX: Directly assign to state so logger actually receives the info
    request.state.user_name = profile.get("full_name") or profile.get("email") or "Unknown"
    request.state.user_id = profile.get("id") or getattr(auth_user, "id", "N/A")

    return {"auth_user": auth_user, "profile": profile}


# ══════════════════════════════════════════════════════════════════════════════
#  OPTIONAL USER
# ══════════════════════════════════════════════════════════════════════════════

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
            
            # 🔥 FIX: Directly assign to state
            request.state.user_name = profile.get("full_name") or profile.get("email") or "Unknown"
            request.state.user_id = profile.get("id") or getattr(auth_user, "id", "N/A")
            
            return {"auth_user": auth_user, "profile": profile}
    except Exception:
        pass
    
    return None


# ══════════════════════════════════════════════════════════════════════════════
#  ADMIN GUARD — FRESH DB READ EVERY TIME
# ══════════════════════════════════════════════════════════════════════════════

async def require_admin(
    current: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """FRESH DB read for admin role — NEVER trusts cache or JWT claims."""
    sb = get_async_admin_supabase()
    
    # 🔥 FIX: Fallback to auth_user.id if profile.id is missing
    user_id = current.get("profile", {}).get("id") or getattr(current.get("auth_user"), "id", "")

    if not user_id:
        logger.warning("require_admin: no user_id in context")
        raise HTTPException(403, "Access denied")

    # ── FRESH DB READ ──────────────────────────────────────────────────────
    try:
        result = await (
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

    # 🔥 FIX: Safely extract data handling potential None values
    row = getattr(result, "data", None)
    if not row:
        logger.warning("require_admin: no DB row | user=%.8s", user_id)
        raise HTTPException(403, "Access denied")

    # ── Role check ─────────────────────────────────────────────────────────
    # 🔥 FIX: Force string conversion to prevent HMAC TypeError if role is NULL
    db_role = str(row.get("role") or "")
    
    if not hmac.compare_digest(db_role, "admin"):
        logger.warning(
            "require_admin: non-admin access attempt | user=%.8s role=%s",
            user_id, db_role
        )
        raise HTTPException(403, "Admin access required")

    # ── Active check ───────────────────────────────────────────────────────
    # 🔥 FIX: Default to True if is_active is missing/null in the database
    if not row.get("is_active", True):
        logger.warning(
            "require_admin: deactivated admin | user=%.8s",
            user_id
        )
        raise HTTPException(403, "Account deactivated")

    # Merge fresh DB data into current context
    current["profile"]["role"] = db_role
    current["profile"]["is_active"] = row.get("is_active", True)

    return current


# ══════════════════════════════════════════════════════════════════════════════
#  RATE LIMIT KEY EXTRACTOR
# ══════════════════════════════════════════════════════════════════════════════

def get_client_ip(request: Request) -> str:
    """Extract real client IP considering proxies."""
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
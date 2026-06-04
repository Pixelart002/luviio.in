"""
Admin Verification Router — Production Grade
=============================================
Dedicated endpoint for frontend to VERIFY admin role server-side.

WHY THIS EXISTS:
  The frontend admin check reads from sessionStorage cache which
  can be spoofed or stale. This endpoint forces a live DB lookup
  on every admin panel load — no cache, no race condition.

SECURITY & STABILITY LAYERS:
  1. Live DB lookup (no cache, no sessionStorage trust)
  2. Role + is_active double-check
  3. Rate limiting to prevent enumeration
  4. Audit logging for access attempts
  5. Timing attack mitigation
  6. Safe user_id extraction (no KeyError crashes)
  7. FIXED: PostgREST 406 Error protection using strict .limit(1)
  8. FIXED: Prevented massive RAM memory leak on exact counts
  9. NEW: Pure Window Logger integration for clear terminal tracking
"""
import logging
import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.dependencies import get_current_user
from app.supabase_client import get_admin_supabase

logger = logging.getLogger(__name__)
limiter = Limiter(key_func=get_remote_address)
router = APIRouter(prefix="/admin", tags=["Admin"])

# ── Constants ─────────────────────────────────────────────────────────────────
_MIN_RESPONSE_SECONDS = 0.2  # Timing attack mitigation


# ── Helper ────────────────────────────────────────────────────────────────────

def _get_user_id(current_user: dict[str, Any]) -> str:
    """Safely extract user_id — no KeyError crashes."""
    if (
        "profile" in current_user 
        and isinstance(current_user["profile"], dict) 
        and "id" in current_user["profile"]
    ):
        return str(current_user["profile"]["id"])
    if "id" in current_user:
        return str(current_user["id"])
    if "sub" in current_user:
        return str(current_user["sub"])
    
    logger.error(f"Cannot find user ID in: {list(current_user.keys())}")
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="User ID not found in session"
    )


# ══════════════════════════════════════════════════════════════════════════════
#  VERIFY ENDPOINT
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/verify")
@limiter.limit("30/minute")  
def verify_admin(
    request: Request,
    current: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """
    Live DB check — never uses cached profile.
    Frontend MUST call this before rendering any admin UI.
    """
    start = time.monotonic()
    client_ip = get_remote_address(request)
    
    user_id = _get_user_id(current)
    sb = get_admin_supabase()
    
    if hasattr(request.state, "actions"):
        request.state.actions.append(f"Admin verification requested for user: {user_id[:8]}...")
        request.state.actions.append("Fetching live user profile from database (Bypassing Cache)")
    
    try:
        result = (
            sb.table("users")
            .select("id, email, full_name, role, is_active, created_at")
            .eq("id", user_id)
            .limit(1)
            .execute()
        )
    except Exception as exc:
        logger.error("Admin verify DB error | user=%.8s: %s", user_id, exc)
        elapsed = time.monotonic() - start
        time.sleep(max(0.0, _MIN_RESPONSE_SECONDS - elapsed))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service temporarily unavailable"
        )

    if not result or not hasattr(result, "data") or not result.data:
        logger.warning(
            "Admin verify failed: user not found | user=%.8s ip=%s", 
            user_id, client_ip
        )
        elapsed = time.monotonic() - start
        time.sleep(max(0.0, _MIN_RESPONSE_SECONDS - elapsed))
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied"
        )

    profile = result.data[0]

    user_role = profile.get("role", "")
    is_active = profile.get("is_active", False)
    
    if hasattr(request.state, "actions"):
        request.state.actions.append(f"Validating strict requirements: Role='{user_role}', Active={is_active}")

    if user_role != "admin":
        logger.warning(
            "Admin verify failed: not admin | user=%.8s role=%s ip=%s",
            user_id, user_role, client_ip
        )
        elapsed = time.monotonic() - start
        time.sleep(max(0.0, _MIN_RESPONSE_SECONDS - elapsed))
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied"
        )

    if not is_active:
        logger.warning(
            "Admin verify failed: deactivated | user=%.8s ip=%s",
            user_id, client_ip
        )
        elapsed = time.monotonic() - start
        time.sleep(max(0.0, _MIN_RESPONSE_SECONDS - elapsed))
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied"
        )

    if hasattr(request.state, "actions"):
        request.state.actions.append("Admin role and active status verified successfully ✅")

    logger.info(
        "Admin verified | user=%.8s email=%s ip=%s", 
        user_id, profile.get("email"), client_ip
    )

    safe_profile = {
        "id": profile.get("id"),
        "email": profile.get("email"),
        "full_name": profile.get("full_name"),
        "role": profile.get("role"),
        "is_active": profile.get("is_active"),
        "created_at": profile.get("created_at"),
    }

    return {
        "verified": True,
        "profile": safe_profile,
        "timestamp": int(time.time()),
    }


# ══════════════════════════════════════════════════════════════════════════════
#  ADMIN DASHBOARD STATS (Quick stats for admin panel)
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/stats")
@limiter.limit("10/minute")
def admin_stats(
    request: Request,
    current: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """
    Quick dashboard stats for admin panel.
    Also serves as secondary verification (must pass verify first).
    """
    user_id = _get_user_id(current)
    sb = get_admin_supabase()
    
    if hasattr(request.state, "actions"):
        request.state.actions.append("Admin dashboard stats requested")
        request.state.actions.append("Re-verifying admin privileges (Secondary DB Guard)")
    
    admin_check = (
        sb.table("users")
        .select("role, is_active")
        .eq("id", user_id)
        .limit(1)
        .execute()
    )
    
    if not admin_check or not hasattr(admin_check, "data") or not admin_check.data:
        raise HTTPException(403, "Access denied")
        
    admin_data = admin_check.data[0]
    if admin_data.get("role") != "admin" or not admin_data.get("is_active"):
        raise HTTPException(403, "Access denied")

    if hasattr(request.state, "actions"):
        request.state.actions.append("Aggregating metrics (products, orders, users, revenue)...")

    stats = {}
    
    try:
        products = (
            sb.table("products")
            .select("id", count="exact")
            .eq("is_active", True)
            .limit(1)
            .execute()
        )
        stats["products"] = products.count if products and hasattr(products, "count") and products.count else 0
    except Exception as exc:
        logger.warning("Stats: product count failed: %s", exc)
        stats["products"] = -1

    try:
        orders = sb.table("orders").select("id", count="exact").limit(1).execute()
        stats["orders"] = orders.count if orders and hasattr(orders, "count") and orders.count else 0
    except Exception as exc:
        logger.warning("Stats: order count failed: %s", exc)
        stats["orders"] = -1

    try:
        pending = (
            sb.table("orders")
            .select("id", count="exact")
            .eq("status", "pending")
            .limit(1)
            .execute()
        )
        stats["pending_orders"] = pending.count if pending and hasattr(pending, "count") and pending.count else 0
    except Exception as exc:
        logger.warning("Stats: pending count failed: %s", exc)
        stats["pending_orders"] = -1

    try:
        users = sb.table("users").select("id", count="exact").limit(1).execute()
        stats["users"] = users.count if users and hasattr(users, "count") and users.count else 0
    except Exception as exc:
        logger.warning("Stats: user count failed: %s", exc)
        stats["users"] = -1

    try:
        revenue_res = (
            sb.table("orders")
            .select("total_amount")
            .in_("status", ["paid", "shipped", "delivered"])
            .execute()
        )
        if revenue_res and hasattr(revenue_res, "data") and revenue_res.data:
            stats["revenue"] = round(
                sum(float(o.get("total_amount", 0)) for o in revenue_res.data), 
                2
            )
        else:
            stats["revenue"] = 0
    except Exception as exc:
        logger.warning("Stats: revenue calc failed: %s", exc)
        stats["revenue"] = -1
        
    if hasattr(request.state, "actions"):
        request.state.actions.append("Dashboard metrics aggregation complete")

    return {
        "verified": True,
        "stats": stats,
        "timestamp": int(time.time()),
    }

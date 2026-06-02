"""
Admin Verification Router — Production Grade
=============================================
Dedicated endpoint for frontend to VERIFY admin role server-side.

WHY THIS EXISTS:
  The frontend admin check reads from sessionStorage cache which
  can be spoofed or stale. This endpoint forces a live DB lookup
  on every admin panel load — no cache, no race condition.

  Frontend calls GET /api/v1/admin/verify on page load.
  If not admin → 403, frontend redirects IMMEDIATELY (no setTimeout).
  If admin → 200 with fresh profile.

  Even if XSS steals a customer's token, they cannot get 200 here.

SECURITY LAYERS:
  1. Live DB lookup (no cache, no sessionStorage trust)
  2. Role + is_active double-check
  3. Rate limiting to prevent enumeration
  4. Audit logging for access attempts
  5. Timing attack mitigation
  6. Safe user_id extraction (no KeyError crashes)
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
    if "profile" in current_user and isinstance(current_user["profile"], dict) and "id" in current_user["profile"]:
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
@limiter.limit("30/minute")  # Prevent abuse (normal usage: 1-2 per page load)
def verify_admin(
    request: Request,
    current: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """
    Live DB check — never uses cached profile.
    
    Frontend MUST call this before rendering any admin UI.
    
    Usage:
      const res = await fetch('/api/v1/admin/verify', {
        headers: { Authorization: `Bearer ${token}` }
      });
      if (!res.ok) { window.location.href = '/'; return; }
      const { profile } = await res.json();
      // Safe to render admin UI
    """
    start = time.monotonic()
    client_ip = get_remote_address(request)
    
    # ── Safe user ID extraction ───────────────────────────────────────────────
    user_id = _get_user_id(current)
    
    # ── Force fresh DB read — no cache, no stale data ─────────────────────────
    sb = get_admin_supabase()
    
    try:
        result = (
            sb.table("users")
            .select("id, email, full_name, role, is_active, created_at")
            .eq("id", user_id)
            .limit(1)
            .maybe_single()  # Safe — won't crash on missing
            .execute()
        )
    except Exception as exc:
        logger.error("Admin verify DB error | user=%.8s: %s", user_id, exc)
        # Timing mitigation
        elapsed = time.monotonic() - start
        time.sleep(max(0.0, _MIN_RESPONSE_SECONDS - elapsed))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service temporarily unavailable"
        )

    # ── Check: user exists ────────────────────────────────────────────────────
    if not result or not hasattr(result, "data") or not result.data:
        logger.warning("Admin verify failed: user not found | user=%.8s ip=%s", user_id, client_ip)
        elapsed = time.monotonic() - start
        time.sleep(max(0.0, _MIN_RESPONSE_SECONDS - elapsed))
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied"
        )

    profile = result.data

    # ── Double-check: role AND is_active ──────────────────────────────────────
    user_role = profile.get("role", "")
    is_active = profile.get("is_active", False)

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

    # ── SUCCESS — Admin verified ──────────────────────────────────────────────
    logger.info("Admin verified | user=%.8s email=%s ip=%s", user_id, profile.get("email"), client_ip)

    # ── Return fresh profile (safe fields only) ───────────────────────────────
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
    # ── Verify admin first ────────────────────────────────────────────────────
    user_id = _get_user_id(current)
    sb = get_admin_supabase()
    
    # Quick verification (lighter than /verify)
    admin_check = (
        sb.table("users")
        .select("role, is_active")
        .eq("id", user_id)
        .maybe_single()
        .execute()
    )
    
    if not admin_check or not admin_check.data:
        raise HTTPException(403, "Access denied")
    if admin_check.data.get("role") != "admin" or not admin_check.data.get("is_active"):
        raise HTTPException(403, "Access denied")

    # ── Gather stats ──────────────────────────────────────────────────────────
    stats = {}
    
    try:
        # Product count
        products = sb.table("products").select("id", count="exact").eq("is_active", True).execute()
        stats["products"] = products.count if products and hasattr(products, "count") else 0
    except Exception as exc:
        logger.warning("Stats: product count failed: %s", exc)
        stats["products"] = -1

    try:
        # Order count
        orders = sb.table("orders").select("id", count="exact").execute()
        stats["orders"] = orders.count if orders and hasattr(orders, "count") else 0
    except Exception as exc:
        logger.warning("Stats: order count failed: %s", exc)
        stats["orders"] = -1

    try:
        # Pending orders
        pending = sb.table("orders").select("id", count="exact").eq("status", "pending").execute()
        stats["pending_orders"] = pending.count if pending and hasattr(pending, "count") else 0
    except Exception as exc:
        logger.warning("Stats: pending count failed: %s", exc)
        stats["pending_orders"] = -1

    try:
        # User count
        users = sb.table("users").select("id", count="exact").execute()
        stats["users"] = users.count if users and hasattr(users, "count") else 0
    except Exception as exc:
        logger.warning("Stats: user count failed: %s", exc)
        stats["users"] = -1

    try:
        # Revenue (paid + shipped + delivered)
        revenue_res = (
            sb.table("orders")
            .select("total_amount")
            .in_("status", ["paid", "shipped", "delivered"])
            .execute()
        )
        if revenue_res and revenue_res.data:
            stats["revenue"] = round(sum(float(o.get("total_amount", 0)) for o in revenue_res.data), 2)
        else:
            stats["revenue"] = 0
    except Exception as exc:
        logger.warning("Stats: revenue calc failed: %s", exc)
        stats["revenue"] = -1

    return {
        "verified": True,
        "stats": stats,
        "timestamp": int(time.time()),
    }
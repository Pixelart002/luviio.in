"""
app/routers/admin_verify.py
============================
Dedicated endpoint for frontend to VERIFY admin role server-side.

WHY THIS EXISTS:
  The frontend admin check reads from sessionStorage cache which
  can be spoofed or stale. This endpoint forces a live DB lookup
  on every admin panel load — no cache, no race condition.

  Frontend calls GET /api/v1/admin/verify on page load.
  If not admin → 403, frontend redirects IMMEDIATELY (no setTimeout).
  If admin → 200 with fresh profile.

  Even if XSS steals a customer's token, they cannot get 200 here.
"""
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, status
from app.dependencies import get_current_user
from app.supabase_client import get_admin_supabase

router = APIRouter(prefix="/admin", tags=["Admin"])


@router.get("/verify")
def verify_admin(current: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    """
    Live DB check — never uses cached profile.
    Frontend MUST call this before rendering any admin UI.
    """
    sb      = get_admin_supabase()
    user_id = current["profile"]["id"]

    # Force fresh DB read — ignore any in-memory/cache state
    result = (
        sb.table("users")
        .select("id, email, full_name, role, is_active")
        .eq("id", user_id)
        .limit(1)
        .execute()
    )

    if not result or not result.data:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )

    profile = result.data[0]

    # Double-check: both role AND is_active
    if profile.get("role") != "admin" or not profile.get("is_active", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )

    return {
        "verified": True,
        "profile":  profile,
    }
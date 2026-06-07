"""
Admin Verification Router — Enterprise Grade
=============================================
Path: app/api/v1/routers/admin_verify.py
"""
import logging
import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from slowapi import Limiter
from slowapi.util import get_remote_address

# 🔥 ARCHITECTURE IMPORTS
from app.core.dependencies import get_current_user
from app.repositories.admin_repo import AdminRepository
from app.api.schemas.admin_dto import AdminVerifyResponse, AdminStatsResponse

logger = logging.getLogger(__name__)
limiter = Limiter(key_func=get_remote_address)
router = APIRouter(prefix="/admin", tags=["Admin"])

_MIN_RESPONSE_SECONDS = 0.2  # Timing attack mitigation

def _get_user_id(current_user: dict[str, Any]) -> str:
    if "profile" in current_user and isinstance(current_user["profile"], dict) and "id" in current_user["profile"]:
        return str(current_user["profile"]["id"])
    if "id" in current_user: return str(current_user["id"])
    if "sub" in current_user: return str(current_user["sub"])
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User ID not found in session")

# ══════════════════════════════════════════════════════════════════════════════
#  VERIFY ENDPOINT
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/verify", response_model=AdminVerifyResponse)
@limiter.limit("30/minute")  
def verify_admin(request: Request, current: dict[str, Any] = Depends(get_current_user)):
    start = time.monotonic()
    client_ip = get_remote_address(request)
    user_id = _get_user_id(current)
    
    admin_repo = AdminRepository()
    
    if hasattr(request.state, "actions"):
        request.state.actions.append(f"Admin verification requested for user: {user_id[:8]}...")
        request.state.actions.append("Fetching live user profile via AdminRepository")
    
    profile = admin_repo.get_live_admin_profile(user_id)

    if not profile:
        elapsed = time.monotonic() - start
        time.sleep(max(0.0, _MIN_RESPONSE_SECONDS - elapsed))
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    user_role = profile.get("role", "")
    is_active = profile.get("is_active", False)

    if user_role != "admin" or not is_active:
        logger.warning("Admin verify failed: role=%s active=%s | ip=%s", user_role, is_active, client_ip)
        elapsed = time.monotonic() - start
        time.sleep(max(0.0, _MIN_RESPONSE_SECONDS - elapsed))
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    if hasattr(request.state, "actions"):
        request.state.actions.append("Admin role and active status verified successfully ✅")

    safe_profile = {
        "id": profile.get("id"), "email": profile.get("email"),
        "full_name": profile.get("full_name"), "role": profile.get("role"),
        "is_active": profile.get("is_active"), "created_at": profile.get("created_at"),
    }

    return {"verified": True, "profile": safe_profile, "timestamp": int(time.time())}


# ══════════════════════════════════════════════════════════════════════════════
#  ADMIN DASHBOARD STATS
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/stats", response_model=AdminStatsResponse)
@limiter.limit("10/minute")
def admin_stats(request: Request, current: dict[str, Any] = Depends(get_current_user)):
    user_id = _get_user_id(current)
    admin_repo = AdminRepository()
    
    if hasattr(request.state, "actions"):
        request.state.actions.append("Admin dashboard stats requested")
    
    profile = admin_repo.get_live_admin_profile(user_id)
    if not profile or profile.get("role") != "admin" or not profile.get("is_active"):
        raise HTTPException(403, "Access denied")

    if hasattr(request.state, "actions"):
        request.state.actions.append("Aggregating metrics via AdminRepository...")

    stats = admin_repo.get_dashboard_stats()

    if hasattr(request.state, "actions"):
        request.state.actions.append("Dashboard metrics aggregation complete")

    return {"verified": True, "stats": stats, "timestamp": int(time.time())}
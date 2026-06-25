"""
Admin Verification Router — Async Enterprise Grade
==================================================
Path: app/api/v1/routers/admin_verify.py

UI LOGGING UPGRADE: Explicit `request.state.actions.append(...)` hooks 
added to live admin checks & telemetry aggregation for PureWindowLogger.
"""
import logging
import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from slowapi import Limiter
from slowapi.util import get_remote_address

# 🔥 ARCHITECTURE IMPORTS: Added get_user_id_strict & require_admin
from app.core.dependencies import get_current_user, get_user_id_strict, require_admin
from app.repositories.admin_repo import AsyncAdminRepository
from app.api.schemas.admin_dto import AdminVerifyResponse, AdminStatsResponse

logger = logging.getLogger(__name__)
limiter = Limiter(key_func=get_remote_address)
router = APIRouter(prefix="/admin", tags=["Admin"])

_MIN_RESPONSE_SECONDS = 0.2  # Timing attack mitigation

# 🔥 DEPRECATED: Replaced by get_user_id_strict Dependency
# def _get_user_id(current_user: dict[str, Any]) -> str:
#     if "profile" in current_user and isinstance(current_user["profile"], dict) and "id" in current_user["profile"]:
#         return str(current_user["profile"]["id"])
#     if "id" in current_user: return str(current_user["id"])
#     if "sub" in current_user: return str(current_user["sub"])
#     raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User ID not found in session")

# ══════════════════════════════════════════════════════════════════════════════
#  VERIFY ENDPOINT
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/verify", response_model=AdminVerifyResponse, dependencies=[Depends(require_admin)])
@limiter.limit("30/minute")  
async def verify_admin(
    request: Request, 
    current: dict[str, Any] = Depends(get_current_user),
    user_id: str = Depends(get_user_id_strict) # 🔥 STRICT ABAC GUARD
):
    if hasattr(request.state, "actions"):
        request.state.actions.append(f"Initiating live God-Mode verification for: {user_id[:8]}...")

    start = time.monotonic()
    client_ip = get_remote_address(request)
    # user_id = _get_user_id(current) <-- REPLACED
    
    admin_repo = AsyncAdminRepository()
    profile = await admin_repo.get_live_admin_profile(user_id)

    if not profile:
        if hasattr(request.state, "actions"):
            request.state.actions.append("Verification rejected: No DB profile mapped to this UID")
        elapsed = time.monotonic() - start
        time.sleep(max(0.0, _MIN_RESPONSE_SECONDS - elapsed))
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    user_role = profile.get("role", "")
    is_active = profile.get("is_active", False)

    if user_role != "admin" or not is_active:
        if hasattr(request.state, "actions"):
            request.state.actions.append(f"Security Alert: Non-admin or inactive access attempt ({user_role})")
        logger.warning("Admin verify failed: role=%s active=%s | ip=%s", user_role, is_active, client_ip)
        elapsed = time.monotonic() - start
        time.sleep(max(0.0, _MIN_RESPONSE_SECONDS - elapsed))
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    if hasattr(request.state, "actions"):
        request.state.actions.append("Access Granted -> Verified as Active System Administrator")

    safe_profile = {
        "id": profile.get("id"), "email": profile.get("email"),
        "full_name": profile.get("full_name"), "role": profile.get("role"),
        "is_active": profile.get("is_active"), "created_at": profile.get("created_at"),
    }

    return {"verified": True, "profile": safe_profile, "timestamp": int(time.time())}

# ══════════════════════════════════════════════════════════════════════════════
#  ADMIN DASHBOARD STATS
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/stats", response_model=AdminStatsResponse, dependencies=[Depends(require_admin)])
@limiter.limit("10/minute")
async def admin_stats(
    request: Request, 
    current: dict[str, Any] = Depends(get_current_user),
    user_id: str = Depends(get_user_id_strict) # 🔥 STRICT ABAC GUARD
):
    if hasattr(request.state, "actions"):
        request.state.actions.append(f"Requesting system telemetry aggregation for: {user_id[:8]}...")

    # user_id = _get_user_id(current) <-- REPLACED
    admin_repo = AsyncAdminRepository()
    
    profile = await admin_repo.get_live_admin_profile(user_id)
    if not profile or profile.get("role") != "admin" or not profile.get("is_active"):
        if hasattr(request.state, "actions"):
            request.state.actions.append("Telemetry Denied -> Failed secondary role verification")
        raise HTTPException(403, "Access denied")

    if hasattr(request.state, "actions"):
        request.state.actions.append("Dispatching 5 concurrent async DB telemetry queries...")

    # This now runs all 5 queries concurrently in the background!
    stats = await admin_repo.get_dashboard_stats()

    if hasattr(request.state, "actions"):
        request.state.actions.append("Successfully aggregated & computed global dashboard metrics")

    return {"verified": True, "stats": stats, "timestamp": int(time.time())}
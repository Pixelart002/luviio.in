"""
Admin Router — Async Enterprise Grade
=====================================
Path: app/api/v1/routers/admin.py
"""
import logging
from typing import Any
from fastapi import APIRouter, Depends, Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.dependencies import get_current_user, get_user_id_strict, require_permission
from app.services.admin_service import AdminService # ✅ Corrected to match file name (adjust if using folder)
from app.api.schemas.admin_dto import AdminVerifyResponse, AdminStatsResponse
from app.permissions.admin import AdminPermissions

logger = logging.getLogger(__name__)
limiter = Limiter(key_func=get_remote_address)
router = APIRouter(prefix="/admin", tags=["Admin"])

@router.get("/verify", response_model=AdminVerifyResponse, dependencies=[Depends(require_permission(AdminPermissions.MANAGE_SETTINGS))])
@limiter.limit("30/minute")  
async def verify_admin(
    request: Request, 
    user_id: str = Depends(get_user_id_strict)
):
    if hasattr(request.state, "actions"):
        request.state.actions.append(f"Initiating live God-Mode verification for: {user_id[:8]}...")

    service = AdminService()
    result = await service.verify_admin_access(user_id)

    if hasattr(request.state, "actions"):
        request.state.actions.append("Access Granted -> Verified as Active System Administrator")

    return result


@router.get("/stats", response_model=AdminStatsResponse, dependencies=[Depends(require_permission(AdminPermissions.VIEW_ANALYTICS))])
@limiter.limit("10/minute")
async def admin_stats(
    request: Request, 
    user_id: str = Depends(get_user_id_strict)
):
    if hasattr(request.state, "actions"):
        request.state.actions.extend([
            f"Requesting system telemetry aggregation for: {user_id[:8]}...",
            "Dispatching concurrent async DB telemetry queries..."
        ])

    service = AdminService()
    result = await service.get_dashboard_metrics(user_id)

    if hasattr(request.state, "actions"):
        request.state.actions.append("Successfully aggregated & computed global dashboard metrics")

    return result
"""
Admin Router — Async Enterprise Grade
=====================================
Path: app/api/v1/routers/admin.py
"""
import logging
from fastapi import APIRouter, Depends, Request, status
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.dependencies import get_user_id_strict, require_permission
from app.services.admin.service import AdminService
from app.api.schemas.admin_dto import AdminVerifyResponse, AdminStatsResponse
from app.permissions.admin import AdminPermissions
from app.constants.messages import AdminMessages

logger = logging.getLogger(__name__)
limiter = Limiter(key_func=get_remote_address)
router = APIRouter(prefix="/admin", tags=["Admin"])

@router.get(
    "/verify", 
    response_model=AdminVerifyResponse, 
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_permission(AdminPermissions.MANAGE_SETTINGS))]
)
@limiter.limit("30/minute")  
async def verify_admin(
    request: Request, 
    user_id: str = Depends(get_user_id_strict)
):
    """
    Verifies God-Mode / Admin access by performing a real-time ABAC check against the database.
    Required PBAC Permission: admin.manage_settings
    """
    if hasattr(request.state, "actions"):
        request.state.actions.append(f"Initiating live verification for: {user_id[:8]}...")

    service = AdminService()
    result = await service.verify_admin_access(user_id)

    if hasattr(request.state, "actions"):
        request.state.actions.append(AdminMessages.VERIFIED_SUCCESS)

    return result


@router.get(
    "/stats", 
    response_model=AdminStatsResponse, 
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_permission(AdminPermissions.VIEW_ANALYTICS))]
)
@limiter.limit("10/minute")
async def admin_stats(
    request: Request, 
    user_id: str = Depends(get_user_id_strict)
):
    """
    Aggregates global system telemetry concurrently (Products, Orders, Revenue, Users).
    Required PBAC Permission: admin.view_analytics
    """
    if hasattr(request.state, "actions"):
        request.state.actions.extend([
            f"Requesting telemetry aggregation for: {user_id[:8]}...",
            "Dispatching concurrent async DB telemetry queries..."
        ])

    service = AdminService()
    result = await service.get_dashboard_metrics(user_id)

    if hasattr(request.state, "actions"):
        request.state.actions.append(AdminMessages.STATS_SUCCESS)

    return result
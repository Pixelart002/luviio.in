"""
Admin Router — Async Enterprise Grade
=====================================
Path: app/api/v1/routers/admin_verify.py
"""
import logging
from fastapi import APIRouter, Depends, Request, status
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.dependencies import get_user_id_strict, require_permission
from app.services.admin.service import AdminService
from app.permissions.admin import AdminPermissions
from app.constants.admin_messages import AdminMessages
from app.utils.response import success_response

logger = logging.getLogger(__name__)
limiter = Limiter(key_func=get_remote_address)
router = APIRouter(prefix="/admin", tags=["Admin"])

@router.get("/verify", dependencies=[Depends(require_permission(AdminPermissions.MANAGE_SETTINGS))], status_code=status.HTTP_200_OK)
@limiter.limit("30/minute")  
async def verify_admin(request: Request, user_id: str = Depends(get_user_id_strict)):
    if hasattr(request.state, "actions"):
        request.state.actions.append(f"Initiating live God-Mode verification for: {user_id[:8]}...")

    data = await AdminService().verify_admin_access(user_id)

    if hasattr(request.state, "actions"):
        request.state.actions.append("Access Granted -> Verified as Active System Administrator")

    return success_response(data=data, message=AdminMessages.VERIFIED)


@router.get("/stats", dependencies=[Depends(require_permission(AdminPermissions.VIEW_ANALYTICS))], status_code=status.HTTP_200_OK)
@limiter.limit("10/minute")
async def admin_stats(request: Request, user_id: str = Depends(get_user_id_strict)):
    if hasattr(request.state, "actions"):
        request.state.actions.extend([
            f"Requesting system telemetry aggregation for: {user_id[:8]}...",
            "Dispatching concurrent async DB telemetry queries..."
        ])

    data = await AdminService().get_dashboard_metrics(user_id)

    if hasattr(request.state, "actions"):
        request.state.actions.append("Successfully aggregated & computed global dashboard metrics")

    return success_response(data=data, message=AdminMessages.STATS_FETCHED)
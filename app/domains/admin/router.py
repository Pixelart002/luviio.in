"""Admin HTTP router — thin transport layer."""
import logging

from fastapi import APIRouter, Depends, Query, Request, status
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.constants.admin_messages import AdminMessages
from app.core.dependencies import get_user_id_strict, require_permission
from app.domains.admin.service import AdminService
from app.permissions.admin import AdminPermissions
from app.utils.response import success_response

logger = logging.getLogger(__name__)
limiter = Limiter(key_func=get_remote_address)
router = APIRouter(prefix="/admin", tags=["Admin"])


@router.get("/verify", dependencies=[Depends(require_permission(AdminPermissions.ACCESS_CONSOLE))], status_code=status.HTTP_200_OK)
@limiter.limit("30/minute")
async def verify_admin(request: Request, user_id: str = Depends(get_user_id_strict)):
    data = await AdminService().verify_admin_access(user_id)
    return success_response(data=data, message=AdminMessages.VERIFIED)


@router.get("/stats", dependencies=[Depends(require_permission(AdminPermissions.VIEW_ANALYTICS))], status_code=status.HTTP_200_OK)
@limiter.limit("10/minute")
async def admin_stats(request: Request, user_id: str = Depends(get_user_id_strict)):
    return success_response(data=await AdminService().get_dashboard_metrics(user_id), message=AdminMessages.STATS_FETCHED)


@router.get("/reports/summary", dependencies=[Depends(require_permission(AdminPermissions.VIEW_ANALYTICS))], status_code=status.HTTP_200_OK)
@limiter.limit("10/minute")
async def admin_reports(request: Request, user_id: str = Depends(get_user_id_strict)):
    return success_response(data=await AdminService().get_reports(user_id))


@router.get("/payments", dependencies=[Depends(require_permission(AdminPermissions.VIEW_ANALYTICS))], status_code=status.HTTP_200_OK)
@limiter.limit("20/minute")
async def admin_payments(request: Request, user_id: str = Depends(get_user_id_strict)):
    return success_response(data=await AdminService().get_payments(user_id))


@router.get("/audit", dependencies=[Depends(require_permission(AdminPermissions.VIEW_ANALYTICS))], status_code=status.HTTP_200_OK)
@limiter.limit("20/minute")
async def admin_audit(request: Request, limit: int = Query(200, ge=1, le=500), user_id: str = Depends(get_user_id_strict)):
    return success_response(data=await AdminService().get_audit_logs(user_id, limit))

"""Admin HTTP router — thin transport layer."""
import logging

from fastapi import APIRouter, Depends, Query, Request, status
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.constants.admin_messages import AdminMessages
from app.core.dependencies import get_user_id_strict, require_permission
from app.domains.admin.service import AdminService
from app.domains.payments.plugin_schemas import (
    MethodRegistrationRequest,
    MethodToggleRequest,
    ProviderRegistrationRequest,
    ProviderToggleRequest,
)
from app.integrations.payments.manager import PaymentPluginManager
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
async def admin_payments(
    request: Request,
    limit: int = Query(10, ge=1, le=50),
    offset: int = Query(0, ge=0),
    user_id: str = Depends(get_user_id_strict),
):
    return success_response(data=await AdminService().get_payments(user_id, limit=limit, offset=offset))


@router.get("/audit", dependencies=[Depends(require_permission(AdminPermissions.VIEW_ANALYTICS))], status_code=status.HTTP_200_OK)
@limiter.limit("20/minute")
async def admin_audit(request: Request, limit: int = Query(200, ge=1, le=500), user_id: str = Depends(get_user_id_strict)):
    return success_response(data=await AdminService().get_audit_logs(user_id, limit))


@router.get("/payment-plugins", dependencies=[Depends(require_permission(AdminPermissions.MANAGE_SETTINGS))])
@limiter.limit("30/minute")
async def list_payment_plugins(request: Request, user_id: str = Depends(get_user_id_strict)):
    return success_response(data=await PaymentPluginManager().list_plugins())


@router.get("/payment-plugins/methods", dependencies=[Depends(require_permission(AdminPermissions.MANAGE_SETTINGS))])
@limiter.limit("30/minute")
async def list_payment_methods(
    request: Request,
    provider_key: str | None = Query(None, min_length=2, max_length=64),
    user_id: str = Depends(get_user_id_strict),
):
    return success_response(data=await PaymentPluginManager().list_methods(provider_key))


@router.patch("/payment-plugins/{provider_key}", dependencies=[Depends(require_permission(AdminPermissions.MANAGE_SETTINGS))])
@limiter.limit("20/minute")
async def toggle_payment_plugin(request: Request, provider_key: str, payload: ProviderToggleRequest, user_id: str = Depends(get_user_id_strict)):
    data = await PaymentPluginManager().set_provider_enabled(provider_key, payload.enabled)
    return success_response(data=data)


@router.patch("/payment-plugins/{provider_key}/methods/{method_key}", dependencies=[Depends(require_permission(AdminPermissions.MANAGE_SETTINGS))])
@limiter.limit("20/minute")
async def toggle_payment_method(request: Request, provider_key: str, method_key: str, payload: MethodToggleRequest, user_id: str = Depends(get_user_id_strict)):
    data = await PaymentPluginManager().set_method_enabled(provider_key, method_key, payload.enabled)
    return success_response(data=data)


@router.post("/payment-plugins", dependencies=[Depends(require_permission(AdminPermissions.MANAGE_SETTINGS))])
@limiter.limit("10/minute")
async def register_payment_plugin(request: Request, payload: ProviderRegistrationRequest, user_id: str = Depends(get_user_id_strict)):
    data = await PaymentPluginManager().register_installed_provider(payload.provider_key, payload.display_name, payload.capabilities, payload.priority)
    return success_response(data=data, message="Payment provider registered. It remains disabled until explicitly enabled.")


@router.post("/payment-plugins/{provider_key}/methods", dependencies=[Depends(require_permission(AdminPermissions.MANAGE_SETTINGS))])
@limiter.limit("10/minute")
async def register_payment_method(request: Request, provider_key: str, payload: MethodRegistrationRequest, user_id: str = Depends(get_user_id_strict)):
    data = await PaymentPluginManager().register_method(provider_key, payload.method_key, payload.display_name, payload.priority, payload.metadata)
    return success_response(data=data, message="Payment method registered. It remains disabled until explicitly enabled.")


@router.delete("/payment-plugins/{provider_key}", dependencies=[Depends(require_permission(AdminPermissions.MANAGE_SETTINGS))])
@limiter.limit("10/minute")
async def deactivate_payment_plugin(request: Request, provider_key: str, user_id: str = Depends(get_user_id_strict)):
    data = await PaymentPluginManager().deactivate_provider(provider_key)
    return success_response(data=data, message="Payment provider deactivated; historical payment records are preserved.")

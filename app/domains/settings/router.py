"""Settings HTTP router owned by the Settings domain."""
import logging
from typing import Any, Dict, Optional
from fastapi import APIRouter, Depends, Query, Request, status
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.dependencies import get_current_user, get_user_id_strict, require_permission
from app.permissions.settings import SettingsPermissions
from app.domains.settings.admin_service import AdminSettingsService
from app.domains.settings.schemas import SettingUpdate
from app.constants.settings_messages import SettingsMessages
from app.utils.response import success_response
from app.core.maintenance import invalidate_maintenance_cache

logger = logging.getLogger(__name__)
limiter = Limiter(key_func=get_remote_address)
router = APIRouter(prefix="/settings", tags=["System Settings"])


@router.get("/", status_code=status.HTTP_200_OK, dependencies=[Depends(require_permission(SettingsPermissions.READ))])
async def list_settings(
    request: Request,
    category: Optional[str] = Query(None, description="Filter by category"),
    force_refresh: bool = Query(False, description="Bypass in-memory cache"),
):
    if hasattr(request.state, "actions"):
        request.state.actions.append(
            f"Admin querying system settings registry (Category: {category or 'ALL'})"
        )
    items = await AdminSettingsService().get_all(category=category, force_refresh=force_refresh)
    return success_response(
        data={"items": items, "total": len(items)}, message=SettingsMessages.FETCHED
    )


@router.patch(
    "/{key}",
    status_code=status.HTTP_200_OK,
    response_model=Dict[str, Any],
    dependencies=[Depends(require_permission(SettingsPermissions.UPDATE))],
)
@limiter.limit("20/minute")
async def update_setting(
    request: Request,
    key: str,
    payload: SettingUpdate,
    user_id: str = Depends(get_user_id_strict),
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    if hasattr(request.state, "actions"):
        request.state.actions.append(
            f"Initiating setting mutation -> Key: '{key}' | Reason: {payload.reason or 'None'}"
        )

    user_role = current_user.get("role") or current_user.get("profile", {}).get("role", "admin")
    updated = await AdminSettingsService().update_core_setting(
        key=key,
        new_value=payload.value,
        admin_id=user_id,
        role=user_role,
        reason=payload.reason or "Admin UI override",
    )
    invalidate_maintenance_cache()

    if hasattr(request.state, "actions"):
        request.state.actions.append("Setting mutated successfully & global TTL cache purged")
    return success_response(data=updated, message=SettingsMessages.UPDATED)


@router.post(
    "/{key}/reset",
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_permission(SettingsPermissions.RESET))],
)
@limiter.limit("10/minute")
async def reset_setting(
    request: Request,
    key: str,
    user_id: str = Depends(get_user_id_strict),
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    if hasattr(request.state, "actions"):
        request.state.actions.append(f"Admin restoring setting '{key}' to factory default...")

    user_role = current_user.get("role") or current_user.get("profile", {}).get("role", "admin")
    restored = await AdminSettingsService().reset_to_default(
        key=key,
        admin_id=user_id,
        role=user_role,
    )
    invalidate_maintenance_cache()

    if hasattr(request.state, "actions"):
        request.state.actions.append("Setting restored to default & cache invalidated")
    return success_response(data=restored, message=SettingsMessages.RESET)

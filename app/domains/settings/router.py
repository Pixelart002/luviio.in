"""Settings HTTP router owned by the Settings domain."""
import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, status
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.constants.settings_messages import SettingsMessages
from app.core.dependencies import get_current_user, get_user_id_strict, require_permission
from app.core.maintenance import invalidate_maintenance_cache
from app.domains.settings.admin_service import AdminSettingsService
from app.domains.settings.schemas import SettingUpdate
from app.permissions.settings import SettingsPermissions
from app.utils.business_asset import delete_business_asset, upload_business_asset
from app.utils.response import success_response

logger = logging.getLogger(__name__)
limiter = Limiter(key_func=get_remote_address)
router = APIRouter(prefix="/settings", tags=["System Settings"])


@router.get("/", status_code=status.HTTP_200_OK, dependencies=[Depends(require_permission(SettingsPermissions.READ))])
async def list_settings(request: Request, category: Optional[str] = Query(None, description="Filter by category"), force_refresh: bool = Query(False, description="Bypass in-memory cache")):
    if hasattr(request.state, "actions"):
        request.state.actions.append(f"Admin querying system settings registry (Category: {category or 'ALL'})")
    items = await AdminSettingsService().get_all(category=category, force_refresh=force_refresh)
    return success_response(data={"items": items, "total": len(items)}, message=SettingsMessages.FETCHED)


@router.patch("/{key}", status_code=status.HTTP_200_OK, response_model=Dict[str, Any], dependencies=[Depends(require_permission(SettingsPermissions.UPDATE))])
@limiter.limit("20/minute")
async def update_setting(request: Request, key: str, payload: SettingUpdate, user_id: str = Depends(get_user_id_strict), current_user: Dict[str, Any] = Depends(get_current_user)):
    if hasattr(request.state, "actions"):
        request.state.actions.append(f"Initiating setting mutation -> Key: '{key}' | Reason: {payload.reason or 'None'}")
    user_role = current_user.get("role") or current_user.get("profile", {}).get("role", "admin")
    updated = await AdminSettingsService().update_core_setting(key=key, new_value=payload.value, admin_id=user_id, role=user_role, reason=payload.reason or "Admin UI override")
    invalidate_maintenance_cache()
    if hasattr(request.state, "actions"):
        request.state.actions.append("Setting mutated successfully & global TTL cache purged")
    return success_response(data=updated, message=SettingsMessages.UPDATED)


@router.post("/business-profile/assets/{asset_type}", status_code=status.HTTP_200_OK, dependencies=[Depends(require_permission(SettingsPermissions.UPDATE))])
@limiter.limit("10/minute")
async def upload_business_profile_asset(request: Request, asset_type: str, file: UploadFile = File(...), user_id: str = Depends(get_user_id_strict), current_user: Dict[str, Any] = Depends(get_current_user)):
    if asset_type not in {"logo", "signature"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported business asset type.")
    data = await file.read()
    service = AdminSettingsService()
    key = "business_logo_url" if asset_type == "logo" else "business_signature_url"
    existing = await service.get_setting(key)
    old_url = existing.get("value")
    try:
        url = upload_business_asset(data, file.filename or "business-asset", asset_type)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc

    role = current_user.get("role") or current_user.get("profile", {}).get("role", "admin")
    try:
        updated = await service.update_core_setting(key=key, new_value=url, admin_id=user_id, role=role, reason=f"Uploaded business {asset_type} from Business Profile")
    except Exception:
        # Storage upload and Postgres settings mutation are separate systems.
        # If the DB write fails, remove the just-created object immediately.
        delete_business_asset(url)
        raise

    if old_url and old_url != url and not delete_business_asset(old_url):
        logger.warning("Superseded business asset remains | type=%s", asset_type)
    invalidate_maintenance_cache()
    return success_response(data={"asset_type": asset_type, "url": url, "setting": updated}, message=f"Business {asset_type} uploaded.")


@router.post("/{key}/reset", status_code=status.HTTP_200_OK, dependencies=[Depends(require_permission(SettingsPermissions.RESET))])
@limiter.limit("10/minute")
async def reset_setting(request: Request, key: str, user_id: str = Depends(get_user_id_strict), current_user: Dict[str, Any] = Depends(get_current_user)):
    if hasattr(request.state, "actions"):
        request.state.actions.append(f"Admin restoring setting '{key}' to factory default...")
    user_role = current_user.get("role") or current_user.get("profile", {}).get("role", "admin")
    service = AdminSettingsService()
    existing = await service.get_setting(key)
    old_value = existing.get("value")
    restored = await service.reset_to_default(key=key, admin_id=user_id, role=user_role)
    if key in {"business_logo_url", "business_signature_url"} and old_value:
        if not delete_business_asset(old_value):
            logger.warning("Reset left business asset for cleanup | key=%s", key)
    invalidate_maintenance_cache()
    if hasattr(request.state, "actions"):
        request.state.actions.append("Setting restored to default & cache invalidated")
    return success_response(data=restored, message=SettingsMessages.RESET)

"""
RBAC Domain — Router
====================
Path: app/domains/rbac/router.py

Admin surface for:
  * role-level permission toggles              -> /api/v1/rbac/permissions
  * user-level action control (the "big-software" per-user disable)
                                               -> /api/v1/rbac/users/{user_id}/actions
"""
import logging

from fastapi import APIRouter, Depends, Request, status, HTTPException

from app.core.dependencies import get_current_user, get_user_id_strict, require_permission
from app.domains.rbac.service import RolePermissionService, UserActionControlService
from app.domains.rbac.policy import RbacPolicy
from app.domains.rbac.schemas import RolePermissionToggle, UserActionControlUpdate
from app.constants.rbac_messages import RbacMessages, USER_ACTIONS
from app.permissions.admin import AdminPermissions
from app.utils.response import success_response

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/rbac", tags=["RBAC & Permissions"])

_permission_svc = RolePermissionService()
_action_svc = UserActionControlService()


# ── Permission catalogue (used by the admin UI to render every toggle) ────────
@router.get("/permissions/catalogue",
            dependencies=[Depends(require_permission(AdminPermissions.MANAGE_ROLES))],
            status_code=status.HTTP_200_OK)
async def permission_catalogue():
    return success_response(data=await _permission_svc.catalogue(), message=RbacMessages.CATALOGUE)


# ── Role-level toggles ─────────────────────────────────────────────────────────
@router.get("/permissions",
            dependencies=[Depends(require_permission(AdminPermissions.MANAGE_ROLES))],
            status_code=status.HTTP_200_OK)
async def list_role_permissions():
    """Static defaults + effective (post-override) matrix + explicit overrides."""
    data = {
        "effective": await _permission_svc.effective_matrix(),
        "overrides": await _permission_svc.list_overrides(),
    }
    return success_response(data=data, message=RbacMessages.OVERRIDES_FETCHED)


@router.post("/permissions/toggle",
             status_code=status.HTTP_200_OK)
async def toggle_role_permission(
    payload: RolePermissionToggle,
    current_user=Depends(require_permission(AdminPermissions.MANAGE_ROLES)),
):
    actor_role = (current_user.get("profile") or {}).get("role", "admin")
    RbacPolicy.assert_role_manageable(actor_role, payload.role)
    result = await _permission_svc.set_override(payload.role, payload.permission, payload.enabled)
    return success_response(data=result, message=RbacMessages.OVERRIDE_UPDATED)


@router.delete("/permissions/{role}/{permission}",
               dependencies=[Depends(require_permission(AdminPermissions.MANAGE_ROLES))],
               status_code=status.HTTP_200_OK)
async def remove_role_permission(role: str, permission: str):
    result = await _permission_svc.remove_override(role, permission)
    return success_response(data=result, message=RbacMessages.OVERRIDE_DELETED)


# ── User-level action controls ──────────────────────────────────────────────────
@router.get("/users/{user_id}/actions",
            dependencies=[Depends(require_permission(AdminPermissions.MANAGE_ROLES))],
            status_code=status.HTTP_200_OK)
async def list_user_controls(user_id: str):
    data = {
        "user_id": user_id,
        "controls": await _action_svc.list_for_user(user_id),
        "all_actions": USER_ACTIONS,
    }
    return success_response(data=data, message=RbacMessages.USER_CONTROLS_FETCHED)


@router.post("/users/{user_id}/actions",
             status_code=status.HTTP_200_OK,
             dependencies=[Depends(require_permission(AdminPermissions.MANAGE_ROLES))])
async def set_user_control(user_id: str, payload: UserActionControlUpdate,
                           actor_id: str = Depends(get_user_id_strict)):
    RbacPolicy.assert_not_self_lockout(actor_id, user_id, payload.action, payload.enabled)
    result = await _action_svc.set_for_user(
        user_id, payload.action, payload.enabled, actor_id=actor_id, reason=payload.reason
    )
    return success_response(data=result, message=RbacMessages.USER_CONTROL_UPDATED)


@router.delete("/users/{user_id}/actions/{action}",
               status_code=status.HTTP_200_OK,
               dependencies=[Depends(require_permission(AdminPermissions.MANAGE_ROLES))])
async def remove_user_control(user_id: str, action: str):
    result = await _action_svc.remove_for_user(user_id, action)
    return success_response(data=result, message=RbacMessages.USER_CONTROL_DELETED)


# ── Live enforcement proxies (handy for the admin UI / debugging) ──────────────
@router.get("/users/{user_id}/actions/{action}/enabled",
            status_code=status.HTTP_200_OK,
            dependencies=[Depends(require_permission(AdminPermissions.MANAGE_ROLES))])
async def check_user_action(user_id: str, action: str):
    from app.permissions.action_control import is_action_enabled
    enabled = await is_action_enabled(user_id, action)
    return success_response(data={"user_id": user_id, "action": action, "enabled": enabled})

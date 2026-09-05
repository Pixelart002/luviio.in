from app.enums.roles import UserRole
from app.permissions.products import ProductPermissions as PP
from app.permissions.orders import OrderPermissions as OP
from app.permissions.users import UserPermissions as UP
from app.permissions.payments import PaymentPermissions as PayP
from app.permissions.admin import AdminPermissions as AP
from app.permissions.settings import SettingsPermissions as SP
from app.permissions.coupons import CouponPermissions as CP
from app.permissions.shipping import ShippingPermissions as ShipP
from app.permissions.subscriptions import SubscriptionPermissions as SubP

# Master Role-to-Permission Mapping
# ==================================
# This is the STATIC default matrix. At runtime, `app.permissions.overrides`
# layers an optional `role_permissions` table on top of it so admins can
# enable/disable individual permissions per role without a redeploy.
# Effective permission = static default, adjusted by DB overrides.
ROLE_PERMISSIONS = {
    UserRole.SUPER_ADMIN: ["*"],  # God Mode — absolute, can never be narrowed at runtime.

    UserRole.ADMIN: [
        PP.CREATE, PP.READ, PP.UPDATE, PP.DELETE,
        OP.READ, OP.UPDATE, OP.CANCEL, OP.REFUND,
        UP.READ, UP.UPDATE, UP.DELETE,
        PayP.READ, PayP.PROCESS, PayP.REFUND,
        AP.VIEW_ANALYTICS, AP.MANAGE_SETTINGS,
        # 🔥 FIX: these were never granted to any role except super_admin
        # (via the "*" wildcard) — every /settings/* endpoint 403'd for
        # admins too, even though AP.MANAGE_SETTINGS above already signaled
        # admin was meant to manage settings. MANAGE_LOCKED intentionally
        # excluded — that stays super_admin-only per SettingsPolicy.
        SP.READ, SP.UPDATE, SP.RESET,
        # New commerce domains — full staff control
        CP.CREATE, CP.READ, CP.UPDATE, CP.DELETE, CP.APPLY,
        ShipP.READ, ShipP.UPDATE, ShipP.DELETE,
        SubP.READ_PLANS, SubP.READ_MINE, SubP.MANAGE, SubP.MANAGE_USERS,
        # NOTE: AP.MANAGE_ROLES stays super_admin-only (role assignment is God-Mode).
    ],

    UserRole.MANAGER: [
        PP.CREATE, PP.READ, PP.UPDATE,
        OP.READ, OP.UPDATE, OP.CANCEL,
        UP.READ,
        PayP.READ,
        AP.VIEW_ANALYTICS,
        # Day-to-day commerce operations, no destructive/financial rights
        CP.CREATE, CP.READ, CP.UPDATE,
        ShipP.READ, ShipP.UPDATE,
        SubP.READ_PLANS, SubP.MANAGE_USERS,
        # NOTE: SettingsPermissions intentionally NOT granted here yet.
        # ManagerSettingsService exists (operational/ui_ux categories only)
        # but no router endpoint calls it yet — /settings/ is still wired
        # to AdminSettingsService only, which returns ALL settings
        # unfiltered. Granting SP.READ here would let managers see
        # financial/locked settings via the list endpoint. Add a
        # manager-scoped router route first, then grant permissions here.
    ],

    UserRole.SUPPORT: [
        PP.READ,
        OP.READ, OP.UPDATE,
        UP.READ,
        PayP.READ,
        CP.READ, CP.APPLY,
        ShipP.READ,
        SubP.READ_PLANS, SubP.READ_MINE,
    ],

    # Customers use ABAC (Resource Ownership) for their own data, but the
    # customer-facing commerce endpoints below are guarded by PBAC.
    UserRole.CUSTOMER: [
        CP.APPLY,
        SubP.READ_PLANS, SubP.SUBSCRIBE, SubP.READ_MINE,
    ],
}


def get_static_role_permissions(role) -> set[str]:
    """
    Returns the static default permission set for a role (handles both the
    UserRole enum and its string value).
    """
    key = role
    if isinstance(role, str):
        try:
            key = UserRole(role)
        except ValueError:
            key = role
    return set(ROLE_PERMISSIONS.get(key, []))

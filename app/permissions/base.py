from app.enums.roles import UserRole
from app.permissions.products import ProductPermissions as PP
from app.permissions.orders import OrderPermissions as OP
from app.permissions.users import UserPermissions as UP
from app.permissions.payments import PaymentPermissions as PayP
from app.permissions.admin import AdminPermissions as AP
from app.permissions.settings import SettingsPermissions as SP

# Master Role-to-Permission Mapping
ROLE_PERMISSIONS = {
    UserRole.SUPER_ADMIN: ["*"],  # God Mode
    
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
    ],
    
    UserRole.MANAGER: [
        PP.CREATE, PP.READ, PP.UPDATE,
        OP.READ, OP.UPDATE, OP.CANCEL,
        UP.READ,
        PayP.READ,
        AP.VIEW_ANALYTICS
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
        PayP.READ
    ],
    
    UserRole.CUSTOMER: [] # Customers use ABAC (Resource Ownership), not PBAC.
}
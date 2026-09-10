from app.enums.roles import UserRole
from app.permissions.admin import AdminPermissions as AP
from app.permissions.coupons import CouponPermissions as CP
from app.permissions.orders import OrderPermissions as OP
from app.permissions.payments import PaymentPermissions as PayP
from app.permissions.products import ProductPermissions as PP
from app.permissions.reviews import ReviewPermissions as RP
from app.permissions.settings import SettingsPermissions as SP
from app.permissions.shipping import ShippingPermissions as ShipP
from app.permissions.subscriptions import SubscriptionPermissions as SubP
from app.permissions.users import UserPermissions as UP

# Master Role-to-Permission Mapping. DB role_permissions is an override layer.
ROLE_PERMISSIONS = {
    UserRole.SUPER_ADMIN: ["*"],
    UserRole.ADMIN: [
        AP.ACCESS_CONSOLE,
        PP.CREATE, PP.READ, PP.UPDATE, PP.DELETE,
        OP.READ, OP.UPDATE, OP.CANCEL, OP.REFUND,
        UP.READ, UP.UPDATE, UP.DELETE,
        PayP.READ, PayP.PROCESS, PayP.REFUND,
        AP.VIEW_ANALYTICS, AP.MANAGE_SETTINGS, AP.MANAGE_ROLES,
        SP.READ, SP.UPDATE, SP.RESET,
        CP.CREATE, CP.READ, CP.UPDATE, CP.DELETE, CP.APPLY,
        ShipP.READ, ShipP.UPDATE, ShipP.DELETE,
        SubP.READ_PLANS, SubP.READ_MINE, SubP.MANAGE, SubP.MANAGE_USERS,
        RP.MODERATE,
    ],
    UserRole.MANAGER: [
        AP.ACCESS_CONSOLE,
        PP.CREATE, PP.READ, PP.UPDATE,
        OP.READ, OP.UPDATE, OP.CANCEL,
        UP.READ,
        PayP.READ,
        AP.VIEW_ANALYTICS,
        CP.CREATE, CP.READ, CP.UPDATE,
        ShipP.READ, ShipP.UPDATE,
        SubP.READ_PLANS, SubP.MANAGE_USERS,
        RP.MODERATE,
    ],
    UserRole.SUPPORT: [
        AP.ACCESS_CONSOLE,
        PP.READ,
        OP.READ, OP.UPDATE,
        UP.READ,
        PayP.READ,
        CP.READ, CP.APPLY,
        ShipP.READ,
        SubP.READ_PLANS, SubP.READ_MINE,
    ],
    UserRole.CUSTOMER: [
        CP.APPLY,
        SubP.READ_PLANS, SubP.SUBSCRIBE, SubP.READ_MINE,
    ],
}


def get_static_role_permissions(role) -> set[str]:
    key = role
    if isinstance(role, str):
        try:
            key = UserRole(role)
        except ValueError:
            key = role
    return set(ROLE_PERMISSIONS.get(key, []))

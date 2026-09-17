from app.enums.roles import UserRole
from app.permissions.admin import AdminPermissions as AP
from app.permissions.cart import CartPermissions as CartP
from app.permissions.coupons import CouponPermissions as CP
from app.permissions.orders import OrderPermissions as OP
from app.permissions.payments import PaymentPermissions as PayP
from app.permissions.products import ProductPermissions as PP
from app.permissions.reviews import ReviewPermissions as RP
from app.permissions.settings import SettingsPermissions as SP
from app.permissions.shipping import ShippingPermissions as ShipP
from app.permissions.subscriptions import SubscriptionPermissions as SubP
from app.permissions.users import UserPermissions as UP

# Inventory uses canonical permission strings because its endpoints are domain-specific.
INVENTORY_READ = "inventory.read"
INVENTORY_ADJUST = "inventory.adjust"
INVENTORY_RECEIVE = "inventory.receive"
INVENTORY_RETURN = "inventory.return"
INVENTORY_DAMAGE = "inventory.damage"
INVENTORY_WASTAGE = "inventory.wastage"
INVENTORY_RECONCILE = "inventory.reconcile"
INVENTORY_HISTORY_READ = "inventory.history.read"
INVENTORY_LOW_STOCK_READ = "inventory.low_stock.read"
INVENTORY_RESERVATION_RELEASE = "inventory.reservation.release"

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
        CartP.VIEW_ABANDONED, CartP.MANAGE_REMINDERS,
        ShipP.READ, ShipP.UPDATE, ShipP.DELETE,
        SubP.READ_PLANS, SubP.READ_MINE, SubP.MANAGE, SubP.MANAGE_USERS,
        RP.MODERATE,
        INVENTORY_READ, INVENTORY_ADJUST, INVENTORY_RECEIVE, INVENTORY_RETURN,
        INVENTORY_DAMAGE, INVENTORY_WASTAGE, INVENTORY_RECONCILE,
        INVENTORY_HISTORY_READ, INVENTORY_LOW_STOCK_READ, INVENTORY_RESERVATION_RELEASE,
    ],
    UserRole.MANAGER: [
        AP.ACCESS_CONSOLE,
        PP.CREATE, PP.READ, PP.UPDATE,
        OP.READ, OP.UPDATE, OP.CANCEL,
        UP.READ,
        PayP.READ,
        AP.VIEW_ANALYTICS,
        CP.CREATE, CP.READ, CP.UPDATE,
        CartP.VIEW_ABANDONED, CartP.MANAGE_REMINDERS,
        ShipP.READ, ShipP.UPDATE,
        SubP.READ_PLANS, SubP.MANAGE_USERS,
        RP.MODERATE,
        INVENTORY_READ, INVENTORY_ADJUST, INVENTORY_RECEIVE, INVENTORY_RETURN,
        INVENTORY_DAMAGE, INVENTORY_WASTAGE, INVENTORY_RECONCILE,
        INVENTORY_HISTORY_READ, INVENTORY_LOW_STOCK_READ, INVENTORY_RESERVATION_RELEASE,
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
        INVENTORY_READ, INVENTORY_HISTORY_READ, INVENTORY_LOW_STOCK_READ,
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

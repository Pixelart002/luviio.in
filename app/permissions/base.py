from app.enums.roles import UserRole
from app.permissions.products import ProductPermissions as PP
from app.permissions.orders import OrderPermissions as OP
from app.permissions.users import UserPermissions as UP
from app.permissions.payments import PaymentPermissions as PayP
from app.permissions.admin import AdminPermissions as AP

# Master Role-to-Permission Mapping
ROLE_PERMISSIONS = {
    UserRole.SUPER_ADMIN: ["*"],  # God Mode
    
    UserRole.ADMIN: [
        PP.CREATE, PP.READ, PP.UPDATE, PP.DELETE,
        OP.READ, OP.UPDATE, OP.CANCEL, OP.REFUND,
        UP.READ, UP.UPDATE, UP.DELETE,
        PayP.READ, PayP.PROCESS, PayP.REFUND,
        AP.VIEW_ANALYTICS, AP.MANAGE_SETTINGS
    ],
    
    UserRole.MANAGER: [
        PP.CREATE, PP.READ, PP.UPDATE,
        OP.READ, OP.UPDATE, OP.CANCEL,
        UP.READ,
        PayP.READ,
        AP.VIEW_ANALYTICS
    ],
    
    UserRole.SUPPORT: [
        PP.READ,
        OP.READ, OP.UPDATE,
        UP.READ,
        PayP.READ
    ],
    
    UserRole.CUSTOMER: [] # Customers use ABAC (Resource Ownership), not PBAC.
}
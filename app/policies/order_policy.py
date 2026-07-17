from app.enums.roles import UserRole
from app.enums.order_status import OrderStatus
from app.core.exceptions import UnauthorizedAction, LuviioException

class OrderPolicy:
    
    @staticmethod
    def can_cancel_order(user_role: str, user_id: str, order_customer_id: str, current_status: str) -> bool:
        """
        Policy: Can this specific user cancel this specific order right now?
        """
        # 1. Status Check
        if current_status not in [OrderStatus.PENDING, OrderStatus.PAID]:
            raise LuviioException("Order cannot be cancelled in its current state.", code="INVALID_STATE", status_code=400)
            
        # 2. Authorization Check
        if user_role in [UserRole.SUPER_ADMIN, UserRole.ADMIN, UserRole.MANAGER]:
            return True
            
        if user_role == UserRole.CUSTOMER and user_id == order_customer_id:
            return True
            
        raise UnauthorizedAction("You are not allowed to cancel this order.")
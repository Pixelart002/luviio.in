from app.enums.roles import UserRole
from app.core.exceptions import UnauthorizedAction

class ProductPolicy:
    
    @staticmethod
    def can_modify_inventory(user_role: str) -> bool:
        """
        Policy: Only high-tier roles can modify physical inventory (stock).
        """
        if user_role in [UserRole.SUPER_ADMIN, UserRole.ADMIN, UserRole.MANAGER]:
            return True
            
        raise UnauthorizedAction("Inventory modification requires Manager privileges or higher.")
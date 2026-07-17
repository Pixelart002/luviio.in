import logging
from typing import Any, Dict, Tuple, List

from app.repositories.user_repo import AsyncUserRepository
from app.core.exceptions import LuviioException, ResourceNotFound, UnauthorizedAction
from app.enums.roles import UserRole

logger = logging.getLogger(__name__)
MAX_ADDRESSES_PER_USER = 10

class UserService:
    def __init__(self):
        self.repo = AsyncUserRepository()

    async def update_profile(self, user_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        if not data: return {}
        try:
            return await self.repo.update_profile(user_id, data)
        except Exception:
            raise LuviioException("Failed to update profile", "DB_ERROR", 500)

    async def get_addresses(self, user_id: str) -> List[Dict[str, Any]]:
        try:
            return await self.repo.get_user_addresses(user_id, MAX_ADDRESSES_PER_USER)
        except Exception:
            raise LuviioException("Failed to fetch addresses", "DB_ERROR", 500)

    async def add_address(self, user_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        try:
            current_count = await self.repo.count_user_addresses(user_id)
        except Exception:
            raise LuviioException("Failed to verify address limit", "DB_ERROR", 500)

        if current_count >= MAX_ADDRESSES_PER_USER:
            raise LuviioException(f"Maximum {MAX_ADDRESSES_PER_USER} addresses allowed.", "LIMIT_EXCEEDED", 400)

        should_be_default = payload.get("is_default", False) or current_count == 0

        if should_be_default:
            try: await self.repo.unset_default_address(user_id)
            except Exception: pass

        payload.update({"user_id": user_id, "is_default": should_be_default})
        
        try:
            res = await self.repo.create_address(payload)
            if not res: raise Exception()
            return res
        except Exception:
            raise LuviioException("Failed to add address", "DB_ERROR", 500)

    async def delete_address(self, user_id: str, address_id: str) -> None:
        existing = await self.repo.get_address(address_id, user_id)
        if not existing:
            raise ResourceNotFound("Address")
            
        was_default = existing.get("is_default", False)

        try:
            if await self.repo.is_address_in_active_order(address_id):
                raise LuviioException("Cannot delete — this address is used in an active order.", "ADDRESS_LOCKED", 409)
        except LuviioException: raise
        except Exception: pass

        try: 
            await self.repo.delete_address(address_id)
        except Exception: 
            raise LuviioException("Failed to delete address", "DB_ERROR", 500)

        if was_default:
            try: await self.repo.set_new_default_address(user_id)
            except Exception: pass

    async def get_users_paginated(self, page: int, page_size: int, search: str = None, role_filter: str = None) -> Tuple[List[Dict[str, Any]], int]:
        try:
            return await self.repo.get_users_paginated(page, page_size, search, role_filter)
        except Exception:
            raise LuviioException("Failed to fetch users", "DB_ERROR", 500)

    async def admin_update_user(self, admin_id: str, target_user_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        if target_user_id == admin_id:
            if payload.get("role") and payload.get("role") != UserRole.ADMIN:
                raise UnauthorizedAction("You cannot change your own role")
            if payload.get("is_active") is False:
                raise UnauthorizedAction("You cannot deactivate your own account")

        if not payload: raise LuviioException("No fields to update", "INVALID_PAYLOAD", 400)

        existing = await self.repo.get_user_by_id(target_user_id)
        if not existing: raise ResourceNotFound("User")

        try:
            return await self.repo.update_profile(target_user_id, payload)
        except Exception:
            raise LuviioException("Failed to update user", "DB_ERROR", 500)

    async def get_user_detail(self, target_user_id: str) -> Dict[str, Any]:
        user = await self.repo.get_user_by_id(target_user_id)
        if not user: raise ResourceNotFound("User")
        
        try: total_orders = await self.repo.count_user_orders(target_user_id)
        except Exception: total_orders = 0
        
        user["total_orders"] = total_orders
        return user
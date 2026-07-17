"""
User Service — Enterprise Profile & Identity Management
=====================================================
Path: app/services/user_service.py
"""
import logging
from typing import Any, Dict, Tuple, List
from fastapi import HTTPException, status

from app.repositories.user_repo import AsyncUserRepository
from app.permissions.policies.user_policies import UserPolicy
from app.constants.user_messages import UserSecurityMessages

logger = logging.getLogger(__name__)
MAX_ADDRESSES_PER_USER = 10

class UserService:
    def __init__(self):
        self.repo = AsyncUserRepository()

    async def update_profile(self, user_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        if not data: 
            return {}
        try:
            return await self.repo.update_profile(user_id, data)
        except Exception as e:
            logger.error("Profile update failed: %s", e)
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=UserSecurityMessages.DB_OPERATION_FAILED)

    async def get_addresses(self, user_id: str) -> List[Dict[str, Any]]:
        return await self.repo.get_user_addresses(user_id, MAX_ADDRESSES_PER_USER)

    async def add_address(self, user_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        current_count = await self.repo.count_user_addresses(user_id)
        
        # Enforce ABAC Limit Policy
        UserPolicy.assert_address_limit(current_count, max_allowed=MAX_ADDRESSES_PER_USER)

        should_be_default = payload.get("is_default", False) or current_count == 0

        if should_be_default:
            try: 
                await self.repo.unset_default_address(user_id)
            except Exception as e: 
                logger.warning("Non-fatal error unsetting default address: %s", e)

        payload.update({"user_id": user_id, "is_default": should_be_default})
        
        res = await self.repo.create_address(payload)
        if not res: 
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=UserSecurityMessages.DB_OPERATION_FAILED)
        return res

    async def delete_address(self, user_id: str, address_id: str) -> None:
        existing = await self.repo.get_address(address_id, user_id)
        if not existing:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=UserSecurityMessages.ADDRESS_NOT_FOUND)
            
        was_default = existing.get("is_default", False)

        is_locked = await self.repo.is_address_in_active_order(address_id)
        
        # Enforce ABAC Address Lock Policy
        UserPolicy.assert_address_not_locked(is_locked)

        await self.repo.delete_address(address_id)

        if was_default:
            try: 
                await self.repo.set_new_default_address(user_id)
            except Exception as e: 
                logger.warning("Non-fatal error setting new default address: %s", e)

    async def get_users_paginated(self, page: int, page_size: int, search: str = None, role_filter: str = None) -> Tuple[List[Dict[str, Any]], int]:
        return await self.repo.get_users_paginated(page, page_size, search, role_filter)

    async def admin_update_user(self, admin_id: str, target_user_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        if not payload: 
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=UserSecurityMessages.NO_FIELDS_TO_UPDATE)

        # Enforce ABAC Admin Override Policy
        UserPolicy.assert_admin_not_downgrading_self(admin_id, target_user_id, payload)

        existing = await self.repo.get_user_by_id(target_user_id)
        if not existing: 
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=UserSecurityMessages.USER_NOT_FOUND)

        try:
            return await self.repo.update_profile(target_user_id, payload)
        except Exception as e:
            logger.error("Admin user override failed: %s", e)
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=UserSecurityMessages.DB_OPERATION_FAILED)

    async def get_user_detail(self, target_user_id: str) -> Dict[str, Any]:
        user = await self.repo.get_user_by_id(target_user_id)
        if not user: 
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=UserSecurityMessages.USER_NOT_FOUND)
        
        total_orders = await self.repo.count_user_orders(target_user_id)
        user["total_orders"] = total_orders
        return user
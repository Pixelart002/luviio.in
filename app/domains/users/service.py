"""
User Service — Enterprise Orchestration & Policy Enforcement
============================================================
Path: app/domains/users/service.py
"""
import logging
from typing import Any, Dict, List, Tuple, Optional

from app.domains.users.repository import AsyncUserRepository
from app.permissions.policies.user_policies import UserPolicy
from app.constants.user_messages import UserRules, UserSecurityMessages
from app.core.exceptions import LuviioException, ResourceNotFound

logger = logging.getLogger(__name__)

class UserService:
    def __init__(self) -> None:
        self.repo = AsyncUserRepository()

    async def update_profile(self, user_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        if not data:
            return {}
        try:
            res = await self.repo.update_profile(user_id, data)
            if not res:
                raise ResourceNotFound("User")
            return res
        except ResourceNotFound:
            raise
        except Exception as exc:
            logger.error("Error updating profile for %s: %s", user_id[:8], exc, exc_info=True)
            raise LuviioException(UserSecurityMessages.DB_OPERATION_FAILED, "DB_ERROR", 500) from exc

    async def get_addresses(self, user_id: str) -> List[Dict[str, Any]]:
        try:
            return await self.repo.get_user_addresses(user_id, UserRules.MAX_ADDRESSES_PER_USER)
        except Exception as exc:
            logger.error("Error fetching addresses for %s: %s", user_id[:8], exc, exc_info=True)
            raise LuviioException(UserSecurityMessages.DB_OPERATION_FAILED, "DB_ERROR", 500) from exc

    async def add_address(self, user_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        try:
            current_count = await self.repo.count_user_addresses(user_id)
        except Exception as exc:
            logger.error("Error counting addresses for %s: %s", user_id[:8], exc, exc_info=True)
            raise LuviioException(UserSecurityMessages.DB_OPERATION_FAILED, "DB_ERROR", 500) from exc
        UserPolicy.assert_address_limit(current_count)
        should_be_default = payload.get("is_default", False) or current_count == 0
        if should_be_default:
            try:
                await self.repo.unset_default_address(user_id)
            except Exception as exc:
                logger.warning("Non-fatal error unsetting default address for %s: %s", user_id[:8], exc)
        payload.update({"user_id": user_id, "is_default": should_be_default})
        try:
            res = await self.repo.create_address(payload)
            if not res:
                raise RuntimeError("Insert returned empty payload")
            return res
        except Exception as exc:
            logger.error("Error adding address for %s: %s", user_id[:8], exc, exc_info=True)
            raise LuviioException(UserSecurityMessages.DB_OPERATION_FAILED, "DB_ERROR", 500) from exc

    async def delete_address(self, user_id: str, address_id: str) -> None:
        existing = await self.repo.get_address(address_id, user_id)
        if not existing:
            raise ResourceNotFound("Address")
        was_default = existing.get("is_default", False)
        try:
            is_locked = await self.repo.is_address_in_active_order(address_id)
            if is_locked:
                await self.repo.soft_delete_address(address_id)
            else:
                await self.repo.hard_delete_address(address_id)
        except Exception as exc:
            logger.error("Error deleting address %s for user %s: %s", address_id[:8], user_id[:8], exc, exc_info=True)
            raise LuviioException(UserSecurityMessages.DB_OPERATION_FAILED, "DB_ERROR", 500) from exc
        if was_default:
            try:
                await self.repo.set_new_default_address(user_id)
            except Exception as exc:
                logger.warning("Non-fatal error setting new default address for %s: %s", user_id[:8], exc)

    async def get_users_paginated(self, page: int, page_size: int, search: Optional[str] = None, role_filter: Optional[str] = None) -> Tuple[List[Dict[str, Any]], int]:
        try:
            return await self.repo.get_users_paginated(page, page_size, search, role_filter)
        except Exception as exc:
            logger.error("Error fetching paginated users: %s", exc, exc_info=True)
            raise LuviioException(UserSecurityMessages.DB_OPERATION_FAILED, "DB_ERROR", 500) from exc

    async def admin_update_user(self, admin_id: str, target_user_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        if not payload:
            raise LuviioException(UserSecurityMessages.NO_FIELDS_TO_UPDATE, "INVALID_PAYLOAD", 400)
        UserPolicy.assert_admin_not_downgrading_self(admin_id, target_user_id, payload)
        existing = await self.repo.get_user_by_id(target_user_id)
        if not existing:
            raise ResourceNotFound("User")
        try:
            res = await self.repo.update_profile(target_user_id, payload)
            if not res:
                raise ResourceNotFound("User")
            return res
        except ResourceNotFound:
            raise
        except Exception as exc:
            logger.error("Error updating target user %s by admin %s: %s", target_user_id[:8], admin_id[:8], exc, exc_info=True)
            raise LuviioException(UserSecurityMessages.DB_OPERATION_FAILED, "DB_ERROR", 500) from exc

    async def get_user_detail(self, target_user_id: str) -> Dict[str, Any]:
        user = await self.repo.get_user_by_id(target_user_id)
        if not user:
            raise ResourceNotFound("User")
        try:
            total_orders = await self.repo.count_user_orders(target_user_id)
        except Exception as exc:
            logger.warning("Error fetching order count for %s: %s", target_user_id[:8], exc)
            total_orders = 0
        user["total_orders"] = total_orders
        return user
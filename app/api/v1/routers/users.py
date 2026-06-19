"""
Users Router — Async Enterprise Grade
=====================================
Path: app/api/v1/routers/users.py
"""
import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, status, Depends, Query, Request
from slowapi import Limiter
from slowapi.util import get_remote_address

# 🔥 ARCHITECTURE IMPORTS: Added get_user_id_strict
from app.core.dependencies import get_current_user, require_admin, get_user_id_strict
from app.repositories.user_repo import AsyncUserRepository
from app.api.schemas.user_dto import ProfileUpdate, AddressCreate, AdminUserUpdate, MessageResponse, UserListResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/users", tags=["Users"])

MAX_ADDRESSES_PER_USER = 10
limiter = Limiter(key_func=get_remote_address)

# ── Helpers ───────────────────────────────────────────────────────────────────

# 🔥 DEPRECATED: Replaced by get_user_id_strict Dependency
# def _get_user_id(current_user: dict[str, Any]) -> str:
#     if "profile" in current_user and isinstance(current_user["profile"], dict) and "id" in current_user["profile"]:
#         return str(current_user["profile"]["id"])
#     if "id" in current_user: return str(current_user["id"])
#     if "sub" in current_user: return str(current_user["sub"])
#     raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User ID not found in session")

# ══════════════════════════════════════════════════════════════════════════════
#  PROFILE ENDPOINTS
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/me")
async def get_me(request: Request, current: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    profile = current.get("profile", current)
    safe_fields = {"id", "email", "full_name", "phone", "role", "is_active", "created_at"}
    return {k: v for k, v in profile.items() if k in safe_fields}

@router.patch("/me")
@limiter.limit("20/minute")
async def update_me(
    request: Request, 
    payload: ProfileUpdate, 
    current: dict[str, Any] = Depends(get_current_user),
    user_id: str = Depends(get_user_id_strict) # 🔥 STRICT ABAC GUARD
) -> dict[str, Any]:
    # user_id = _get_user_id(current) <-- REPLACED
    repo = AsyncUserRepository()
    
    data = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not data: return current.get("profile", current)
    
    try:
        updated = await repo.update_profile(user_id, data)
        return updated or current.get("profile", current)
    except Exception as exc:
        raise HTTPException(500, "Failed to update profile")

# ══════════════════════════════════════════════════════════════════════════════
#  ADDRESS ENDPOINTS
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/me/addresses")
async def list_addresses(
    request: Request, 
    current: dict[str, Any] = Depends(get_current_user),
    user_id: str = Depends(get_user_id_strict) # 🔥 STRICT ABAC GUARD
) -> list[dict[str, Any]]:
    # user_id = _get_user_id(current) <-- REPLACED
    try:
        return await AsyncUserRepository().get_user_addresses(user_id, MAX_ADDRESSES_PER_USER)
    except Exception as exc:
        raise HTTPException(500, "Failed to fetch addresses")

@router.post("/me/addresses", status_code=status.HTTP_201_CREATED)
@limiter.limit("10/minute")
async def add_address(
    request: Request, 
    payload: AddressCreate, 
    current: dict[str, Any] = Depends(get_current_user),
    user_id: str = Depends(get_user_id_strict) # 🔥 STRICT ABAC GUARD
) -> dict[str, Any]:
    # user_id = _get_user_id(current) <-- REPLACED
    repo = AsyncUserRepository()

    try:
        current_count = await repo.count_user_addresses(user_id)
    except Exception:
        raise HTTPException(500, "Failed to verify address limit")

    if current_count >= MAX_ADDRESSES_PER_USER:
        raise HTTPException(status_code=400, detail=f"Maximum {MAX_ADDRESSES_PER_USER} addresses allowed. Please delete one first.")

    should_be_default = payload.is_default or current_count == 0

    if should_be_default:
        try: await repo.unset_default_address(user_id)
        except Exception: pass

    try:
        res = await repo.create_address({**payload.model_dump(), "user_id": user_id, "is_default": should_be_default})
    except Exception:
        raise HTTPException(500, "Failed to add address")

    if not res: raise HTTPException(500, "Failed to add address")
    return res

@router.delete("/me/addresses/{address_id}", response_model=MessageResponse)
async def delete_address(
    request: Request, 
    address_id: UUID, 
    current: dict[str, Any] = Depends(get_current_user),
    user_id: str = Depends(get_user_id_strict) # 🔥 STRICT ABAC GUARD
):
    # user_id = _get_user_id(current) <-- REPLACED
    repo = AsyncUserRepository()

    existing = await repo.get_address(str(address_id), user_id)
    if not existing: raise HTTPException(404, "Address not found")
    was_default = existing.get("is_default", False)

    try:
        if await repo.is_address_in_active_order(str(address_id)):
            raise HTTPException(status_code=409, detail="Cannot delete — this address is used in an active order.")
    except HTTPException: raise
    except Exception: pass

    try: await repo.delete_address(str(address_id))
    except Exception: raise HTTPException(500, "Failed to delete address")

    if was_default:
        try: await repo.set_new_default_address(user_id)
        except Exception: pass

    return {"message": "Address deleted successfully"}


# ══════════════════════════════════════════════════════════════════════════════
#  ADMIN ENDPOINTS
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/", dependencies=[Depends(require_admin)], response_model=UserListResponse)
async def list_users(
    request: Request, page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
    search: str | None = Query(None, max_length=100), role_filter: str | None = Query(None, pattern="^(customer|admin)$")
):
    try: 
        items, total = await AsyncUserRepository().get_users_paginated(page, page_size, search, role_filter)
    except Exception: raise HTTPException(500, "Failed to fetch users")

    return {"items": items, "total": total, "page": page, "page_size": page_size, "pages": -(-total // page_size) if page_size > 0 else 0}

@router.patch("/{user_id}", dependencies=[Depends(require_admin)])
async def admin_update_user(
    request: Request, 
    user_id: UUID, 
    payload: AdminUserUpdate, 
    current: dict[str, Any] = Depends(require_admin),
    admin_id: str = Depends(get_user_id_strict) # 🔥 STRICT ABAC GUARD
):
    # admin_id = _get_user_id(current) <-- REPLACED
    repo = AsyncUserRepository()

    if str(user_id) == str(admin_id):
        if payload.role and payload.role != "admin": raise HTTPException(status_code=403, detail="You cannot change your own role")
        if payload.is_active is False: raise HTTPException(status_code=403, detail="You cannot deactivate your own account")

    data = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not data: raise HTTPException(400, "No fields to update")

    existing = await repo.get_user_by_id(str(user_id))
    if not existing: raise HTTPException(404, "User not found")

    try: result = await repo.update_profile(str(user_id), data)
    except Exception: raise HTTPException(500, "Failed to update user")
    return result

@router.get("/{user_id}", dependencies=[Depends(require_admin)])
async def get_user_detail(request: Request, user_id: UUID):
    repo = AsyncUserRepository()
    
    user = await repo.get_user_by_id(str(user_id))
    if not user: raise HTTPException(404, "User not found")
    
    try: total_orders = await repo.count_user_orders(str(user_id))
    except Exception: total_orders = 0
    
    user["total_orders"] = total_orders
    return user
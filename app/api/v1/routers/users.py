"""
User Router — Async Hardened Production Grade
=============================================
Path: app/api/v1/routers/users.py
"""
import logging
from uuid import UUID
from typing import Dict, Any, Optional
from fastapi import APIRouter, Depends, Query, Request, status
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.dependencies import get_current_user, get_user_id_strict, require_permission
from app.permissions.users import UserPermissions
from app.services.users.service import UserService
from app.api.schemas.user_dto import ProfileUpdate, AddressCreate, AdminUserUpdate, MessageResponse
from app.constants.user_messages import UserMessages
from app.utils.response import success_response
from app.utils.pagination import paginate

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/users", tags=["Users"])
limiter = Limiter(key_func=get_remote_address)

@router.get("/me", status_code=status.HTTP_200_OK)
async def get_me(request: Request, current: Dict[str, Any] = Depends(get_current_user)):
    """Returns the currently authenticated user's profile metadata."""
    if hasattr(request.state, "actions"): 
        request.state.actions.append("Extracting active profile payload from secure token session")
        
    profile = current.get("profile", current)
    safe_fields = {"id", "email", "full_name", "phone", "role", "is_active", "created_at"}
    return success_response({k: v for k, v in profile.items() if k in safe_fields})

@router.patch("/me", status_code=status.HTTP_200_OK)
@limiter.limit("20/minute")
async def update_me(request: Request, payload: ProfileUpdate, current: Dict[str, Any] = Depends(get_current_user), user_id: str = Depends(get_user_id_strict)):
    """Updates non-sensitive profile information."""
    if hasattr(request.state, "actions"): 
        request.state.actions.append(f"Validating profile update schema for -> UID: {user_id[:8]}...")
    
    updated = await UserService().update_profile(user_id, payload.model_dump(exclude_unset=True))
    
    if updated and hasattr(request.state, "actions"): 
        request.state.actions.append(UserMessages.PROFILE_UPDATED)
        
    return success_response(data=updated or current.get("profile", current), message=UserMessages.PROFILE_UPDATED)

@router.get("/me/addresses", status_code=status.HTTP_200_OK)
async def list_addresses(request: Request, user_id: str = Depends(get_user_id_strict)):
    """Returns a list of all shipping addresses bound to the current user."""
    if hasattr(request.state, "actions"): 
        request.state.actions.append("Fetching saved shipping address ledger for active user")
        
    return success_response(await UserService().get_addresses(user_id))

@router.post("/me/addresses", status_code=status.HTTP_201_CREATED)
@limiter.limit("10/minute")
async def add_address(request: Request, payload: AddressCreate, user_id: str = Depends(get_user_id_strict)):
    """Adds a new shipping address. Enforces ABAC max limits per user."""
    if hasattr(request.state, "actions"): 
        request.state.actions.append("Validating address limits against global maximum")
    
    result = await UserService().add_address(user_id, payload.model_dump())
    
    if hasattr(request.state, "actions"): 
        request.state.actions.append(UserMessages.ADDRESS_ADDED)
        
    return success_response(data=result, message=UserMessages.ADDRESS_ADDED)

@router.delete("/me/addresses/{address_id}", status_code=status.HTTP_200_OK, response_model=MessageResponse)
async def delete_address(request: Request, address_id: UUID, user_id: str = Depends(get_user_id_strict)):
    """ABAC Guarded: Deletes a shipping address, failing if currently locked to a shipment."""
    if hasattr(request.state, "actions"): 
        request.state.actions.append(f"Targeting address {str(address_id)[:8]}... for deletion")
    
    await UserService().delete_address(user_id, str(address_id))
    
    if hasattr(request.state, "actions"): 
        request.state.actions.append(UserMessages.ADDRESS_DELETED)
        
    return {"message": UserMessages.ADDRESS_DELETED}

@router.get("/", status_code=status.HTTP_200_OK, dependencies=[Depends(require_permission(UserPermissions.READ))])
async def list_users(
    request: Request, 
    page: int = Query(1, ge=1), 
    page_size: int = Query(20, ge=1, le=100), 
    search: Optional[str] = Query(None, max_length=100), 
    role_filter: Optional[str] = Query(None, pattern="^(customer|admin|manager|support)$")
):
    """PBAC Guarded: Returns a paginated catalog of all registered users."""
    if hasattr(request.state, "actions"): 
        request.state.actions.append(f"God-Mode: Admin scanning global user registry (Page: {page})")
    
    items, total = await UserService().get_users_paginated(page, page_size, search, role_filter)
    return paginate(items, total, page, page_size)

@router.patch("/{user_id}", status_code=status.HTTP_200_OK, dependencies=[Depends(require_permission(UserPermissions.UPDATE))])
async def admin_update_user(request: Request, user_id: UUID, payload: AdminUserUpdate, admin_id: str = Depends(get_user_id_strict)):
    """PBAC Guarded: Hard override of a user's role or active state."""
    if hasattr(request.state, "actions"): 
        request.state.actions.append(f"Admin overriding user profile -> Target ID: {str(user_id)[:8]}...")
    
    result = await UserService().admin_update_user(admin_id, str(user_id), payload.model_dump(exclude_unset=True))
    
    if hasattr(request.state, "actions"): 
        request.state.actions.append(UserMessages.USER_UPDATED)
        
    return success_response(data=result, message=UserMessages.USER_UPDATED)

@router.get("/{user_id}", status_code=status.HTTP_200_OK, dependencies=[Depends(require_permission(UserPermissions.READ))])
async def get_user_detail(request: Request, user_id: UUID):
    """PBAC Guarded: Deep fetch of user metadata and historical order counts."""
    if hasattr(request.state, "actions"): 
        request.state.actions.append(f"Admin fetching full detail & telemetry for User -> {str(user_id)[:8]}...")
    
    result = await UserService().get_user_detail(str(user_id))
    
    if hasattr(request.state, "actions"): 
        request.state.actions.append(f"Aggregated user profile & historical order count ({result.get('total_orders')} orders)")
        
    return success_response(result)
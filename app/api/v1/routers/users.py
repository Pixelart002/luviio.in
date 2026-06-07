"""
Users Router — Enterprise Grade
================================
Path: app/api/v1/routers/users.py

Architecture Upgrades:
  1. ALL Supabase DB logic strictly delegated to UserRepository.
  2. Router only handles HTTP flow, Auth/Admin dependencies, and Responses.
"""
import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, status, Depends, Query, Request
from slowapi import Limiter
from slowapi.util import get_remote_address

# 🔥 ARCHITECTURE IMPORTS
from app.core.dependencies import get_current_user, require_admin
from app.repositories.user_repo import UserRepository
from app.api.schemas.user_dto import ProfileUpdate, AddressCreate, AdminUserUpdate, MessageResponse, UserListResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/users", tags=["Users"])

# ── Constants & Rate Limiter ──────────────────────────────────────────────────
MAX_ADDRESSES_PER_USER = 10
limiter = Limiter(key_func=get_remote_address)

# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_user_id(current_user: dict[str, Any]) -> str:
    if "profile" in current_user and isinstance(current_user["profile"], dict) and "id" in current_user["profile"]:
        return str(current_user["profile"]["id"])
    if "id" in current_user: return str(current_user["id"])
    if "sub" in current_user: return str(current_user["sub"])
        
    logger.error(f"Cannot find user ID in session keys: {list(current_user.keys())}")
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User ID not found in session")

def _audit_log(action: str, admin_id: str, target_user_id: str = "", details: str = ""):
    logger.info("AUDIT | action=%s admin=%.8s target=%.8s | %s", action, admin_id, target_user_id, details)

# ══════════════════════════════════════════════════════════════════════════════
#  PROFILE ENDPOINTS
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/me")
def get_me(request: Request, current: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    if hasattr(request.state, "actions"): request.state.actions.append("Fetching current user profile")
    profile = current.get("profile", current)
    safe_fields = {"id", "email", "full_name", "phone", "role", "is_active", "created_at"}
    return {k: v for k, v in profile.items() if k in safe_fields}

@router.patch("/me")
@limiter.limit("20/minute")
def update_me(request: Request, payload: ProfileUpdate, current: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    if hasattr(request.state, "actions"): request.state.actions.append("Processing profile update request")
    user_id = _get_user_id(current)
    repo = UserRepository()
    
    data = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not data: return current.get("profile", current)
    
    try:
        updated = repo.update_profile(user_id, data)
        logger.info("Profile updated | user=%.8s fields=%s", user_id, list(data.keys()))
        if hasattr(request.state, "actions"): request.state.actions.append(f"Successfully updated fields: {', '.join(data.keys())}")
        return updated or current.get("profile", current)
    except Exception as exc:
        logger.error("Profile update failed | user=%.8s: %s", user_id, exc)
        raise HTTPException(500, "Failed to update profile")

# ══════════════════════════════════════════════════════════════════════════════
#  ADDRESS ENDPOINTS
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/me/addresses")
def list_addresses(request: Request, current: dict[str, Any] = Depends(get_current_user)) -> list[dict[str, Any]]:
    if hasattr(request.state, "actions"): request.state.actions.append("Fetching user's saved addresses")
    user_id = _get_user_id(current)
    try:
        return UserRepository().get_user_addresses(user_id, MAX_ADDRESSES_PER_USER)
    except Exception as exc:
        logger.error("Failed to list addresses | user=%.8s: %s", user_id, exc)
        raise HTTPException(500, "Failed to fetch addresses")

@router.post("/me/addresses", status_code=status.HTTP_201_CREATED)
@limiter.limit("10/minute")
def add_address(request: Request, payload: AddressCreate, current: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    if hasattr(request.state, "actions"): request.state.actions.append("Initiating new shipping address creation")
    user_id = _get_user_id(current)
    repo = UserRepository()

    try:
        current_count = repo.count_user_addresses(user_id)
    except Exception:
        raise HTTPException(500, "Failed to verify address limit")

    if hasattr(request.state, "actions"): request.state.actions.append(f"Current address count: {current_count}/{MAX_ADDRESSES_PER_USER}")
    if current_count >= MAX_ADDRESSES_PER_USER:
        raise HTTPException(status_code=400, detail=f"Maximum {MAX_ADDRESSES_PER_USER} addresses allowed. Please delete one first.")

    should_be_default = payload.is_default or current_count == 0

    if should_be_default:
        try: repo.unset_default_address(user_id)
        except Exception: pass

    try:
        res = repo.create_address({**payload.model_dump(), "user_id": user_id, "is_default": should_be_default})
    except Exception:
        raise HTTPException(500, "Failed to add address")

    if not res: raise HTTPException(500, "Failed to add address")
    if hasattr(request.state, "actions"): request.state.actions.append(f"New address saved successfully (Default: {should_be_default})")
    
    return res

@router.delete("/me/addresses/{address_id}", response_model=MessageResponse)
def delete_address(request: Request, address_id: UUID, current: dict[str, Any] = Depends(get_current_user)):
    if hasattr(request.state, "actions"): request.state.actions.append(f"Validating address deletion: {str(address_id)[:8]}...")
    user_id = _get_user_id(current)
    repo = UserRepository()

    existing = repo.get_address(str(address_id), user_id)
    if not existing: raise HTTPException(404, "Address not found")
    was_default = existing.get("is_default", False)

    try:
        if repo.is_address_in_active_order(str(address_id)):
            raise HTTPException(status_code=409, detail="Cannot delete — this address is used in an active order.")
    except HTTPException: raise
    except Exception: pass

    if hasattr(request.state, "actions"): request.state.actions.append("No active orders found for this address. Proceeding.")

    try: repo.delete_address(str(address_id))
    except Exception: raise HTTPException(500, "Failed to delete address")

    if was_default:
        try: repo.set_new_default_address(user_id)
        except Exception: pass

    if hasattr(request.state, "actions"): request.state.actions.append("Address successfully deleted")
    return {"message": "Address deleted successfully"}


# ══════════════════════════════════════════════════════════════════════════════
#  ADMIN ENDPOINTS
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/", dependencies=[Depends(require_admin)], response_model=UserListResponse)
def list_users(
    request: Request, page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
    search: str | None = Query(None, max_length=100), role_filter: str | None = Query(None, pattern="^(customer|admin)$")
):
    if hasattr(request.state, "actions"): request.state.actions.append(f"Admin listing users (Page: {page})")
    try: 
        items, total = UserRepository().get_users_paginated(page, page_size, search, role_filter)
    except Exception: raise HTTPException(500, "Failed to fetch users")

    return {"items": items, "total": total, "page": page, "page_size": page_size, "pages": -(-total // page_size) if page_size > 0 else 0}

@router.patch("/{user_id}", dependencies=[Depends(require_admin)])
def admin_update_user(request: Request, user_id: UUID, payload: AdminUserUpdate, current: dict[str, Any] = Depends(require_admin)):
    if hasattr(request.state, "actions"): request.state.actions.append(f"Admin modifying user: {str(user_id)[:8]}...")
    admin_id = _get_user_id(current)
    repo = UserRepository()

    if str(user_id) == str(admin_id):
        if payload.role and payload.role != "admin": raise HTTPException(status_code=403, detail="You cannot change your own role")
        if payload.is_active is False: raise HTTPException(status_code=403, detail="You cannot deactivate your own account")

    data = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not data: raise HTTPException(400, "No fields to update")

    existing = repo.get_user_by_id(str(user_id))
    if not existing: raise HTTPException(404, "User not found")

    try: result = repo.update_profile(str(user_id), data)
    except Exception: raise HTTPException(500, "Failed to update user")

    old_role, old_active = existing.get("role", "?"), existing.get("is_active", "?")
    _audit_log("USER_UPDATED", admin_id, str(user_id), f"role: {old_role}→{data.get('role', old_role)}, active: {old_active}→{data.get('is_active', old_active)}")
    
    if hasattr(request.state, "actions"): request.state.actions.append("User role/status successfully updated in database")
    return result

@router.get("/{user_id}", dependencies=[Depends(require_admin)])
def get_user_detail(request: Request, user_id: UUID):
    if hasattr(request.state, "actions"): request.state.actions.append(f"Admin fetching details for user: {str(user_id)[:8]}...")
    repo = UserRepository()
    
    user = repo.get_user_by_id(str(user_id))
    if not user: raise HTTPException(404, "User not found")
    
    try: total_orders = repo.count_user_orders(str(user_id))
    except Exception: total_orders = 0
    
    user["total_orders"] = total_orders
    return user
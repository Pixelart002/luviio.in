"""
Users Router
=============
Changes from original:
  All .single() → .maybe_single() throughout.
  UserRepository used for get_me / update_me (cleaner).
  FIXED: Safe extraction of user ID via _get_user_id() to prevent KeyError crashes.
  FIXED: Added comprehensive NoneType checks on all Supabase responses (.data and .count).
"""
import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, status, Depends, Query
from pydantic import BaseModel, Field

from postgrest.exceptions import APIError as PostgrestError

from app.dependencies import get_current_user, require_admin
from app.supabase_client import get_admin_supabase
from app.repositories.user_repo import UserRepository

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/users", tags=["Users"])

MAX_ADDRESSES_PER_USER = 10


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_user_id(current_user: dict[str, Any]) -> str:
    """Safely extract user_id from the current user object/token payload."""
    if "profile" in current_user and isinstance(current_user["profile"], dict) and "id" in current_user["profile"]:
        return str(current_user["profile"]["id"])
    if "id" in current_user:
        return str(current_user["id"])
    if "sub" in current_user:
        return str(current_user["sub"])
        
    logger.error(f"Cannot find user ID in: {current_user}")
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User ID not found in session")


# ── Models ────────────────────────────────────────────────────────────────────

class ProfileUpdate(BaseModel):
    full_name: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=20)


class AddressCreate(BaseModel):
    line1: str = Field(max_length=255)
    line2: str | None = Field(default=None, max_length=255)
    city: str = Field(max_length=100)
    state: str | None = Field(default=None, max_length=100)
    postal_code: str = Field(max_length=20)
    country: str = Field(min_length=2, max_length=2)
    is_default: bool = False


class AdminUserUpdate(BaseModel):
    is_active: bool | None = None
    role: str | None = Field(default=None, pattern="^(customer|admin)$")


# ── Profile ───────────────────────────────────────────────────────────────────

@router.get("/me")
def get_me(current: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    # Safely return profile or current if nested profile doesn't exist
    return current.get("profile", current)


@router.patch("/me")
def update_me(
    payload: ProfileUpdate,
    current: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    sb   = get_admin_supabase()
    repo = UserRepository(sb)
    
    # Safe user ID extraction
    user_id = _get_user_id(current)
    
    data = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not data:
        return current.get("profile", current)
        
    updated = repo.update_profile(user_id, data)
    return updated or current.get("profile", current)


# ── Addresses ─────────────────────────────────────────────────────────────────

@router.get("/me/addresses")
def list_addresses(
    current: dict[str, Any] = Depends(get_current_user),
) -> list[dict[str, Any]]:
    sb = get_admin_supabase()
    user_id = _get_user_id(current)
    
    res = (
        sb.table("addresses")
        .select("*")
        .eq("user_id", user_id)
        .order("is_default", desc=True)
        .limit(MAX_ADDRESSES_PER_USER)
        .execute()
    )
    return res.data if res and hasattr(res, "data") and res.data else []


@router.post("/me/addresses", status_code=status.HTTP_201_CREATED)
def add_address(
    payload: AddressCreate,
    current: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    sb      = get_admin_supabase()
    user_id = _get_user_id(current)

    count_res = (
        sb.table("addresses")
        .select("id", count="exact")
        .eq("user_id", user_id)
        .execute()
    )
    
    current_count = count_res.count if count_res and hasattr(count_res, "count") and count_res.count else 0
    if current_count >= MAX_ADDRESSES_PER_USER:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Maximum {MAX_ADDRESSES_PER_USER} addresses allowed per user",
        )

    if payload.is_default:
        sb.table("addresses").update({"is_default": False}).eq("user_id", user_id).execute()

    res = (
        sb.table("addresses")
        .insert({**payload.model_dump(), "user_id": user_id})
        .execute()
    )
    
    if not res or not hasattr(res, "data") or not res.data:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to add address")
        
    return res.data[0]


@router.delete("/me/addresses/{address_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_address(
    address_id: UUID,
    current: dict[str, Any] = Depends(get_current_user),
) -> None:
    sb      = get_admin_supabase()
    user_id = _get_user_id(current)

    existing = (
        sb.table("addresses")
        .select("id")
        .eq("id", str(address_id))
        .eq("user_id", user_id)
        .maybe_single()
        .execute()
    )
    
    # Safe check for existence
    if not existing or not hasattr(existing, "data") or not existing.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Address not found")

    active = (
        sb.table("orders")
        .select("id")
        .eq("shipping_address_id", str(address_id))
        .in_("status", ["pending", "paid", "shipped"])
        .execute()
    )
    
    # Safe check for active orders
    if active and hasattr(active, "data") and active.data:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot delete — address is used in an active order",
        )

    sb.table("addresses").delete().eq("id", str(address_id)).execute()


# ── Admin ─────────────────────────────────────────────────────────────────────

@router.get("/", dependencies=[Depends(require_admin)])
def list_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> dict[str, Any]:
    sb = get_admin_supabase()
    offset = (page - 1) * page_size
    result = (
        sb.table("users")
        .select("id, email, full_name, phone, role, is_active, created_at", count="exact")
        .order("created_at", desc=True)
        .range(offset, offset + page_size - 1)
        .execute()
    )
    
    total: int = result.count if result and hasattr(result, "count") and result.count else 0
    items = result.data if result and hasattr(result, "data") and result.data else []
    
    return {
        "items":     items,
        "total":     total,
        "page":      page,
        "page_size": page_size,
        "pages":     -(-total // page_size) if page_size > 0 else 0,
    }


@router.patch("/{user_id}", dependencies=[Depends(require_admin)])
def admin_update_user(
    user_id: UUID,
    payload: AdminUserUpdate,
    current: dict[str, Any] = Depends(require_admin),
) -> dict[str, Any]:
    sb = get_admin_supabase()
    
    admin_id = _get_user_id(current)

    if str(user_id) == str(admin_id) and payload.role:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You cannot change your own role",
        )

    data = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No fields to update")

    result = sb.table("users").update(data).eq("id", str(user_id)).execute()
    
    # Safe check
    if not result or not hasattr(result, "data") or not result.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        
    return result.data[0]
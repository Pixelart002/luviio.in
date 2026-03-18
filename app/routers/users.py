"""
Users Router
=============
Changes from original:
  All .single() → .maybe_single() throughout.
  UserRepository used for get_me / update_me (cleaner).
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
    return current["profile"]


@router.patch("/me")
def update_me(
    payload: ProfileUpdate,
    current: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    sb   = get_admin_supabase()
    repo = UserRepository(sb)
    data = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not data:
        return current["profile"]
    updated = repo.update_profile(current["profile"]["id"], data)
    return updated or current["profile"]


# ── Addresses ─────────────────────────────────────────────────────────────────

@router.get("/me/addresses")
def list_addresses(
    current: dict[str, Any] = Depends(get_current_user),
) -> list[dict[str, Any]]:
    sb = get_admin_supabase()
    return (
        sb.table("addresses")
        .select("*")
        .eq("user_id", current["profile"]["id"])
        .order("is_default", desc=True)
        .limit(MAX_ADDRESSES_PER_USER)
        .execute()
        .data
    )


@router.post("/me/addresses", status_code=status.HTTP_201_CREATED)
def add_address(
    payload: AddressCreate,
    current: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    sb      = get_admin_supabase()
    user_id = current["profile"]["id"]

    count_res = (
        sb.table("addresses")
        .select("id", count="exact")
        .eq("user_id", user_id)
        .execute()
    )
    if (count_res.count or 0) >= MAX_ADDRESSES_PER_USER:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Maximum {MAX_ADDRESSES_PER_USER} addresses allowed per user",
        )

    if payload.is_default:
        sb.table("addresses").update({"is_default": False}).eq("user_id", user_id).execute()

    return (
        sb.table("addresses")
        .insert({**payload.model_dump(), "user_id": user_id})
        .execute()
        .data[0]
    )


@router.delete("/me/addresses/{address_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_address(
    address_id: UUID,
    current: dict[str, Any] = Depends(get_current_user),
) -> None:
    sb      = get_admin_supabase()
    user_id = current["profile"]["id"]

    existing = (
        sb.table("addresses")
        .select("id")
        .eq("id", str(address_id))
        .eq("user_id", user_id)
        .maybe_single()   # ← was missing, plain .execute().data check is fine but explicit is better
        .execute()
    )
    if not existing.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Address not found")

    active = (
        sb.table("orders")
        .select("id")
        .eq("shipping_address_id", str(address_id))
        .in_("status", ["pending", "paid", "shipped"])
        .execute()
    )
    if active.data:
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
    total: int = result.count or 0
    return {
        "items":     result.data,
        "total":     total,
        "page":      page,
        "page_size": page_size,
        "pages":     -(-total // page_size),
    }


@router.patch("/{user_id}", dependencies=[Depends(require_admin)])
def admin_update_user(
    user_id: UUID,
    payload: AdminUserUpdate,
    current: dict[str, Any] = Depends(require_admin),
) -> dict[str, Any]:
    sb = get_admin_supabase()

    if str(user_id) == str(current["profile"]["id"]) and payload.role:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You cannot change your own role",
        )

    data = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No fields to update")

    result = sb.table("users").update(data).eq("id", str(user_id)).execute()
    if not result.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return result.data[0]
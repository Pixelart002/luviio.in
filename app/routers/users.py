import logging
from typing import Any

from fastapi import APIRouter, HTTPException, status, Depends, Query
from pydantic import BaseModel, Field

from app.dependencies import get_current_user, require_admin
from app.supabase_client import get_admin_supabase

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/users", tags=["Users"])

MAX_ADDRESSES_PER_USER = 10

# ── Request models ─────────────────────────────────────────────────────────────

class ProfileUpdate(BaseModel):
    full_name: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=20)


class AddressCreate(BaseModel):
    line1: str = Field(max_length=255)
    line2: str | None = Field(default=None, max_length=255)
    city: str = Field(max_length=100)
    state: str | None = Field(default=None, max_length=100)
    postal_code: str = Field(max_length=20)
    country: str = Field(min_length=2, max_length=2)  # ISO 3166-1 alpha-2 e.g. "IN"
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
    sb = get_admin_supabase()
    user_id: str = current["profile"]["id"]
    data = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not data:
        return current["profile"]
    result = sb.table("users").update(data).eq("id", user_id).execute()
    return result.data[0] if result.data else current["profile"]


# ── Addresses ─────────────────────────────────────────────────────────────────

@router.get("/me/addresses")
def list_addresses(
    current: dict[str, Any] = Depends(get_current_user),
) -> list[dict[str, Any]]:
    sb = get_admin_supabase()
    result = (
        sb.table("addresses")
        .select("*")
        .eq("user_id", current["profile"]["id"])
        .execute()
    )
    return result.data


@router.post("/me/addresses", status_code=status.HTTP_201_CREATED)
def add_address(
    payload: AddressCreate,
    current: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    sb = get_admin_supabase()
    user_id: str = current["profile"]["id"]

    # Max address limit check
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

    # Pehle default unset karo agar ye new default hai
    if payload.is_default:
        sb.table("addresses").update({"is_default": False}).eq("user_id", user_id).execute()

    result = sb.table("addresses").insert(
        {**payload.model_dump(), "user_id": user_id}
    ).execute()
    return result.data[0]


@router.delete("/me/addresses/{address_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_address(
    address_id: str,
    current: dict[str, Any] = Depends(get_current_user),
) -> None:
    sb = get_admin_supabase()
    user_id: str = current["profile"]["id"]

    # Ownership check
    existing = (
        sb.table("addresses")
        .select("id")
        .eq("id", address_id)
        .eq("user_id", user_id)
        .execute()
    )
    if not existing.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Address not found")

    # Active order check — address delete nahi ho sakta agar order use kar raha ho
    active_orders = (
        sb.table("orders")
        .select("id")
        .eq("shipping_address_id", address_id)
        .in_("status", ["pending", "paid", "shipped"])
        .execute()
    )
    if active_orders.data:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot delete address — it is used in an active order",
        )

    sb.table("addresses").delete().eq("id", address_id).execute()


# ── Admin ─────────────────────────────────────────────────────────────────────

@router.get("/", dependencies=[Depends(require_admin)])
def list_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> dict[str, Any]:
    sb = get_admin_supabase()
    offset = (page - 1) * page_size

    # Explicit columns — no SELECT * (sensitive data minimize)
    result = (
        sb.table("users")
        .select("id, email, full_name, phone, role, is_active, created_at", count="exact")
        .order("created_at", desc=True)
        .range(offset, offset + page_size - 1)
        .execute()
    )
    total: int = result.count or 0
    return {
        "items": result.data,
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": -(-total // page_size),
    }


@router.patch("/{user_id}", dependencies=[Depends(require_admin)])
def admin_update_user(
    user_id: str,
    payload: AdminUserUpdate,
    current: dict[str, Any] = Depends(require_admin),
) -> dict[str, Any]:
    sb = get_admin_supabase()

    # Admin apna khud ka role nahi badal sakta
    if str(user_id) == str(current["profile"]["id"]) and payload.role:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You cannot change your own role",
        )

    data = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No fields to update",
        )

    result = sb.table("users").update(data).eq("id", user_id).execute()
    if not result.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return result.data[0]
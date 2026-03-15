from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel, Field
from typing import Optional
from app.dependencies import get_current_user, require_admin
from app.supabase_client import get_admin_supabase

router = APIRouter(prefix="/users", tags=["Users"])


class ProfileUpdate(BaseModel):
    full_name: Optional[str] = Field(default=None, max_length=255)
    phone: Optional[str] = Field(default=None, max_length=20)

class AddressCreate(BaseModel):
    line1: str = Field(max_length=255)
    line2: Optional[str] = Field(default=None, max_length=255)
    city: str = Field(max_length=100)
    state: Optional[str] = Field(default=None, max_length=100)
    postal_code: str = Field(max_length=20)
    country: str = Field(min_length=2, max_length=2)
    is_default: bool = False

class AdminUserUpdate(BaseModel):
    is_active: Optional[bool] = None
    role: Optional[str] = Field(default=None, pattern="^(customer|admin)$")


# ── Profile ───────────────────────────────────────────────────────────────────

@router.get("/me")
def get_me(current: dict = Depends(get_current_user)):
    return current["profile"]


@router.patch("/me")
def update_me(payload: ProfileUpdate, current: dict = Depends(get_current_user)):
    sb = get_admin_supabase()
    user_id = current["profile"]["id"]
    data = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not data:
        return current["profile"]
    result = sb.table("users").update(data).eq("id", user_id).execute()
    return result.data[0] if result.data else current["profile"]


# ── Addresses ─────────────────────────────────────────────────────────────────

@router.get("/me/addresses")
def list_addresses(current: dict = Depends(get_current_user)):
    sb = get_admin_supabase()
    result = sb.table("addresses").select("*").eq("user_id", current["profile"]["id"]).execute()
    return result.data


@router.post("/me/addresses", status_code=201)
def add_address(payload: AddressCreate, current: dict = Depends(get_current_user)):
    sb = get_admin_supabase()
    user_id = current["profile"]["id"]
    if payload.is_default:
        sb.table("addresses").update({"is_default": False}).eq("user_id", user_id).execute()
    result = sb.table("addresses").insert({**payload.model_dump(), "user_id": user_id}).execute()
    return result.data[0]


@router.delete("/me/addresses/{address_id}", status_code=204)
def delete_address(address_id: str, current: dict = Depends(get_current_user)):
    sb = get_admin_supabase()
    existing = sb.table("addresses").select("id").eq("id", address_id).eq("user_id", current["profile"]["id"]).execute()
    if not existing.data:
        raise HTTPException(status_code=404, detail="Address not found")
    sb.table("addresses").delete().eq("id", address_id).execute()


# ── Admin ─────────────────────────────────────────────────────────────────────

@router.get("/", dependencies=[Depends(require_admin)])
def list_users(
    skip: int = 0,
    limit: int = Query(20, ge=1, le=100)  # ← pehle 50 tha, ab max 100 cap hai
):
    sb = get_admin_supabase()
    result = sb.table("users").select("*").range(skip, skip + limit - 1).execute()
    return result.data


@router.patch("/{user_id}", dependencies=[Depends(require_admin)])
def admin_update_user(user_id: str, payload: AdminUserUpdate, current: dict = Depends(require_admin)):
    sb = get_admin_supabase()

    # Admin apna khud ka role nahi badal sakta ← naya security check
    if str(user_id) == str(current["profile"]["id"]) and payload.role:
        raise HTTPException(status_code=403, detail="You cannot change your own role")

    data = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not data:
        raise HTTPException(status_code=400, detail="No fields to update")
    result = sb.table("users").update(data).eq("id", user_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="User not found")
    return result.data[0]
"""
Users Router — Enterprise Grade
================================
Path: app/api/v1/routers/users.py
"""
import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, status, Depends, Query, Request
from slowapi import Limiter
from slowapi.util import get_remote_address

# 🔥 ARCHITECTURE IMPORTS
from app.core.dependencies import get_current_user, require_admin
from app.core.supabase import get_admin_supabase
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
    sb = get_admin_supabase()
    user_id = _get_user_id(current)
    
    data = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not data: return current.get("profile", current)
    
    try:
        updated = sb.table("users").update(data).eq("id", user_id).execute()
        logger.info("Profile updated | user=%.8s fields=%s", user_id, list(data.keys()))
        if hasattr(request.state, "actions"): request.state.actions.append(f"Successfully updated fields: {', '.join(data.keys())}")
        return updated.data[0] if updated and getattr(updated, "data", None) else current.get("profile", current)
    except Exception as exc:
        logger.error("Profile update failed | user=%.8s: %s", user_id, exc)
        raise HTTPException(500, "Failed to update profile")

# ══════════════════════════════════════════════════════════════════════════════
#  ADDRESS ENDPOINTS
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/me/addresses")
def list_addresses(request: Request, current: dict[str, Any] = Depends(get_current_user)) -> list[dict[str, Any]]:
    if hasattr(request.state, "actions"): request.state.actions.append("Fetching user's saved addresses")
    sb = get_admin_supabase()
    user_id = _get_user_id(current)
    try:
        res = sb.table("addresses").select("*").eq("user_id", user_id).order("is_default", desc=True).order("created_at", desc=True).limit(MAX_ADDRESSES_PER_USER).execute()
        return res.data if res and hasattr(res, "data") and res.data else []
    except Exception as exc:
        logger.error("Failed to list addresses | user=%.8s: %s", user_id, exc)
        raise HTTPException(500, "Failed to fetch addresses")

@router.post("/me/addresses", status_code=status.HTTP_201_CREATED)
@limiter.limit("10/minute")
def add_address(request: Request, payload: AddressCreate, current: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    if hasattr(request.state, "actions"): request.state.actions.append("Initiating new shipping address creation")
    sb = get_admin_supabase()
    user_id = _get_user_id(current)

    try:
        count_res = sb.table("addresses").select("id", count="exact").eq("user_id", user_id).limit(1).execute()
        current_count = count_res.count if count_res and hasattr(count_res, "count") and count_res.count else 0
    except Exception as exc:
        raise HTTPException(500, "Failed to verify address limit")

    if hasattr(request.state, "actions"): request.state.actions.append(f"Current address count: {current_count}/{MAX_ADDRESSES_PER_USER}")
    if current_count >= MAX_ADDRESSES_PER_USER:
        raise HTTPException(status_code=400, detail=f"Maximum {MAX_ADDRESSES_PER_USER} addresses allowed. Please delete one first.")

    should_be_default = payload.is_default or current_count == 0

    if should_be_default:
        try: sb.table("addresses").update({"is_default": False}).eq("user_id", user_id).execute()
        except Exception: pass

    try:
        res = sb.table("addresses").insert({**payload.model_dump(), "user_id": user_id, "is_default": should_be_default}).execute()
    except Exception as exc:
        raise HTTPException(500, "Failed to add address")

    if not res or not hasattr(res, "data") or not res.data: raise HTTPException(500, "Failed to add address")
    if hasattr(request.state, "actions"): request.state.actions.append(f"New address saved successfully (Default: {should_be_default})")
    
    return res.data[0]

@router.delete("/me/addresses/{address_id}", response_model=MessageResponse)
def delete_address(request: Request, address_id: UUID, current: dict[str, Any] = Depends(get_current_user)):
    if hasattr(request.state, "actions"): request.state.actions.append(f"Validating address deletion: {str(address_id)[:8]}...")
    sb = get_admin_supabase()
    user_id = _get_user_id(current)

    existing = sb.table("addresses").select("id, is_default").eq("id", str(address_id)).eq("user_id", user_id).limit(1).execute()
    if not existing or not hasattr(existing, "data") or not existing.data: raise HTTPException(404, "Address not found")
    was_default = existing.data[0].get("is_default", False)

    try:
        active = sb.table("orders").select("id").eq("shipping_address_id", str(address_id)).in_("status", ["pending", "paid", "shipped"]).limit(1).execute()
        if active and hasattr(active, "data") and active.data:
            raise HTTPException(status_code=409, detail="Cannot delete — this address is used in an active order.")
    except HTTPException: raise
    except Exception: pass

    if hasattr(request.state, "actions"): request.state.actions.append("No active orders found for this address. Proceeding.")

    try: sb.table("addresses").delete().eq("id", str(address_id)).execute()
    except Exception: raise HTTPException(500, "Failed to delete address")

    if was_default:
        try:
            remaining = sb.table("addresses").select("id").eq("user_id", user_id).limit(1).execute()
            if remaining and hasattr(remaining, "data") and remaining.data:
                sb.table("addresses").update({"is_default": True}).eq("id", remaining.data[0]["id"]).execute()
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
    sb = get_admin_supabase()
    offset = (page - 1) * page_size
    q = sb.table("users").select("id, email, full_name, phone, role, is_active, created_at", count="exact").order("created_at", desc=True)
    if search: q = q.or_(f"email.ilike.%{search}%,full_name.ilike.%{search}%")
    if role_filter: q = q.eq("role", role_filter)
    
    try: result = q.range(offset, offset + page_size - 1).execute()
    except Exception: raise HTTPException(500, "Failed to fetch users")

    total = result.count if result and hasattr(result, "count") and result.count else 0
    items = result.data if result and hasattr(result, "data") and result.data else []
    return {"items": items, "total": total, "page": page, "page_size": page_size, "pages": -(-total // page_size) if page_size > 0 else 0}

@router.patch("/{user_id}", dependencies=[Depends(require_admin)])
def admin_update_user(request: Request, user_id: UUID, payload: AdminUserUpdate, current: dict[str, Any] = Depends(require_admin)):
    if hasattr(request.state, "actions"): request.state.actions.append(f"Admin modifying user: {str(user_id)[:8]}...")
    sb = get_admin_supabase()
    admin_id = _get_user_id(current)

    if str(user_id) == str(admin_id):
        if payload.role and payload.role != "admin": raise HTTPException(status_code=403, detail="You cannot change your own role")
        if payload.is_active is False: raise HTTPException(status_code=403, detail="You cannot deactivate your own account")

    data = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not data: raise HTTPException(400, "No fields to update")

    existing = sb.table("users").select("id, email, role, is_active").eq("id", str(user_id)).limit(1).execute()
    if not existing or not hasattr(existing, "data") or not existing.data: raise HTTPException(404, "User not found")

    try: result = sb.table("users").update(data).eq("id", str(user_id)).execute()
    except Exception: raise HTTPException(500, "Failed to update user")

    old_role, old_active = existing.data[0].get("role", "?"), existing.data[0].get("is_active", "?")
    _audit_log("USER_UPDATED", admin_id, str(user_id), f"role: {old_role}→{data.get('role', old_role)}, active: {old_active}→{data.get('is_active', old_active)}")
    
    if hasattr(request.state, "actions"): request.state.actions.append("User role/status successfully updated in database")
    return result.data[0]

@router.get("/{user_id}", dependencies=[Depends(require_admin)])
def get_user_detail(request: Request, user_id: UUID):
    if hasattr(request.state, "actions"): request.state.actions.append(f"Admin fetching details for user: {str(user_id)[:8]}...")
    sb = get_admin_supabase()
    
    user = sb.table("users").select("id, email, full_name, phone, role, is_active, created_at").eq("id", str(user_id)).limit(1).execute()
    if not user or not hasattr(user, "data") or not user.data: raise HTTPException(404, "User not found")
    
    try:
        order_count = sb.table("orders").select("id", count="exact").eq("customer_id", str(user_id)).limit(1).execute()
        total_orders = order_count.count if order_count and hasattr(order_count, "count") and order_count.count else 0
    except Exception: total_orders = 0
    
    result = user.data[0]
    result["total_orders"] = total_orders
    return result
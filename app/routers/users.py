"""
Users Router — Production Grade
================================
Changes from original:
  1. FIXED: All .maybe_single() replaced with strict .limit(1) for PostgREST 406 protection.
  2. FIXED: Safe _get_user_id() extraction to prevent KeyError crashes.
  3. FIXED: Comprehensive NoneType checks on all Supabase responses.
  4. FIXED: Memory leak prevented on exact count queries.
  5. ADDED: Admin cannot delete/disable themselves.
  6. ADDED: Address count limit enforcement.
  7. ADDED: Active order check before address deletion.
  8. ADDED: Phone number format validation.
  9. ADDED: Audit logging for admin actions.
  10. NEW: Pure Window Logger integration for clear terminal tracking.
"""
import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, status, Depends, Query, Request
from pydantic import BaseModel, Field, field_validator
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.dependencies import get_current_user, require_admin
from app.supabase_client import get_admin_supabase
from app.repositories.user_repo import UserRepository

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/users", tags=["Users"])

# ── Constants ─────────────────────────────────────────────────────────────────
MAX_ADDRESSES_PER_USER = 10

# ── Rate limiter ──────────────────────────────────────────────────────────────
limiter = Limiter(key_func=get_remote_address)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_user_id(current_user: dict[str, Any]) -> str:
    """Safely extract user_id from the current user object/token payload."""
    if "profile" in current_user and isinstance(current_user["profile"], dict) and "id" in current_user["profile"]:
        return str(current_user["profile"]["id"])
    if "id" in current_user:
        return str(current_user["id"])
    if "sub" in current_user:
        return str(current_user["sub"])
        
    logger.error(f"Cannot find user ID in session keys: {list(current_user.keys())}")
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED, 
        detail="User ID not found in session"
    )


def _audit_log(action: str, admin_id: str, target_user_id: str = "", details: str = ""):
    """Log admin actions for audit trail"""
    logger.info(
        "AUDIT | action=%s admin=%.8s target=%.8s | %s",
        action, admin_id, target_user_id, details
    )


def _is_admin(current_user: dict[str, Any]) -> bool:
    """Check if current user has admin role"""
    profile = current_user.get("profile", {})
    return profile.get("role") == "admin"


# ── Models ────────────────────────────────────────────────────────────────────

class ProfileUpdate(BaseModel):
    full_name: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=20)

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: str | None) -> str | None:
        if v is not None:
            cleaned = ''.join(c for c in v if c.isdigit() or c == '+')
            if len(cleaned.replace('+', '')) < 10:
                raise ValueError("Phone number must be at least 10 digits")
            return cleaned
        return v


class AddressCreate(BaseModel):
    line1: str = Field(max_length=255)
    line2: str | None = Field(default=None, max_length=255)
    city: str = Field(max_length=100)
    state: str | None = Field(default=None, max_length=100)
    postal_code: str = Field(max_length=20)
    country: str = Field(min_length=2, max_length=2)
    is_default: bool = False

    @field_validator("country")
    @classmethod
    def validate_country(cls, v: str) -> str:
        return v.upper()

    @field_validator("postal_code")
    @classmethod
    def validate_postal(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Postal code is required")
        return v.strip()


class AdminUserUpdate(BaseModel):
    is_active: bool | None = None
    role: str | None = Field(default=None, pattern="^(customer|admin)$")


# ══════════════════════════════════════════════════════════════════════════════
#  PROFILE ENDPOINTS
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/me")
def get_me(
    request: Request,
    current: dict[str, Any] = Depends(get_current_user)
) -> dict[str, Any]:
    """Get current user's profile."""
    if hasattr(request.state, "actions"):
        request.state.actions.append("Fetching current user profile")
        
    profile = current.get("profile", current)
    
    safe_fields = {"id", "email", "full_name", "phone", "role", "is_active", "created_at"}
    return {k: v for k, v in profile.items() if k in safe_fields}


@router.patch("/me")
@limiter.limit("20/minute")
def update_me(
    request: Request,
    payload: ProfileUpdate,
    current: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Update current user's profile."""
    if hasattr(request.state, "actions"):
        request.state.actions.append("Processing profile update request")
        
    sb = get_admin_supabase()
    repo = UserRepository(sb)
    
    user_id = _get_user_id(current)
    
    data = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not data:
        return current.get("profile", current)
    
    try:
        updated = repo.update_profile(user_id, data)
        logger.info("Profile updated | user=%.8s fields=%s", user_id, list(data.keys()))
        
        if hasattr(request.state, "actions"):
            request.state.actions.append(f"Successfully updated fields: {', '.join(data.keys())}")
            
        return updated or current.get("profile", current)
    except Exception as exc:
        logger.error("Profile update failed | user=%.8s: %s", user_id, exc)
        raise HTTPException(500, "Failed to update profile")


# ══════════════════════════════════════════════════════════════════════════════
#  ADDRESS ENDPOINTS
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/me/addresses")
def list_addresses(
    request: Request,
    current: dict[str, Any] = Depends(get_current_user),
) -> list[dict[str, Any]]:
    """List current user's saved addresses."""
    if hasattr(request.state, "actions"):
        request.state.actions.append("Fetching user's saved addresses")
        
    sb = get_admin_supabase()
    user_id = _get_user_id(current)
    
    try:
        res = (
            sb.table("addresses")
            .select("*")
            .eq("user_id", user_id)
            .order("is_default", desc=True)
            .order("created_at", desc=True)
            .limit(MAX_ADDRESSES_PER_USER)
            .execute()
        )
        return res.data if res and hasattr(res, "data") and res.data else []
    except Exception as exc:
        logger.error("Failed to list addresses | user=%.8s: %s", user_id, exc)
        raise HTTPException(500, "Failed to fetch addresses")


@router.post("/me/addresses", status_code=status.HTTP_201_CREATED)
@limiter.limit("10/minute")
def add_address(
    request: Request,
    payload: AddressCreate,
    current: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Add a new shipping address."""
    if hasattr(request.state, "actions"):
        request.state.actions.append("Initiating new shipping address creation")
        
    sb = get_admin_supabase()
    user_id = _get_user_id(current)

    try:
        count_res = (
            sb.table("addresses")
            .select("id", count="exact")
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
        current_count = count_res.count if count_res and hasattr(count_res, "count") and count_res.count else 0
    except Exception as exc:
        logger.error("Address count failed | user=%.8s: %s", user_id, exc)
        raise HTTPException(500, "Failed to verify address limit")

    if hasattr(request.state, "actions"):
        request.state.actions.append(f"Current address count: {current_count}/{MAX_ADDRESSES_PER_USER}")

    if current_count >= MAX_ADDRESSES_PER_USER:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Maximum {MAX_ADDRESSES_PER_USER} addresses allowed. Please delete one first.",
        )

    should_be_default = payload.is_default or current_count == 0

    if should_be_default:
        try:
            sb.table("addresses").update({"is_default": False}).eq("user_id", user_id).execute()
        except Exception as exc:
            logger.warning("Failed to unset default addresses | user=%.8s: %s", user_id, exc)

    try:
        res = (
            sb.table("addresses")
            .insert({
                **payload.model_dump(),
                "user_id": user_id,
                "is_default": should_be_default,
            })
            .execute()
        )
    except Exception as exc:
        logger.error("Address insert failed | user=%.8s: %s", user_id, exc)
        raise HTTPException(500, "Failed to add address")

    if not res or not hasattr(res, "data") or not res.data:
        raise HTTPException(500, "Failed to add address")

    if hasattr(request.state, "actions"):
        request.state.actions.append(f"New address saved successfully (Default: {should_be_default})")

    logger.info(
        "Address added | user=%.8s addr=%.8s default=%s", 
        user_id, res.data[0]["id"], should_be_default
    )
    return res.data[0]


@router.delete("/me/addresses/{address_id}")
def delete_address(
    request: Request,
    address_id: UUID,
    current: dict[str, Any] = Depends(get_current_user),
) -> dict[str, str]:
    """Delete a shipping address."""
    if hasattr(request.state, "actions"):
        request.state.actions.append(f"Validating address deletion: {str(address_id)[:8]}...")
        
    sb = get_admin_supabase()
    user_id = _get_user_id(current)

    existing = (
        sb.table("addresses")
        .select("id, is_default")
        .eq("id", str(address_id))
        .eq("user_id", user_id)
        .limit(1)
        .execute()
    )
    
    if not existing or not hasattr(existing, "data") or not existing.data:
        raise HTTPException(404, "Address not found")

    was_default = existing.data[0].get("is_default", False)

    try:
        active = (
            sb.table("orders")
            .select("id")
            .eq("shipping_address_id", str(address_id))
            .in_("status", ["pending", "paid", "shipped"])
            .limit(1)
            .execute()
        )
        
        if active and hasattr(active, "data") and active.data:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Cannot delete — this address is used in an active order.",
            )
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("Active order check failed | addr=%.8s: %s", address_id, exc)

    if hasattr(request.state, "actions"):
        request.state.actions.append("No active orders found for this address. Proceeding.")

    try:
        sb.table("addresses").delete().eq("id", str(address_id)).execute()
    except Exception as exc:
        logger.error("Address delete failed | addr=%.8s: %s", address_id, exc)
        raise HTTPException(500, "Failed to delete address")

    if was_default:
        try:
            remaining = (
                sb.table("addresses")
                .select("id")
                .eq("user_id", user_id)
                .limit(1)
                .execute()
            )
            if remaining and hasattr(remaining, "data") and remaining.data:
                sb.table("addresses").update({"is_default": True}).eq("id", remaining.data[0]["id"]).execute()
        except Exception as exc:
            logger.warning("Failed to set new default | user=%.8s: %s", user_id, exc)

    if hasattr(request.state, "actions"):
        request.state.actions.append("Address successfully deleted")

    logger.info("Address deleted | user=%.8s addr=%.8s", user_id, address_id)
    return {"message": "Address deleted successfully"}


# ══════════════════════════════════════════════════════════════════════════════
#  ADMIN ENDPOINTS
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/", dependencies=[Depends(require_admin)])
def list_users(
    request: Request,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: str | None = Query(None, max_length=100),
    role_filter: str | None = Query(None, pattern="^(customer|admin)$"),
) -> dict[str, Any]:
    """Admin: List all users with optional search and role filter."""
    if hasattr(request.state, "actions"):
        request.state.actions.append(f"Admin listing users (Page: {page})")
        
    sb = get_admin_supabase()
    offset = (page - 1) * page_size
    
    q = (
        sb.table("users")
        .select("id, email, full_name, phone, role, is_active, created_at", count="exact")
        .order("created_at", desc=True)
    )
    
    if search:
        q = q.or_(f"email.ilike.%{search}%,full_name.ilike.%{search}%")
        
    if role_filter:
        q = q.eq("role", role_filter)
    
    try:
        result = q.range(offset, offset + page_size - 1).execute()
    except Exception as exc:
        logger.error("User list failed: %s", exc)
        raise HTTPException(500, "Failed to fetch users")

    total = result.count if result and hasattr(result, "count") and result.count else 0
    items = result.data if result and hasattr(result, "data") and result.data else []
    
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": -(-total // page_size) if page_size > 0 else 0,
    }


@router.patch("/{user_id}", dependencies=[Depends(require_admin)])
def admin_update_user(
    request: Request,
    user_id: UUID,
    payload: AdminUserUpdate,
    current: dict[str, Any] = Depends(require_admin),
) -> dict[str, Any]:
    """Admin: Update user role or active status."""
    if hasattr(request.state, "actions"):
        request.state.actions.append(f"Admin modifying user: {str(user_id)[:8]}...")
        
    sb = get_admin_supabase()
    admin_id = _get_user_id(current)

    if str(user_id) == str(admin_id):
        if payload.role and payload.role != "admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You cannot change your own role",
            )
        if payload.is_active is False:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You cannot deactivate your own account",
            )

    data = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not data:
        raise HTTPException(400, "No fields to update")

    existing = (
        sb.table("users")
        .select("id, email, role, is_active")
        .eq("id", str(user_id))
        .limit(1)
        .execute()
    )
    if not existing or not hasattr(existing, "data") or not existing.data:
        raise HTTPException(404, "User not found")

    try:
        result = sb.table("users").update(data).eq("id", str(user_id)).execute()
    except Exception as exc:
        logger.error("Admin user update failed | target=%.8s: %s", user_id, exc)
        raise HTTPException(500, "Failed to update user")

    if not result or not hasattr(result, "data") or not result.data:
        raise HTTPException(404, "User not found")

    old_role = existing.data[0].get("role", "?")
    old_active = existing.data[0].get("is_active", "?")
    _audit_log(
        "USER_UPDATED", admin_id, str(user_id),
        f"role: {old_role}→{data.get('role', old_role)}, "
        f"active: {old_active}→{data.get('is_active', old_active)}"
    )
    
    if hasattr(request.state, "actions"):
        request.state.actions.append("User role/status successfully updated in database")

    return result.data[0]


@router.get("/{user_id}", dependencies=[Depends(require_admin)])
def get_user_detail(
    request: Request,
    user_id: UUID,
) -> dict[str, Any]:
    """Admin: Get single user details including order count."""
    if hasattr(request.state, "actions"):
        request.state.actions.append(f"Admin fetching details for user: {str(user_id)[:8]}...")
        
    sb = get_admin_supabase()
    
    user = (
        sb.table("users")
        .select("id, email, full_name, phone, role, is_active, created_at")
        .eq("id", str(user_id))
        .limit(1)
        .execute()
    )
    
    if not user or not hasattr(user, "data") or not user.data:
        raise HTTPException(404, "User not found")
    
    try:
        order_count = (
            sb.table("orders")
            .select("id", count="exact")
            .eq("customer_id", str(user_id))
            .limit(1)
            .execute()
        )
        total_orders = order_count.count if order_count and hasattr(order_count, "count") and order_count.count else 0
    except Exception:
        total_orders = 0
    
    result = user.data[0]
    result["total_orders"] = total_orders
    
    return result

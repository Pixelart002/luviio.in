"""
Users Router — Production Grade
================================
Changes from original:
  1. FIXED: All .single() → .maybe_single() throughout
  2. FIXED: Safe _get_user_id() extraction to prevent KeyError crashes
  3. FIXED: Comprehensive NoneType checks on all Supabase responses
  4. ADDED: Admin cannot delete/disable themselves
  5. ADDED: Address count limit enforcement
  6. ADDED: Active order check before address deletion
  7. ADDED: Phone number format validation
  8. ADDED: Audit logging for admin actions
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
        
    logger.error(f"Cannot find user ID in: {list(current_user.keys())}")
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User ID not found in session")


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
            # Basic phone validation (Indian format)
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
def get_me(current: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    """
    Get current user's profile.
    Returns nested profile if available, otherwise top-level user data.
    """
    profile = current.get("profile", current)
    
    # 🔥 Strip sensitive internal fields
    safe_fields = {"id", "email", "full_name", "phone", "role", "is_active", "created_at"}
    return {k: v for k, v in profile.items() if k in safe_fields}


@router.patch("/me")
@limiter.limit("20/minute")
def update_me(
    request: Request,
    payload: ProfileUpdate,
    current: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """
    Update current user's profile.
    Only full_name and phone can be updated by the user.
    """
    sb = get_admin_supabase()
    repo = UserRepository(sb)
    
    # Safe user ID extraction
    user_id = _get_user_id(current)
    
    data = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not data:
        return current.get("profile", current)
    
    try:
        updated = repo.update_profile(user_id, data)
        logger.info("Profile updated | user=%.8s fields=%s", user_id, list(data.keys()))
        return updated or current.get("profile", current)
    except Exception as exc:
        logger.error("Profile update failed | user=%.8s: %s", user_id, exc)
        raise HTTPException(500, "Failed to update profile")


# ══════════════════════════════════════════════════════════════════════════════
#  ADDRESS ENDPOINTS
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/me/addresses")
def list_addresses(
    current: dict[str, Any] = Depends(get_current_user),
) -> list[dict[str, Any]]:
    """
    List current user's saved addresses.
    Ordered by default first, then most recently created.
    """
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
    """
    Add a new shipping address.
    Auto-sets as default if it's the first address.
    Max 10 addresses per user.
    """
    sb = get_admin_supabase()
    user_id = _get_user_id(current)

    # ── Count existing addresses ──────────────────────────────────────────────
    try:
        count_res = (
            sb.table("addresses")
            .select("id", count="exact")
            .eq("user_id", user_id)
            .execute()
        )
        current_count = count_res.count if count_res and hasattr(count_res, "count") and count_res.count else 0
    except Exception as exc:
        logger.error("Address count failed | user=%.8s: %s", user_id, exc)
        raise HTTPException(500, "Failed to verify address limit")

    if current_count >= MAX_ADDRESSES_PER_USER:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Maximum {MAX_ADDRESSES_PER_USER} addresses allowed per user. Please delete an existing address first.",
        )

    # ── If this is the first address, auto-set as default ─────────────────────
    should_be_default = payload.is_default or current_count == 0

    # ── Unset other defaults if this is default ───────────────────────────────
    if should_be_default:
        try:
            sb.table("addresses").update({"is_default": False}).eq("user_id", user_id).execute()
        except Exception as exc:
            logger.warning("Failed to unset default addresses | user=%.8s: %s", user_id, exc)

    # ── Insert new address ────────────────────────────────────────────────────
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

    logger.info("Address added | user=%.8s addr=%.8s default=%s", user_id, res.data[0]["id"], should_be_default)
    return res.data[0]


@router.delete("/me/addresses/{address_id}")
def delete_address(
    address_id: UUID,
    current: dict[str, Any] = Depends(get_current_user),
) -> dict[str, str]:
    """
    Delete a shipping address.
    Cannot delete if used in active order (pending/paid/shipped).
    """
    sb = get_admin_supabase()
    user_id = _get_user_id(current)

    # ── Verify ownership ───────────────────────────────────────────────────────
    existing = (
        sb.table("addresses")
        .select("id, is_default")
        .eq("id", str(address_id))
        .eq("user_id", user_id)
        .maybe_single()
        .execute()
    )
    
    if not existing or not hasattr(existing, "data") or not existing.data:
        raise HTTPException(404, "Address not found")

    # ── Check active orders ────────────────────────────────────────────────────
    try:
        active = (
            sb.table("orders")
            .select("id")
            .eq("shipping_address_id", str(address_id))
            .in_("status", ["pending", "paid", "shipped"])
            .execute()
        )
        
        if active and hasattr(active, "data") and active.data:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Cannot delete — this address is used in an active order. Please wait until the order is delivered or cancelled.",
            )
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("Active order check failed | addr=%.8s: %s", address_id, exc)
        # Continue with deletion on check failure (non-critical)

    # ── Delete address ─────────────────────────────────────────────────────────
    try:
        was_default = existing.data.get("is_default", False)
        sb.table("addresses").delete().eq("id", str(address_id)).execute()
    except Exception as exc:
        logger.error("Address delete failed | addr=%.8s: %s", address_id, exc)
        raise HTTPException(500, "Failed to delete address")

    # ── If deleted address was default, set a new default ─────────────────────
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

    logger.info("Address deleted | user=%.8s addr=%.8s", user_id, address_id)
    return {"message": "Address deleted successfully"}


# ══════════════════════════════════════════════════════════════════════════════
#  ADMIN ENDPOINTS
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/", dependencies=[Depends(require_admin)])
def list_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: str | None = Query(None, max_length=100),
    role_filter: str | None = Query(None, pattern="^(customer|admin)$"),
) -> dict[str, Any]:
    """
    Admin: List all users with optional search and role filter.
    """
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
    user_id: UUID,
    payload: AdminUserUpdate,
    current: dict[str, Any] = Depends(require_admin),
) -> dict[str, Any]:
    """
    Admin: Update user role or active status.
    
    Safety: Admin cannot change their own role.
    """
    sb = get_admin_supabase()
    admin_id = _get_user_id(current)

    # ── Self-protection ───────────────────────────────────────────────────────
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

    # ── Verify user exists ────────────────────────────────────────────────────
    existing = (
        sb.table("users")
        .select("id, email, role, is_active")
        .eq("id", str(user_id))
        .maybe_single()
        .execute()
    )
    if not existing or not hasattr(existing, "data") or not existing.data:
        raise HTTPException(404, "User not found")

    # ── Update ────────────────────────────────────────────────────────────────
    try:
        result = sb.table("users").update(data).eq("id", str(user_id)).execute()
    except Exception as exc:
        logger.error("Admin user update failed | target=%.8s: %s", user_id, exc)
        raise HTTPException(500, "Failed to update user")

    if not result or not hasattr(result, "data") or not result.data:
        raise HTTPException(404, "User not found")

    # ── Audit log ─────────────────────────────────────────────────────────────
    old_role = existing.data.get("role", "?")
    old_active = existing.data.get("is_active", "?")
    _audit_log(
        "USER_UPDATED", admin_id, str(user_id),
        f"role: {old_role}→{data.get('role', old_role)}, "
        f"active: {old_active}→{data.get('is_active', old_active)}"
    )

    return result.data[0]


@router.get("/{user_id}", dependencies=[Depends(require_admin)])
def get_user_detail(
    user_id: UUID,
) -> dict[str, Any]:
    """
    Admin: Get single user details including order count.
    """
    sb = get_admin_supabase()
    
    user = (
        sb.table("users")
        .select("id, email, full_name, phone, role, is_active, created_at")
        .eq("id", str(user_id))
        .maybe_single()
        .execute()
    )
    
    if not user or not hasattr(user, "data") or not user.data:
        raise HTTPException(404, "User not found")
    
    # Count orders for this user
    try:
        order_count = (
            sb.table("orders")
            .select("id", count="exact")
            .eq("customer_id", str(user_id))
            .execute()
        )
        total_orders = order_count.count if order_count and hasattr(order_count, "count") else 0
    except Exception:
        total_orders = 0
    
    result = user.data
    result["total_orders"] = total_orders
    
    return result
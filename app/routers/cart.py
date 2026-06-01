"""
Cart Router with Built-in Pricing
==================================
Endpoints:
  GET    /api/v1/cart                         — get cart with live pricing
  POST   /api/v1/cart/items                   — add / upsert item
  PUT    /api/v1/cart/items/{product_id}      — set quantity for one item
  DELETE /api/v1/cart/items/{product_id}      — remove one item
  DELETE /api/v1/cart                         — clear entire cart

Admin:
  GET    /api/v1/cart/admin/abandoned         — carts with items not updated in 24h
  POST   /api/v1/cart/admin/remind/{cart_id} — push + email reminder to cart owner

Design notes:
  • One cart per user (UNIQUE constraint on carts.user_id).
  • price_snapshot stored per item = price at time of adding.
  • Pricing breakdown (shipping/tax) calculated from pricing_config table —
    SINGLE source of truth, same as admin settings panel.
  • Abandoned cart = has items AND updated_at < 24h ago.
"""
from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.dependencies import get_current_user, require_admin
from app.supabase_client import get_admin_supabase
from app.utils.push import send_push_to_user
from app.utils.email import send_cart_reminder_email

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/cart", tags=["Cart"])

_ABANDONED_HOURS = 24


# ── Schemas ───────────────────────────────────────────────────────────────────

class AddItemRequest(BaseModel):
    product_id: UUID
    quantity: int = Field(ge=1, le=100)


class UpdateItemRequest(BaseModel):
    quantity: int = Field(ge=1, le=100)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_user_id(current: dict[str, Any]) -> str:
    profile = current.get("profile")
    if isinstance(profile, dict) and "id" in profile:
        return str(profile["id"])
    if "id" in current:
        return str(current["id"])
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User ID not found")


def _fetch_pricing_config(sb: Any) -> dict[str, Any]:
    """
    Fetch pricing configuration from Supabase.
    SINGLE SOURCE OF TRUTH — same table admin settings panel writes to.
    """
    try:
        res = (
            sb.table("pricing_config")
            .select("*")
            .limit(1)
            .single()
            .execute()
        )
        if res and res.data:
            return res.data
    except Exception as e:
        logger.warning("pricing_config fetch failed, using defaults: %s", e)

    # Fallback defaults
    return {
        "tax_rate": 18.0,
        "shipping_flat": 99.0,
        "shipping_threshold": 999.0,
        "currency": "INR",
        "tax_enabled": True,
        "shipping_enabled": True,
    }


def _get_or_create_cart(sb: Any, user_id: str) -> dict[str, Any]:
    """Fetch or create cart for user."""
    sb.table("carts").upsert(
        {"user_id": user_id}, on_conflict="user_id", ignore_duplicates=True
    ).execute()

    fetch = (
        sb.table("carts")
        .select("*")
        .eq("user_id", user_id)
        .limit(1)
        .execute()
    )
    if not fetch or not getattr(fetch, "data", None):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not get or create cart",
        )
    return fetch.data[0]


def _calculate_cart_pricing(sb: Any, cart: dict[str, Any]) -> dict[str, Any]:
    """
    Load cart items + calculate pricing using pricing_config table.
    EXACT same logic that was in /pricing/calculate endpoint.
    """
    # ── 1. Fetch pricing config ──────────────────────────────────────────
    config = _fetch_pricing_config(sb)

    tax_rate = Decimal(str(config["tax_rate"])) / Decimal("100")
    shipping_flat = Decimal(str(config["shipping_flat"]))
    shipping_threshold = Decimal(str(config["shipping_threshold"]))
    tax_enabled = config.get("tax_enabled", True)
    shipping_enabled = config.get("shipping_enabled", True)

    # ── 2. Fetch cart items with product details ─────────────────────────
    items_res = (
        sb.table("cart_items")
        .select(
            "id, product_id, quantity, price_snapshot, added_at, "
            "products(id, name, slug, price, stock, image_url, is_active)"
        )
        .eq("cart_id", cart["id"])
        .order("added_at", desc=False)
        .execute()
    )

    raw_items: list[dict[str, Any]] = getattr(items_res, "data", None) or []

    # ── 3. Enrich items + calculate subtotal ─────────────────────────────
    enriched: list[dict[str, Any]] = []
    subtotal = Decimal("0")
    has_unavailable = False

    for row in raw_items:
        prod = row.get("products") or {}
        qty = row["quantity"]
        snapshot = Decimal(str(row["price_snapshot"]))
        current_price = Decimal(str(prod.get("price", snapshot)))
        line_total = current_price * qty
        subtotal += line_total

        in_stock = (
            prod.get("is_active", True)
            and prod.get("stock", 0) >= qty
        )
        price_changed = abs(float(current_price) - float(snapshot)) > 0.001

        if not in_stock:
            has_unavailable = True

        enriched.append({
            "id": row["id"],
            "product_id": row["product_id"],
            "name": prod.get("name", ""),
            "slug": prod.get("slug", ""),
            "image_url": prod.get("image_url"),
            "quantity": qty,
            "unit_price": float(current_price),
            "price_snapshot": float(snapshot),
            "line_total": float(line_total),
            "stock": prod.get("stock", 0),
            "in_stock": in_stock,
            "is_active": prod.get("is_active", True),
            "price_changed": price_changed,
            "added_at": row["added_at"],
        })

    # ── 4. Calculate shipping (same as /pricing/calculate) ───────────────
    shipping = Decimal("0")
    if shipping_enabled and subtotal < shipping_threshold:
        shipping = shipping_flat

    # ── 5. Calculate tax (same as /pricing/calculate) ────────────────────
    tax = Decimal("0")
    if tax_enabled:
        tax = (subtotal + shipping) * tax_rate

    # ── 6. Calculate total ───────────────────────────────────────────────
    total = subtotal + shipping + tax

    # ── 7. Free shipping progress ────────────────────────────────────────
    amount_to_free = 0.0
    if shipping_enabled and shipping > 0:
        amount_to_free = max(0.0, float(shipping_threshold - subtotal))

    # ── 8. Return full cart response ─────────────────────────────────────
    return {
        "cart_id": cart["id"],
        "user_id": cart["user_id"],
        "updated_at": cart["updated_at"],
        "items": enriched,
        "item_count": len(enriched),
        "subtotal": round(float(subtotal), 2),
        "shipping_cost": round(float(shipping), 2),
        "tax_amount": round(float(tax), 2),
        "total_amount": round(float(total), 2),
        "free_shipping_eligible": shipping == 0,
        "amount_to_free_shipping": round(amount_to_free, 2),
        "free_shipping_threshold": float(shipping_threshold),
        "tax_rate_pct": float(config["tax_rate"]),
        "has_unavailable_items": has_unavailable,
        "currency": config.get("currency", "INR"),
    }


# ══════════════════════════════════════════════════════════════════════════════
#  CUSTOMER ENDPOINTS
# ══════════════════════════════════════════════════════════════════════════════

@router.get("")
def get_cart(current: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    """Get cart with live pricing from pricing_config table."""
    sb = get_admin_supabase()
    user_id = _get_user_id(current)
    cart = _get_or_create_cart(sb, user_id)
    return _calculate_cart_pricing(sb, cart)


@router.post("/items", status_code=status.HTTP_200_OK)
def add_item(
    payload: AddItemRequest,
    current: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Add item to cart or increase quantity if already present."""
    sb = get_admin_supabase()
    user_id = _get_user_id(current)
    product_id = str(payload.product_id)

    # Verify product
    prod_res = (
        sb.table("products")
        .select("id, name, price, stock, is_active")
        .eq("id", product_id)
        .eq("is_active", True)
        .limit(1)
        .execute()
    )
    if not prod_res or not getattr(prod_res, "data", None):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found or inactive")

    prod = prod_res.data[0]
    if prod["stock"] < payload.quantity:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Only {prod['stock']} units available")

    cart = _get_or_create_cart(sb, user_id)

    # Check existing
    existing_res = (
        sb.table("cart_items")
        .select("id, quantity")
        .eq("cart_id", cart["id"])
        .eq("product_id", product_id)
        .limit(1)
        .execute()
    )
    existing = getattr(existing_res, "data", None) or []

    if existing:
        new_qty = existing[0]["quantity"] + payload.quantity
        if new_qty > 100:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Maximum 100 units per item")
        if prod["stock"] < new_qty:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Only {prod['stock']} units available (you already have {existing[0]['quantity']} in cart)",
            )
        sb.table("cart_items").update({"quantity": new_qty}).eq("id", existing[0]["id"]).execute()
    else:
        sb.table("cart_items").insert({
            "cart_id": cart["id"],
            "product_id": product_id,
            "quantity": payload.quantity,
            "price_snapshot": float(prod["price"]),
        }).execute()

    cart = _get_or_create_cart(sb, user_id)
    return _calculate_cart_pricing(sb, cart)


@router.put("/items/{product_id}", status_code=status.HTTP_200_OK)
def update_item(
    product_id: UUID,
    payload: UpdateItemRequest,
    current: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Set exact quantity for a cart item."""
    sb = get_admin_supabase()
    user_id = _get_user_id(current)
    pid = str(product_id)
    cart = _get_or_create_cart(sb, user_id)

    prod_res = (
        sb.table("products")
        .select("stock, is_active")
        .eq("id", pid)
        .limit(1)
        .execute()
    )
    prod = (getattr(prod_res, "data", None) or [{}])[0]
    if not prod.get("is_active", True):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    if prod.get("stock", 0) < payload.quantity:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Only {prod['stock']} units available")

    update_res = (
        sb.table("cart_items")
        .update({"quantity": payload.quantity})
        .eq("cart_id", cart["id"])
        .eq("product_id", pid)
        .execute()
    )
    if not getattr(update_res, "data", None):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not in cart")

    cart = _get_or_create_cart(sb, user_id)
    return _calculate_cart_pricing(sb, cart)


@router.delete("/items/{product_id}", status_code=status.HTTP_200_OK)
def remove_item(
    product_id: UUID,
    current: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Remove single item from cart."""
    sb = get_admin_supabase()
    user_id = _get_user_id(current)
    pid = str(product_id)
    cart = _get_or_create_cart(sb, user_id)

    sb.table("cart_items").delete().eq("cart_id", cart["id"]).eq("product_id", pid).execute()

    cart = _get_or_create_cart(sb, user_id)
    return _calculate_cart_pricing(sb, cart)


@router.delete("", status_code=status.HTTP_200_OK)
def clear_cart(current: dict[str, Any] = Depends(get_current_user)) -> dict[str, str]:
    """Remove all items from cart."""
    sb = get_admin_supabase()
    user_id = _get_user_id(current)
    cart = _get_or_create_cart(sb, user_id)

    sb.table("cart_items").delete().eq("cart_id", cart["id"]).execute()
    logger.info("Cart cleared | user=%.8s", user_id)
    return {"message": "Cart cleared"}


# ══════════════════════════════════════════════════════════════════════════════
#  ADMIN ENDPOINTS
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/admin/abandoned", dependencies=[Depends(require_admin)])
def list_abandoned_carts(
    hours: int = Query(default=_ABANDONED_HOURS, ge=1, le=168),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> dict[str, Any]:
    """List abandoned carts for admin."""
    sb = get_admin_supabase()
    offset = (page - 1) * page_size

    import datetime
    cutoff = (
        datetime.datetime.now(datetime.timezone.utc)
        - datetime.timedelta(hours=hours)
    ).isoformat()

    result = (
        sb.table("carts")
        .select(
            "id, user_id, updated_at, created_at, "
            "cart_items(id, quantity, price_snapshot, product_id), "
            "users(email, full_name)",
            count="exact",
        )
        .lt("updated_at", cutoff)
        .order("updated_at", desc=False)
        .range(offset, offset + page_size - 1)
        .execute()
    )

    all_rows = getattr(result, "data", None) or []
    rows = [r for r in all_rows if r.get("cart_items")]

    for row in rows:
        items = row.get("cart_items", [])
        est_value = sum(Decimal(str(i["price_snapshot"])) * i["quantity"] for i in items)
        row["item_count"] = len(items)
        row["estimated_value"] = float(est_value)

    total = result.count or 0
    return {
        "items": rows,
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": -(-total // page_size) if page_size > 0 else 0,
        "hours_threshold": hours,
    }


@router.post("/admin/remind/{cart_id}", dependencies=[Depends(require_admin)])
def send_cart_reminder(cart_id: UUID) -> dict[str, str]:
    """Send push + email reminder for abandoned cart."""
    sb = get_admin_supabase()

    cart_res = (
        sb.table("carts")
        .select(
            "id, user_id, "
            "cart_items(quantity, price_snapshot, products(name, image_url, slug)), "
            "users(email, full_name)"
        )
        .eq("id", str(cart_id))
        .limit(1)
        .execute()
    )

    if not cart_res or not getattr(cart_res, "data", None):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cart not found")

    cart = cart_res.data[0]
    user_info = cart.get("users") or {}
    items = cart.get("cart_items") or []

    if not items:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cart is empty")

    user_id = cart["user_id"]
    email = user_info.get("email", "")
    name = user_info.get("full_name", "there")

    # Push
    push_sent = 0
    try:
        push_sent = send_push_to_user(
            sb, user_id,
            title="🛒 You left something behind!",
            body=f"Hi {name or 'there'}, your cart has {len(items)} item(s) waiting.",
            icon="/icons/ri-shopping-cart-2.png",
            url="/cart.html",
        )
    except Exception as exc:
        logger.warning("Push failed | cart=%s | %s", str(cart_id)[:8], exc)

    # Email
    email_sent = False
    if email:
        try:
            send_cart_reminder_email(email, name, items)
            email_sent = True
        except Exception as exc:
            logger.warning("Email failed | cart=%s | %s", str(cart_id)[:8], exc)

    logger.info("Reminder sent | cart=%s | push=%d email=%s", str(cart_id)[:8], push_sent, email_sent)

    return {
        "message": "Reminder sent",
        "push_sent": str(push_sent > 0),
        "email_sent": str(email_sent),
    }
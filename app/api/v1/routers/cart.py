"""
Cart Router — Enterprise Grade
===============================
Path: app/api/v1/routers/cart.py

Architecture Upgrades:
  1. ALL Supabase DB logic moved to CartRepository.
  2. Pricing logic strictly delegated to Central Pricing Engine.
  3. Clean separation of concerns.
"""
from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
import datetime

# 🔥 ARCHITECTURE IMPORTS
from app.core.dependencies import get_current_user, require_admin
from app.api.schemas.cart_dto import (
    AddItemRequest, UpdateItemRequest, CartResponse, 
    MessageResponse, AbandonedCartResponse, ReminderResponse
)
from app.repositories.cart_repo import CartRepository
from app.services.pricing import get_pricing_from_config
from app.integrations.push.webpush_impl import send_push_to_user
from app.integrations.email.registry import get_email_provider

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/cart", tags=["Cart"])

_ABANDONED_HOURS = 24

# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_user_id(current: dict[str, Any]) -> str:
    profile = current.get("profile", {})
    user_id = profile.get("id") or current.get("id") or current.get("sub")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User ID not found")
    return str(user_id)

def _calculate_cart_pricing(repo: CartRepository, cart: dict[str, Any]) -> dict[str, Any]:
    """Calculate cart using the central PricingEngine."""
    config = repo.get_pricing_config()
    pricing_engine = get_pricing_from_config(config)

    raw_items = repo.get_cart_items_with_products(cart["id"])
    enriched, subtotal, has_unavailable = [], Decimal("0"), False

    for row in raw_items:
        prod = row.get("products") or {}
        qty = row["quantity"]
        snapshot = Decimal(str(row["price_snapshot"]))
        current_price = Decimal(str(prod.get("price", snapshot)))
        line_total = current_price * qty
        subtotal += line_total

        in_stock = prod.get("is_active", True) and prod.get("stock", 0) >= qty
        price_changed = abs(float(current_price) - float(snapshot)) > 0.001

        if not in_stock: has_unavailable = True

        enriched.append({
            "id": row["id"], "product_id": row["product_id"],
            "name": prod.get("name", ""), "slug": prod.get("slug", ""),
            "image_url": prod.get("image_url"), "quantity": qty,
            "unit_price": float(current_price), "price_snapshot": float(snapshot),
            "line_total": float(line_total), "stock": prod.get("stock", 0),
            "in_stock": in_stock, "is_active": prod.get("is_active", True),
            "price_changed": price_changed, "added_at": row["added_at"],
        })

    breakdown = pricing_engine.calculate(subtotal)
    amount_to_free = max(0.0, float(pricing_engine.shipping_threshold) - float(subtotal)) if pricing_engine.shipping_enabled and subtotal < pricing_engine.shipping_threshold else 0.0

    return {
        "items": enriched, "item_count": len(enriched),
        "subtotal": breakdown.subtotal, "shipping_cost": breakdown.shipping_cost,
        "tax_amount": breakdown.tax_amount, "total_amount": breakdown.total_amount,
        "free_shipping_eligible": breakdown.shipping_cost == 0 and subtotal > 0,
        "amount_to_free_shipping": round(amount_to_free, 2),
        "free_shipping_threshold": float(pricing_engine.shipping_threshold),
        "tax_rate_pct": float(pricing_engine.tax_rate * 100),
        "has_unavailable_items": has_unavailable, "currency": pricing_engine.currency,
    }


# ══════════════════════════════════════════════════════════════════════════════
#  CUSTOMER ENDPOINTS
# ══════════════════════════════════════════════════════════════════════════════

@router.get("", response_model=CartResponse)
def get_cart(request: Request, current: dict[str, Any] = Depends(get_current_user)):
    user_id = _get_user_id(current)
    repo = CartRepository()
    
    if hasattr(request.state, "actions"): request.state.actions.extend(["Fetching active cart via Repo", "Applying live SSOT pricing rules"])
    
    cart = repo.get_or_create_cart(user_id)
    return _calculate_cart_pricing(repo, cart)

@router.post("/items", status_code=status.HTTP_200_OK, response_model=CartResponse)
def add_item(request: Request, payload: AddItemRequest, current: dict[str, Any] = Depends(get_current_user)):
    user_id = _get_user_id(current)
    product_id = str(payload.product_id)
    repo = CartRepository()
    
    if hasattr(request.state, "actions"): request.state.actions.append(f"Verifying stock for product: {product_id[:8]}...")

    prod = repo.get_product_stock_status(product_id)
    if not prod or not prod.get("is_active"): raise HTTPException(404, "Product not found or inactive")
    if prod["stock"] < payload.quantity: raise HTTPException(409, f"Only {prod['stock']} units available")

    cart = repo.get_or_create_cart(user_id)
    existing = repo.get_cart_item(cart["id"], product_id)

    if existing:
        new_qty = existing["quantity"] + payload.quantity
        if new_qty > 100: raise HTTPException(400, "Maximum 100 units per item")
        if prod["stock"] < new_qty: raise HTTPException(409, f"Only {prod['stock']} units available")
        
        repo.update_item_quantity(existing["id"], new_qty)
        if hasattr(request.state, "actions"): request.state.actions.append(f"Updated existing item quantity to {new_qty}")
    else:
        repo.add_item_to_cart(cart["id"], product_id, payload.quantity, float(prod["price"]))
        if hasattr(request.state, "actions"): request.state.actions.append("Added new product to cart")

    return _calculate_cart_pricing(repo, cart)

@router.put("/items/{product_id}", status_code=status.HTTP_200_OK, response_model=CartResponse)
def update_item(request: Request, product_id: UUID, payload: UpdateItemRequest, current: dict[str, Any] = Depends(get_current_user)):
    user_id = _get_user_id(current)
    pid = str(product_id)
    repo = CartRepository()
    
    if hasattr(request.state, "actions"): request.state.actions.append(f"Updating quantity to {payload.quantity}")

    cart = repo.get_or_create_cart(user_id)
    prod = repo.get_product_stock_status(pid)
    
    if not prod or not prod.get("is_active"): raise HTTPException(404, "Product not found")
    if prod["stock"] < payload.quantity: raise HTTPException(409, f"Only {prod['stock']} units available")

    success = repo.update_item_quantity_by_product(cart["id"], pid, payload.quantity)
    if not success: raise HTTPException(404, "Item not in cart")

    if hasattr(request.state, "actions"): request.state.actions.append("Quantity successfully updated and totals recalculated")
    return _calculate_cart_pricing(repo, cart)

@router.delete("/items/{product_id}", status_code=status.HTTP_200_OK, response_model=CartResponse)
def remove_item(request: Request, product_id: UUID, current: dict[str, Any] = Depends(get_current_user)):
    user_id = _get_user_id(current)
    pid = str(product_id)
    repo = CartRepository()
    
    cart = repo.get_or_create_cart(user_id)
    repo.remove_item(cart["id"], pid)
    
    if hasattr(request.state, "actions"): request.state.actions.append(f"Product {pid[:8]}... removed from cart")
    return _calculate_cart_pricing(repo, cart)

@router.delete("", status_code=status.HTTP_200_OK, response_model=MessageResponse)
def clear_cart(request: Request, current: dict[str, Any] = Depends(get_current_user)):
    user_id = _get_user_id(current)
    repo = CartRepository()
    
    cart = repo.get_or_create_cart(user_id)
    repo.clear_cart(cart["id"])
    
    if hasattr(request.state, "actions"): request.state.actions.append("Entire cart cleared successfully")
    return {"message": "Cart cleared"}


# ══════════════════════════════════════════════════════════════════════════════
#  ADMIN ENDPOINTS
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/admin/abandoned", dependencies=[Depends(require_admin)], response_model=AbandonedCartResponse)
def list_abandoned_carts(
    request: Request, hours: int = Query(default=_ABANDONED_HOURS, ge=1, le=168),
    page: int = Query(default=1, ge=1), page_size: int = Query(default=20, ge=1, le=100)
):
    repo = CartRepository()
    offset = (page - 1) * page_size
    if hasattr(request.state, "actions"): request.state.actions.append(f"Fetching abandoned carts (Cutoff: >{hours} hours)")

    cutoff = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=hours)).isoformat()
    rows, total = repo.get_abandoned_carts(cutoff, offset, page_size)

    for row in rows:
        items = row.get("cart_items", [])
        row["item_count"] = len(items)
        row["estimated_value"] = float(sum(Decimal(str(i["price_snapshot"])) * i["quantity"] for i in items))

    return {
        "items": rows, "total": total, "page": page, "page_size": page_size,
        "pages": -(-total // page_size) if page_size > 0 else 0, "hours_threshold": hours
    }

@router.post("/admin/remind/{cart_id}", dependencies=[Depends(require_admin)], response_model=ReminderResponse)
def send_cart_reminder(request: Request, cart_id: UUID):
    repo = CartRepository()
    if hasattr(request.state, "actions"): request.state.actions.append(f"Initiating reminder for abandoned cart: {str(cart_id)[:8]}...")

    cart = repo.get_cart_for_reminder(str(cart_id))
    if not cart: raise HTTPException(404, "Cart not found")

    user_info = cart.get("users") or {}
    items = cart.get("cart_items") or []
    if not items: raise HTTPException(400, "Cart is empty")

    user_id, email, name = cart["user_id"], user_info.get("email", ""), user_info.get("full_name", "there")

    push_sent = 0
    try: 
        # Integration logic
        from app.core.supabase import get_admin_supabase
        sb = get_admin_supabase() 
        push_sent = send_push_to_user(sb, user_id, title="🛒 You left something behind!", body=f"Hi {name or 'there'}, your cart has {len(items)} item(s) waiting.", icon="/icons/ri-shopping-cart-2.png", url="/cart.html")
    except Exception as exc: logger.warning("Push failed | %s", exc)

    email_sent = False
    if email:
        try:
            email_service = get_email_provider("resend")
            email_service.send_cart_reminder_email(email, name, items)
            email_sent = True
        except Exception as exc: logger.warning("Email failed | %s", exc)
            
    if hasattr(request.state, "actions"):
        request.state.actions.extend([f"Push Sent: {'Yes' if push_sent else 'No'}", f"Email Sent: {'Yes' if email_sent else 'No'}"])

    return {"message": "Reminder sent", "push_sent": str(push_sent > 0), "email_sent": str(email_sent)}
"""
Cart Router — Async Enterprise Grade
====================================
Path: app/api/v1/routers/cart.py

FIX APPLIED:
  1. breakdown.shipping_cost → breakdown.shipping  (AttributeError was here)
  2. breakdown.tax_amount   → breakdown.tax
  3. breakdown.total_amount → breakdown.total
  4. Used breakdown.as_dict() for clean mapping (shipping_cost key stays in response)
  5. Removed stray traceback text inside send_cart_reminder return
"""
from __future__ import annotations

import asyncio
import logging
import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from app.core.dependencies import get_current_user, require_admin
from app.api.schemas.cart_dto import (
    AddItemRequest, UpdateItemRequest, CartResponse,
    MessageResponse, AbandonedCartResponse, ReminderResponse
)
from app.repositories.cart_repo import AsyncCartRepository
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


async def _calculate_cart_pricing(
    repo: AsyncCartRepository,
    cart: dict[str, Any],
) -> dict[str, Any]:
    """
    Calculate cart totals using the central PricingEngine (SSOT).

    FIX: PriceBreakdown ke fields hain:
         .subtotal  .shipping  .tax  .total  .currency
    Inhe access karne ka sahi tarika: breakdown.as_dict()
    which maps them to the API-friendly keys:
         subtotal / shipping_cost / tax_amount / total_amount
    """
    config, raw_items = await asyncio.gather(
        repo.get_pricing_config(),
        repo.get_cart_items_with_products(cart["id"]),
    )
    pricing_engine = get_pricing_from_config(config)

    enriched: list[dict[str, Any]] = []
    subtotal        = Decimal("0")
    has_unavailable = False

    for row in raw_items:
        prod          = row.get("products") or {}
        qty           = row["quantity"]
        snapshot      = Decimal(str(row["price_snapshot"]))
        current_price = Decimal(str(prod.get("price", snapshot)))
        line_total    = current_price * qty
        subtotal     += line_total

        in_stock      = prod.get("is_active", True) and prod.get("stock", 0) >= qty
        price_changed = abs(float(current_price) - float(snapshot)) > 0.001

        if not in_stock:
            has_unavailable = True

        enriched.append({
            "id":            row["id"],
            "product_id":    row["product_id"],
            "name":          prod.get("name", ""),
            "slug":          prod.get("slug", ""),
            "image_url":     prod.get("image_url"),
            "quantity":      qty,
            "unit_price":    float(current_price),
            "price_snapshot": float(snapshot),
            "line_total":    float(line_total),
            "stock":         prod.get("stock", 0),
            "in_stock":      in_stock,
            "is_active":     prod.get("is_active", True),
            "price_changed": price_changed,
            "added_at":      row["added_at"],
        })

    breakdown = pricing_engine.calculate(subtotal)

    # ── FIX: breakdown.as_dict() maps correctly: ──────────────────────────────
    # PriceBreakdown.shipping  →  dict key "shipping_cost"  (API response key)
    # PriceBreakdown.tax       →  dict key "tax_amount"
    # PriceBreakdown.total     →  dict key "total_amount"
    # ─────────────────────────────────────────────────────────────────────────
    pricing_dict = breakdown.as_dict()

    # Amount needed to unlock free shipping
    amount_to_free = 0.0
    if pricing_engine.shipping_enabled and subtotal < pricing_engine.shipping_threshold:
        amount_to_free = round(
            max(0.0, float(pricing_engine.shipping_threshold) - float(subtotal)), 2
        )

    return {
        "items":      enriched,
        "item_count": len(enriched),

        # ── Spread pricing dict (correct field names from as_dict()) ──────────
        # Keys: subtotal, shipping_cost, tax_amount, total_amount, currency
        **pricing_dict,

        # ── Extra cart-specific fields ────────────────────────────────────────
        # FIX: breakdown.shipping  (not .shipping_cost — that's only in as_dict)
        "free_shipping_eligible":   breakdown.shipping == Decimal("0") and subtotal > Decimal("0"),
        "amount_to_free_shipping":  amount_to_free,
        "free_shipping_threshold":  float(pricing_engine.shipping_threshold),
        "tax_rate_pct":             float(pricing_engine.tax_rate * 100),
        "has_unavailable_items":    has_unavailable,
    }


# ══════════════════════════════════════════════════════════════════════════════
#  CUSTOMER ENDPOINTS
# ══════════════════════════════════════════════════════════════════════════════

@router.get("", response_model=CartResponse)
async def get_cart(
    request: Request,
    current: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    user_id = _get_user_id(current)
    repo    = AsyncCartRepository()

    if hasattr(request.state, "actions"):
        request.state.actions.extend([
            "Fetching active cart via Repo",
            "Applying live SSOT pricing rules",
        ])

    cart = await repo.get_or_create_cart(user_id)
    return await _calculate_cart_pricing(repo, cart)


@router.post("/items", status_code=status.HTTP_200_OK, response_model=CartResponse)
async def add_item(
    request: Request,
    payload: AddItemRequest,
    current: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    user_id    = _get_user_id(current)
    product_id = str(payload.product_id)
    repo       = AsyncCartRepository()

    if await repo.is_cart_locked(user_id):
        raise HTTPException(status.HTTP_409_CONFLICT, "Your cart is locked during checkout. Complete or cancel your payment before modifying the cart.")

    if hasattr(request.state, "actions"):
        request.state.actions.append(f"Verifying stock for product: {product_id[:8]}…")

    prod = await repo.get_product_stock_status(product_id)
    if not prod or not prod.get("is_active"):
        raise HTTPException(404, "Product not found or inactive")
    if prod["stock"] < payload.quantity:
        raise HTTPException(409, f"Only {prod['stock']} units available")

    cart     = await repo.get_or_create_cart(user_id)
    existing = await repo.get_cart_item(cart["id"], product_id)

    if existing:
        new_qty = existing["quantity"] + payload.quantity
        if new_qty > 100:
            raise HTTPException(400, "Maximum 100 units per item")
        if prod["stock"] < new_qty:
            raise HTTPException(
                409,
                f"Only {prod['stock']} units available "
                f"(you already have {existing['quantity']} in cart)",
            )
        await repo.update_item_quantity(existing["id"], new_qty)
        if hasattr(request.state, "actions"):
            request.state.actions.append(f"Updated existing item quantity to {new_qty}")
    else:
        await repo.add_item_to_cart(
            cart["id"], product_id, payload.quantity, float(prod["price"])
        )
        if hasattr(request.state, "actions"):
            request.state.actions.append("Added new product to cart")

    return await _calculate_cart_pricing(repo, cart)


@router.put("/items/{product_id}", status_code=status.HTTP_200_OK, response_model=CartResponse)
async def update_item(
    request:    Request,
    product_id: UUID,
    payload:    UpdateItemRequest,
    current:    dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    user_id = _get_user_id(current)
    pid     = str(product_id)
    repo    = AsyncCartRepository()

    if await repo.is_cart_locked(user_id):
        raise HTTPException(status.HTTP_409_CONFLICT, "Your cart is locked during checkout. Complete or cancel your payment before modifying the cart.")

    if hasattr(request.state, "actions"):
        request.state.actions.append(f"Updating quantity to {payload.quantity}")

    cart = await repo.get_or_create_cart(user_id)
    prod = await repo.get_product_stock_status(pid)

    if not prod or not prod.get("is_active"):
        raise HTTPException(404, "Product not found")
    if prod["stock"] < payload.quantity:
        raise HTTPException(409, f"Only {prod['stock']} units available")

    success = await repo.update_item_quantity_by_product(cart["id"], pid, payload.quantity)
    if not success:
        raise HTTPException(404, "Item not in cart")

    if hasattr(request.state, "actions"):
        request.state.actions.append("Quantity updated and totals recalculated")

    return await _calculate_cart_pricing(repo, cart)


@router.delete("/items/{product_id}", status_code=status.HTTP_200_OK, response_model=CartResponse)
async def remove_item(
    request:    Request,
    product_id: UUID,
    current:    dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    user_id = _get_user_id(current)
    pid     = str(product_id)
    repo    = AsyncCartRepository()

    if await repo.is_cart_locked(user_id):
        raise HTTPException(status.HTTP_409_CONFLICT, "Your cart is locked during checkout. Complete or cancel your payment before modifying the cart.")

    cart = await repo.get_or_create_cart(user_id)
    await repo.remove_item(cart["id"], pid)

    if hasattr(request.state, "actions"):
        request.state.actions.append(f"Product {pid[:8]}… removed from cart")

    return await _calculate_cart_pricing(repo, cart)


@router.delete("", status_code=status.HTTP_200_OK, response_model=MessageResponse)
async def clear_cart(
    request: Request,
    current: dict[str, Any] = Depends(get_current_user),
) -> dict[str, str]:
    user_id = _get_user_id(current)
    repo    = AsyncCartRepository()

    cart = await repo.get_or_create_cart(user_id)
    await repo.clear_cart(cart["id"])

    if hasattr(request.state, "actions"):
        request.state.actions.append("Entire cart cleared successfully")

    return {"message": "Cart cleared"}


# ══════════════════════════════════════════════════════════════════════════════
#  ADMIN ENDPOINTS
# ══════════════════════════════════════════════════════════════════════════════

@router.get(
    "/admin/abandoned",
    dependencies=[Depends(require_admin)],
    response_model=AbandonedCartResponse,
)
async def list_abandoned_carts(
    request:   Request,
    hours:     int = Query(default=_ABANDONED_HOURS, ge=1, le=168),
    page:      int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> dict[str, Any]:
    repo   = AsyncCartRepository()
    offset = (page - 1) * page_size

    if hasattr(request.state, "actions"):
        request.state.actions.append(f"Fetching abandoned carts (cutoff: >{hours}h)")

    cutoff = (
        datetime.datetime.now(datetime.timezone.utc)
        - datetime.timedelta(hours=hours)
    ).isoformat()

    rows, total = await repo.get_abandoned_carts(cutoff, offset, page_size)

    for row in rows:
        items = row.get("cart_items", [])
        row["item_count"]      = len(items)
        row["estimated_value"] = float(
            sum(Decimal(str(i["price_snapshot"])) * i["quantity"] for i in items)
        )

    return {
        "items":           rows,
        "total":           total,
        "page":            page,
        "page_size":       page_size,
        "pages":           -(-total // page_size) if page_size > 0 else 0,
        "hours_threshold": hours,
    }


@router.post(
    "/admin/remind/{cart_id}",
    dependencies=[Depends(require_admin)],
    response_model=ReminderResponse,
)
async def send_cart_reminder(
    request: Request,
    cart_id: UUID,
) -> dict[str, str]:
    repo = AsyncCartRepository()

    if hasattr(request.state, "actions"):
        request.state.actions.append(f"Initiating reminder for cart: {str(cart_id)[:8]}…")

    cart = await repo.get_cart_for_reminder(str(cart_id))
    if not cart:
        raise HTTPException(404, "Cart not found")

    user_info = cart.get("users") or {}
    items     = cart.get("cart_items") or []
    if not items:
        raise HTTPException(400, "Cart is empty — no reminder needed")

    user_id = cart["user_id"]
    email   = user_info.get("email", "")
    name    = user_info.get("full_name", "there")

    # ── Push notification ─────────────────────────────────────────────────────
    push_sent = 0
    try:
        from app.core.supabase import get_admin_supabase
        sb_sync   = get_admin_supabase()
        push_sent = send_push_to_user(
            sb_sync, user_id,
            title="🛒 You left something behind!",
            body=f"Hi {name or 'there'}, your cart has {len(items)} item(s) waiting.",
            icon="/icons/ri-shopping-cart-2.png",
            url="/cart.html",
        )
    except Exception as exc:
        logger.warning("Cart reminder push failed | cart=%s | %s", str(cart_id)[:8], exc)

    # ── Email ─────────────────────────────────────────────────────────────────
    email_sent = False
    if email:
        try:
            email_service = get_email_provider("resend")
            email_service.send_cart_reminder_email(email, name, items)
            email_sent = True
        except Exception as exc:
            logger.warning("Cart reminder email failed | cart=%s | %s", str(cart_id)[:8], exc)
    else:
        logger.warning("Cart reminder: no email for user %.8s", user_id)

    if hasattr(request.state, "actions"):
        request.state.actions.extend([
            f"Push sent: {'Yes' if push_sent else 'No'}",
            f"Email sent: {'Yes' if email_sent else 'No'}",
        ])

    logger.info(
        "Cart reminder sent | cart=%s user=%.8s push=%d email=%s",
        str(cart_id)[:8], user_id, push_sent, email_sent,
    )

    # ── FIX: Clean return — no stray text after this ──────────────────────────
    return {
        "message":    "Reminder sent",
        "push_sent":  str(push_sent > 0),
        "email_sent": str(email_sent),
    }
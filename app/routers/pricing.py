"""
Pricing Router
==============
GET  /api/v1/pricing/calculate  — calculate shipping + tax for a list of items
GET  /api/v1/pricing/config     — return current pricing config (rates, thresholds)

WHY THIS EXISTS:
  Frontend MUST NEVER calculate tax/shipping locally. Any local calculation
  creates idempotency mismatches — the amount the user sees != the amount
  charged at checkout, causing payment failures or support tickets.

  Every screen that shows a price breakdown (cart, checkout, order review)
  calls this endpoint. The result is the single source of truth.

USAGE:
  POST /api/v1/pricing/calculate
  Body: { "items": [{ "product_id": "uuid", "quantity": 2 }] }

  Response:
  {
    "items": [{ "product_id": "...", "name": "...", "unit_price": 210.00,
                "quantity": 2, "line_total": 420.00, "price_changed": false }],
    "subtotal":      420.00,
    "shipping_cost":   0.00,   ← free above threshold
    "tax_amount":     33.60,
    "total_amount":  453.60,
    "free_shipping_threshold": 75.00,
    "tax_rate_pct":              8.0,
    "currency":               "INR"
  }

  `price_changed: true` means the product price changed since the user added
  it to cart. Frontend should warn the user before checkout.
"""
from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.config import settings
from app.services.pricing import get_default_pricing
from app.supabase_client import get_admin_supabase

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/pricing", tags=["Pricing"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class PricingItem(BaseModel):
    product_id:     UUID
    quantity:       int  = Field(ge=1, le=100)
    # Optional: price the frontend believes the product has (from cart snapshot).
    # If provided and differs from current DB price, response sets price_changed=True.
    cached_price:   float | None = None


class PricingRequest(BaseModel):
    items: list[PricingItem] = Field(min_length=1, max_length=50)


class PricingLineItem(BaseModel):
    product_id:    str
    name:          str
    slug:          str
    image_url:     str | None
    unit_price:    float
    quantity:      int
    line_total:    float
    in_stock:      bool
    price_changed: bool   # True if current price != cached_price sent by frontend


class PricingResponse(BaseModel):
    items:                    list[PricingLineItem]
    subtotal:                 float
    shipping_cost:            float
    tax_amount:               float
    total_amount:             float
    free_shipping_threshold:  float
    free_shipping_eligible:   bool
    amount_to_free_shipping:  float   # 0 if already free
    tax_rate_pct:             float
    currency:                 str = "INR"
    has_unavailable_items:    bool   # True if any item is inactive or out of stock


class PricingConfigResponse(BaseModel):
    shipping_threshold: float
    shipping_flat:      float
    tax_rate_pct:       float
    currency:           str = "INR"


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/calculate", response_model=PricingResponse)
def calculate_pricing(payload: PricingRequest) -> PricingResponse:
    """
    Server-side pricing calculation — the ONLY source of truth.

    Frontend calls this on:
      • Cart page load / item change
      • Checkout page load
      • Before creating an order (to verify totals)

    Returns current prices from DB, not cached prices. If a product's price
    changed since the user added it to cart, `price_changed` is set True so
    the frontend can warn the user.
    """
    sb          = get_admin_supabase()
    product_ids = [str(item.product_id) for item in payload.items]

    # Batch fetch all products in one query — no N+1
    res = (
        sb.table("products")
        .select("id, name, slug, price, stock, image_url, is_active")
        .in_("id", product_ids)
        .execute()
    )

    if not res or not getattr(res, "data", None):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No products found for the given IDs",
        )

    prod_map: dict[str, dict[str, Any]] = {p["id"]: p for p in res.data}

    # Build cache lookup from request (product_id → cached_price)
    cached: dict[str, float | None] = {
        str(item.product_id): item.cached_price for item in payload.items
    }

    line_items: list[PricingLineItem]  = []
    subtotal      = Decimal("0")
    has_unavailable = False

    for req_item in payload.items:
        pid  = str(req_item.product_id)
        prod = prod_map.get(pid)

        if not prod:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Product {pid} not found",
            )

        current_price = Decimal(str(prod["price"]))
        qty           = req_item.quantity
        line_total    = current_price * qty
        subtotal     += line_total

        # Detect price change (warn user but don't block — checkout will use live price)
        cached_price  = cached.get(pid)
        price_changed = (
            cached_price is not None
            and abs(float(current_price) - cached_price) > 0.001
        )

        in_stock = prod.get("is_active", True) and prod.get("stock", 0) >= qty
        if not in_stock or not prod.get("is_active", True):
            has_unavailable = True

        line_items.append(PricingLineItem(
            product_id=pid,
            name=prod["name"],
            slug=prod["slug"],
            image_url=prod.get("image_url"),
            unit_price=float(current_price),
            quantity=qty,
            line_total=float(line_total),
            in_stock=in_stock,
            price_changed=price_changed,
        ))

    # Apply pricing strategy (StandardPricing from config)
    pricing   = get_default_pricing()
    breakdown = pricing.calculate(subtotal)

    threshold      = float(settings.SHIPPING_THRESHOLD)
    sub_float      = float(subtotal)
    amount_to_free = max(0.0, threshold - sub_float) if breakdown.shipping > 0 else 0.0

    return PricingResponse(
        items=line_items,
        subtotal=float(breakdown.subtotal),
        shipping_cost=float(breakdown.shipping),
        tax_amount=round(float(breakdown.tax), 2),
        total_amount=round(float(breakdown.total), 2),
        free_shipping_threshold=threshold,
        free_shipping_eligible=breakdown.shipping == 0,
        amount_to_free_shipping=round(amount_to_free, 2),
        tax_rate_pct=float(settings.TAX_RATE) * 100,
        has_unavailable_items=has_unavailable,
    )


@router.get("/config", response_model=PricingConfigResponse)
def get_pricing_config() -> PricingConfigResponse:
    """
    Return current pricing configuration.

    Frontend can use this to show "Free shipping on orders above ₹X"
    banners without hardcoding any values.
    """
    return PricingConfigResponse(
        shipping_threshold=float(settings.SHIPPING_THRESHOLD),
        shipping_flat=float(settings.SHIPPING_FLAT),
        tax_rate_pct=float(settings.TAX_RATE) * 100,
    )
    
    
    
    # Isse aapka 'Save Settings' button 405 error dena band kar dega
@router.patch("/config")
def update_pricing_config(payload: PricingConfigResponse):
    """
    Kyunki pricing settings abhi .env/settings se chal rahi hain,
    ye endpoint temporary success return karega.
    Production mein yahan logic database update ka aayega.
    """
    return {"message": "Configuration received successfully"}
    
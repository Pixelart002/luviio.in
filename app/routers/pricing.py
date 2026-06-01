from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.supabase_client import get_admin_supabase

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/pricing", tags=["Pricing"])


# ──────────────────────────────────────────────────────────────
# Schemas
# ──────────────────────────────────────────────────────────────

class PricingItem(BaseModel):
    product_id: UUID
    quantity: int = Field(ge=1, le=100)
    cached_price: float | None = None


class PricingRequest(BaseModel):
    items: list[PricingItem] = Field(min_length=1, max_length=50)


class PricingLineItem(BaseModel):
    product_id: str
    name: str
    slug: str
    image_url: str | None
    unit_price: float
    quantity: int
    line_total: float
    in_stock: bool
    price_changed: bool


class PricingResponse(BaseModel):
    items: list[PricingLineItem]
    subtotal: float
    shipping_cost: float
    tax_amount: float
    total_amount: float
    free_shipping_threshold: float
    free_shipping_eligible: bool
    amount_to_free_shipping: float
    tax_rate_pct: float
    currency: str
    has_unavailable_items: bool


class PricingConfigResponse(BaseModel):
    tax_rate: float
    shipping_flat: float
    shipping_threshold: float
    currency: str
    tax_enabled: bool
    shipping_enabled: bool


class PricingConfigUpdate(BaseModel):
    tax_rate: float = Field(ge=0, le=100)
    shipping_flat: float = Field(ge=0)
    shipping_threshold: float = Field(ge=0)
    currency: str = Field(min_length=1, max_length=10)

    tax_enabled: bool = True
    shipping_enabled: bool = True


# ──────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────

def fetch_pricing_config() -> dict[str, Any]:
    sb = get_admin_supabase()

    res = (
        sb.table("pricing_config")
        .select("*")
        .limit(1)
        .single()
        .execute()
    )

    if not res or not getattr(res, "data", None):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Pricing configuration not found",
        )

    return res.data


# ──────────────────────────────────────────────────────────────
# Calculate Pricing
# ──────────────────────────────────────────────────────────────

@router.post("/calculate", response_model=PricingResponse)
def calculate_pricing(payload: PricingRequest) -> PricingResponse:

    sb = get_admin_supabase()

    config = fetch_pricing_config()

    tax_rate = Decimal(str(config["tax_rate"])) / Decimal("100")
    shipping_flat = Decimal(str(config["shipping_flat"]))
    shipping_threshold = Decimal(str(config["shipping_threshold"]))

    tax_enabled = config["tax_enabled"]
    shipping_enabled = config["shipping_enabled"]

    product_ids = [str(item.product_id) for item in payload.items]

    res = (
        sb.table("products")
        .select("id,name,slug,price,stock,image_url,is_active")
        .in_("id", product_ids)
        .execute()
    )

    if not res or not getattr(res, "data", None):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No products found",
        )

    prod_map: dict[str, dict[str, Any]] = {
        p["id"]: p for p in res.data
    }

    cached_prices = {
        str(item.product_id): item.cached_price
        for item in payload.items
    }

    subtotal = Decimal("0")
    has_unavailable_items = False

    line_items: list[PricingLineItem] = []

    for item in payload.items:

        pid = str(item.product_id)

        product = prod_map.get(pid)

        if not product:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Product {pid} not found",
            )

        current_price = Decimal(str(product["price"]))
        qty = item.quantity

        line_total = current_price * qty
        subtotal += line_total

        cached_price = cached_prices.get(pid)

        price_changed = (
            cached_price is not None
            and abs(float(current_price) - cached_price) > 0.001
        )

        in_stock = (
            product.get("is_active", True)
            and product.get("stock", 0) >= qty
        )

        if not in_stock:
            has_unavailable_items = True

        line_items.append(
            PricingLineItem(
                product_id=pid,
                name=product["name"],
                slug=product["slug"],
                image_url=product.get("image_url"),
                unit_price=float(current_price),
                quantity=qty,
                line_total=float(line_total),
                in_stock=in_stock,
                price_changed=price_changed,
            )
        )

    shipping = Decimal("0")

    if shipping_enabled:
        if subtotal < shipping_threshold:
            shipping = shipping_flat

    tax = Decimal("0")

    if tax_enabled:
        tax = (subtotal + shipping) * tax_rate

    total = subtotal + shipping + tax

    amount_to_free_shipping = 0.0

    if shipping_enabled and shipping > 0:
        amount_to_free_shipping = max(
            0.0,
            float(shipping_threshold - subtotal),
        )

    return PricingResponse(
        items=line_items,
        subtotal=round(float(subtotal), 2),
        shipping_cost=round(float(shipping), 2),
        tax_amount=round(float(tax), 2),
        total_amount=round(float(total), 2),
        free_shipping_threshold=float(shipping_threshold),
        free_shipping_eligible=shipping == 0,
        amount_to_free_shipping=round(
            amount_to_free_shipping,
            2,
        ),
        tax_rate_pct=float(config["tax_rate"]),
        currency=config["currency"],
        has_unavailable_items=has_unavailable_items,
    )


# ──────────────────────────────────────────────────────────────
# Get Config
# ──────────────────────────────────────────────────────────────

@router.get("/config", response_model=PricingConfigResponse)
def get_pricing_config():

    config = fetch_pricing_config()

    return PricingConfigResponse(
        tax_rate=float(config["tax_rate"]),
        shipping_flat=float(config["shipping_flat"]),
        shipping_threshold=float(config["shipping_threshold"]),
        currency=config["currency"],
        tax_enabled=config["tax_enabled"],
        shipping_enabled=config["shipping_enabled"],
    )


# ──────────────────────────────────────────────────────────────
# Update Config
# ──────────────────────────────────────────────────────────────

@router.put("/config")
def update_pricing_config(
    payload: PricingConfigUpdate,
):

    sb = get_admin_supabase()

    config = fetch_pricing_config()

    data = payload.model_dump()

    data["updated_at"] = (
        datetime.now(timezone.utc)
        .isoformat()
    )

    (
        sb.table("pricing_config")
        .update(data)
        .eq("id", config["id"])
        .execute()
    )

    return {
        "success": True,
        "message": "Pricing configuration updated",
    }
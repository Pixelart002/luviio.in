"""
Cart Schemas (DTOs)
===================
Path: app/api/schemas/cart_dto.py
"""
from pydantic import BaseModel, Field
from typing import List, Any
from uuid import UUID

# ── Requests ──────────────────────────────────────────────────────────────────

class AddItemRequest(BaseModel):
    product_id: UUID
    quantity: int = Field(ge=1, le=100)

class UpdateItemRequest(BaseModel):
    quantity: int = Field(ge=1, le=100)

# ── Responses ─────────────────────────────────────────────────────────────────

class CartItemDTO(BaseModel):
    id: str
    product_id: str
    name: str
    slug: str
    image_url: str | None
    quantity: int
    unit_price: float
    compare_price: Optional[float] = 0.0
    price_snapshot: float
    line_total: float
    stock: int
    in_stock: bool
    is_active: bool
    price_changed: bool
    added_at: str

class CartResponse(BaseModel):
    items: List[CartItemDTO]
    item_count: int
    subtotal: float
    shipping_cost: float
    tax_amount: float
    total_amount: float
    free_shipping_eligible: bool
    amount_to_free_shipping: float
    free_shipping_threshold: float
    tax_rate_pct: float
    has_unavailable_items: bool
    currency: str

class MessageResponse(BaseModel):
    message: str

class AbandonedCartResponse(BaseModel):
    items: List[dict]
    total: int
    page: int
    page_size: int
    pages: int
    hours_threshold: int

class ReminderResponse(BaseModel):
    message: str
    push_sent: str
    email_sent: str
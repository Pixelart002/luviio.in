"""
Cart Schemas (DTOs) — Enterprise Grade & GST Ready
====================================================
Path: app/api/schemas/cart_dto.py
"""
from pydantic import BaseModel, ConfigDict, Field
from typing import List, Optional
from uuid import UUID
from app.constants.cart_messages import CartRules

class AddItemRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    product_id: UUID
    quantity: int = Field(ge=1, le=CartRules.MAX_QTY_PER_ITEM)

class UpdateItemRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    quantity: int = Field(ge=1, le=CartRules.MAX_QTY_PER_ITEM)

class CartItemDTO(BaseModel):
    id: str
    product_id: str
    name: str
    slug: str
    image_url: Optional[str] = None
    hsn_code: str             # 🔥 Added: Item-level HSN code for legal invoice compliance
    gst_percentage: int       # 🔥 Added: Item-level GST percentage slab (e.g., 5, 12, 18, 28)
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
    # ❌ Removed obsolete global tax_rate_pct field
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
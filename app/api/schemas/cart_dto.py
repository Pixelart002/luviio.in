"""
Cart Schemas (DTOs) — Enterprise Grade & GST Ready
====================================================
Path: app/api/schemas/cart_dto.py
"""
from pydantic import BaseModel, ConfigDict, Field
from typing import List, Optional, Dict, Any
from uuid import UUID
from app.constants.cart_messages import CartRules

class AddItemRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    product_id: UUID
    quantity: int = Field(default=1, ge=1, le=CartRules.MAX_QTY_PER_ITEM)

class UpdateItemRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    quantity: int = Field(ge=1, le=CartRules.MAX_QTY_PER_ITEM)

class CartItemDTO(BaseModel):
    id: str
    product_id: str
    name: str
    slug: str
    image_url: Optional[str] = None
    hsn_code: str
    gst_percentage: int
    quantity: int
    unit_price: float
    compare_price: float
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
    has_unavailable_items: bool
    currency: str = "INR"

class AbandonedCartResponse(BaseModel):
    items: List[Dict[str, Any]]
    total: int
    page: int
    page_size: int
    pages: int
    hours_threshold: int

class ReminderResponse(BaseModel):
    message: str
    push_sent: str
    email_sent: str
    
class MessageResponse(BaseModel):
    message: str
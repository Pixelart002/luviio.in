"""
Cart Schemas — Strict Pydantic DTOs
===================================
Path: app/api/schemas/cart_dto.py
"""
from pydantic import BaseModel, ConfigDict, Field
from typing import List, Optional, Dict, Any
from uuid import UUID

class AddItemRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    product_id: UUID
    quantity: int = Field(default=1, ge=1, le=100)

class UpdateItemRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    quantity: int = Field(..., ge=1, le=100)

class CartItemDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    product_id: str
    name: str
    slug: str
    image_url: Optional[str] = None
    quantity: int
    unit_price: float
    compare_price: float = 0.0
    price_snapshot: float
    line_total: float
    stock: int
    in_stock: bool
    is_active: bool
    price_changed: bool
    added_at: str

class CartResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
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
    currency: str = "INR"

class MessageResponse(BaseModel):
    message: str

class AbandonedCartResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
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
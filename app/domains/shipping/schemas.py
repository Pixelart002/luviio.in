"""
Shipping Domain — Schemas (DTOs)
================================
Path: app/domains/shipping/schemas.py
"""
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from app.constants.shipping_messages import SHIPPING_FLAT, SHIPPING_FREE_THRESHOLD, SHIPPING_PER_ITEM, SHIPPING_WEIGHT


class ShippingMethodCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    name: str = Field(..., min_length=2, max_length=80)
    type: str = Field(SHIPPING_FLAT, description="flat | free_threshold | per_item | weight")
    base_rate: float = Field(0, ge=0)
    threshold: Optional[float] = Field(None, ge=0, description="free-above threshold (free_threshold)")
    per_item_rate: Optional[float] = Field(None, ge=0, description="per_unit add-on (per_item)")
    weight_rate: Optional[float] = Field(None, ge=0, description="per-kg rate (weight)")
    estimated_days: int = Field(3, ge=1, le=30)
    is_active: bool = True
    sort_order: int = 0


class ShippingMethodUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    name: Optional[str] = None
    type: Optional[str] = None
    base_rate: Optional[float] = Field(None, ge=0)
    threshold: Optional[float] = Field(None, ge=0)
    per_item_rate: Optional[float] = Field(None, ge=0)
    weight_rate: Optional[float] = Field(None, ge=0)
    estimated_days: Optional[int] = Field(None, ge=1, le=30)
    is_active: Optional[bool] = None
    sort_order: Optional[int] = None


class ShippingRateRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    cart_subtotal: float = Field(..., ge=0)
    item_count: int = Field(1, ge=0)
    total_weight_kg: float = Field(0, ge=0)
    method_id: Optional[str] = None
    pincode: Optional[str] = Field(None, max_length=12)

from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.constants.shipping_messages import (
    SHIPPING_FLAT,
    SHIPPING_FREE_THRESHOLD,
    SHIPPING_PER_ITEM,
    SHIPPING_WEIGHT,
)

SHIPPING_TYPES = {SHIPPING_FLAT, SHIPPING_FREE_THRESHOLD, SHIPPING_PER_ITEM, SHIPPING_WEIGHT}


class ShippingMethodCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    name: str = Field(..., min_length=2, max_length=80)
    type: str = SHIPPING_FLAT
    base_rate: Decimal = Field(Decimal("0.00"), ge=0, decimal_places=2)
    threshold: Optional[Decimal] = Field(None, ge=0, decimal_places=2)
    per_item_rate: Optional[Decimal] = Field(None, ge=0, decimal_places=2)
    weight_rate: Optional[Decimal] = Field(None, ge=0, decimal_places=2)
    estimated_days: int = Field(3, ge=1, le=30)
    carrier: Optional[str] = Field(None, max_length=80)
    service_code: Optional[str] = Field(None, max_length=80)
    supports_cod: bool = True
    is_active: bool = True
    sort_order: int = 0

    @field_validator("type")
    @classmethod
    def validate_type(cls, value: str) -> str:
        if value not in SHIPPING_TYPES:
            raise ValueError(f"Unsupported shipping type: {value}")
        return value


class ShippingMethodUpdate(ShippingMethodCreate):
    name: Optional[str] = Field(None, min_length=2, max_length=80)
    type: Optional[str] = None
    base_rate: Optional[Decimal] = Field(None, ge=0, decimal_places=2)
    threshold: Optional[Decimal] = Field(None, ge=0, decimal_places=2)
    per_item_rate: Optional[Decimal] = Field(None, ge=0, decimal_places=2)
    weight_rate: Optional[Decimal] = Field(None, ge=0, decimal_places=2)
    estimated_days: Optional[int] = Field(None, ge=1, le=30)
    supports_cod: Optional[bool] = None
    is_active: Optional[bool] = None
    sort_order: Optional[int] = None


class ShippingRateRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    cart_subtotal: Decimal = Field(..., ge=0, decimal_places=2)
    item_count: int = Field(1, ge=1, le=1000)
    total_weight_kg: Decimal = Field(Decimal("0"), ge=0, le=100, decimal_places=3)
    volumetric_weight_kg: Decimal = Field(Decimal("0"), ge=0, le=100, decimal_places=3)
    method_id: Optional[str] = None
    pincode: str = Field(..., pattern=r"^[1-9][0-9]{5}$")
    cod: bool = False


class ShiprocketServiceabilityRequest(BaseModel):
    pickup_pincode: str = Field(..., pattern=r"^[1-9][0-9]{5}$")
    delivery_pincode: str = Field(..., pattern=r"^[1-9][0-9]{5}$")
    weight_kg: Decimal = Field(..., gt=0, le=100, decimal_places=3)
    cod: bool = False

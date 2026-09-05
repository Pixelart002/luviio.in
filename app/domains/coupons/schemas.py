"""
Coupons Domain — Schemas (DTOs)
===============================
Path: app/domains/coupons/schemas.py
"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.constants.coupon_messages import COUPON_TYPE_PERCENT, COUPON_TYPE_FIXED


class CouponCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    code: str = Field(..., min_length=3, max_length=50)
    type: str = Field(COUPON_TYPE_PERCENT, description="percent | fixed")
    value: float = Field(..., gt=0, description="Percent (e.g. 10 = 10%) or fixed amount in INR")
    min_order_amount: float = Field(0, ge=0)
    max_discount: Optional[float] = Field(None, ge=0, description="Cap on the discount amount")
    valid_from: Optional[datetime] = None
    valid_until: Optional[datetime] = None
    usage_limit: Optional[int] = Field(None, ge=1, description="Total redemption cap")
    per_user_limit: int = Field(1, ge=1)
    is_active: bool = True
    description: str = ""

    @field_validator("type")
    @classmethod
    def _type(cls, v: str) -> str:
        if v not in (COUPON_TYPE_PERCENT, COUPON_TYPE_FIXED):
            raise ValueError("type must be 'percent' or 'fixed'")
        return v

    @field_validator("value")
    @classmethod
    def _value(cls, v: float) -> float:
        if v > 100:
            raise ValueError("Percent value cannot exceed 100")
        return v


class CouponUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    type: Optional[str] = None
    value: Optional[float] = Field(None, gt=0)
    min_order_amount: Optional[float] = Field(None, ge=0)
    max_discount: Optional[float] = Field(None, ge=0)
    valid_from: Optional[datetime] = None
    valid_until: Optional[datetime] = None
    usage_limit: Optional[int] = Field(None, ge=1)
    per_user_limit: Optional[int] = Field(None, ge=1)
    is_active: Optional[bool] = None
    description: Optional[str] = None


class CouponApplyRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    code: str = Field(..., min_length=3, max_length=50)
    cart_subtotal: float = Field(..., ge=0, description="Order subtotal before coupon & tax")


class CouponApplyResult(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    code: str
    type: str
    value: float
    discount: float          # the resolved discount amount actually applied
    subtotal_after: float
    coupon_id: str = ""


class CouponDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    code: str
    type: str
    value: float
    min_order_amount: float
    max_discount: Optional[float]
    valid_from: Optional[datetime]
    valid_until: Optional[datetime]
    usage_limit: Optional[int]
    per_user_limit: int
    used_count: int
    is_active: bool
    description: str

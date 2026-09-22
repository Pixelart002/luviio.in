"""
Payment Schemas (DTOs)
======================
Path: app/domains/payments/schemas.py
"""
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class PaymentIntentRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    idempotency_key: str = Field(..., min_length=10, max_length=100, description="Unique key to prevent duplicate orders")
    shipping_address_id: UUID = Field(..., description="Selected shipping address ID")
    billing_address_id: Optional[UUID] = Field(None, description="Selected billing address ID, if different from shipping")
    coupon_code: Optional[str] = Field(None, max_length=40, description="Optional promo code to apply at checkout")
    shipping_courier_id: Optional[int] = Field(None, ge=1, description="Customer-selected Shiprocket courier company ID")
    provider_key: Optional[str] = Field(default=None, min_length=2, max_length=64, description="Installed payment provider key")


class PaymentIntentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    client_secret: str
    payment_intent_id: str
    order_id: str
    order_number: str
    payment_provider: str = "stripe"


class ConfirmPaymentRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    payment_intent_id: str = Field(..., min_length=5, max_length=200, description="Provider payment reference")
    provider_key: Optional[str] = Field(default=None, min_length=2, max_length=64, description="Payment provider key")


class NotifyFailedRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    payment_intent_id: str = Field(..., min_length=5, max_length=200, description="Provider payment reference")
    error_message: Optional[str] = Field(default="", max_length=500, description="Reason for failure")
    provider_key: Optional[str] = Field(default=None, min_length=2, max_length=64)

"""
Payment Schemas (DTOs)
======================
Path: app/api/schemas/payment_dto.py
"""
from pydantic import BaseModel, ConfigDict, Field
from uuid import UUID
from typing import Optional

class PaymentIntentRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    idempotency_key: str = Field(..., min_length=10, max_length=100, description="Unique key to prevent duplicate orders")
    shipping_address_id: UUID = Field(..., description="Selected shipping address ID")

class PaymentIntentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    client_secret: str
    payment_intent_id: str
    order_id: str
    order_number: str

class ConfirmPaymentRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    payment_intent_id: str = Field(..., min_length=5, max_length=100, description="Stripe Payment Intent ID")

class NotifyFailedRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    payment_intent_id: str = Field(..., min_length=5, max_length=100, description="Stripe Payment Intent ID")
    error_message: Optional[str] = Field(default="", max_length=500, description="Reason for failure")
"""
Payment Schemas (DTOs)
======================
Path: app/api/schemas/payment_dto.py
"""
from pydantic import BaseModel, Field
from uuid import UUID

class PaymentIntentRequest(BaseModel):
    # 🔥 order_id: UUID  <-- YE LINE HATA DENI HAI
    idempotency_key: str = Field(..., description="Unique key to prevent duplicate orders")
    shipping_address_id: UUID = Field(..., description="Selected shipping address ID")

class PaymentIntentResponse(BaseModel):
    client_secret: str
    payment_intent_id: str

class ConfirmPaymentRequest(BaseModel):
    # 🔥 order_id: UUID  <-- YE LINE BHI HATA DENI HAI
    payment_intent_id: str = Field(..., description="Stripe Payment Intent ID")

class NotifyFailedRequest(BaseModel):
    # 🔥 order_id: UUID  <-- YE LINE BHI HATA DENI HAI
    payment_intent_id: str = Field(..., description="Stripe Payment Intent ID")
    error_message: str = Field(default="", description="Reason for failure")
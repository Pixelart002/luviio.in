"""
Payment Schemas — Strict Pydantic DTOs
======================================
Path: app/api/schemas/payment_dto.py
"""
from pydantic import BaseModel, ConfigDict, Field
from uuid import UUID

class PaymentIntentRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    
    # 🔥 Client cannot spoof order_id anymore. Generated securely via idempotency.
    idempotency_key: str = Field(..., description="Unique UUID v4 key to prevent duplicate charging")
    shipping_address_id: UUID = Field(..., description="Selected shipping address ID for this checkout")

class PaymentIntentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    client_secret: str
    payment_intent_id: str
    order_id: str

class ConfirmPaymentRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    
    # 🔥 Client submits ONLY the Stripe Intent ID. Backend resolves the actual Order ID.
    payment_intent_id: str = Field(..., description="Stripe Payment Intent ID to verify")

class NotifyFailedRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    
    payment_intent_id: str = Field(..., description="Stripe Payment Intent ID that failed")
    error_message: str = Field(default="", description="Reason for gateway failure")
"""
Payment Schemas (DTOs)
======================
Path: app/api/schemas/payment_dto.py
"""
from pydantic import BaseModel, Field
from uuid import UUID

class PaymentIntentRequest(BaseModel):
    order_id: UUID

class PaymentIntentResponse(BaseModel):
    client_secret: str
    payment_intent_id: str

class ConfirmPaymentRequest(BaseModel):
    order_id: UUID
    payment_intent_id: str

class NotifyFailedRequest(BaseModel):
    order_id: UUID
    payment_intent_id: str
    error_message: str = Field(default="", max_length=500)
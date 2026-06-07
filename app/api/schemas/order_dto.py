"""
Order Schemas (DTOs)
====================
Path: app/api/schemas/order_dto.py
"""
import re
from uuid import UUID
from pydantic import BaseModel, Field, field_validator
from typing import List, Any

MAX_ITEMS_PER_ORDER = 50
VALID_STATUSES = {"pending", "paid", "shipped", "delivered", "cancelled", "refunded"}

class OrderItemInput(BaseModel):
    product_id: UUID
    quantity: int = Field(ge=1, le=100)

class OrderCreate(BaseModel):
    items: List[OrderItemInput] = Field(min_length=1, max_length=MAX_ITEMS_PER_ORDER)
    shipping_address_id: UUID
    notes: str | None = Field(default=None, max_length=500)
    idempotency_key: str | None = Field(default=None, max_length=64)

    @field_validator("items")
    @classmethod
    def no_duplicate_products(cls, v):
        ids = [str(item.product_id) for item in v]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate product_id not allowed — combine quantities instead.")
        return v

    @field_validator("idempotency_key")
    @classmethod
    def validate_idempotency_key(cls, v):
        if v is not None and not re.match(r'^[a-zA-Z0-9\-_]{8,64}$', v):
            raise ValueError("Invalid idempotency_key format")
        return v

class OrderAdminUpdate(BaseModel):
    status: str | None = Field(default=None)
    tracking_number: str | None = Field(default=None, max_length=100)

    @field_validator("status")
    @classmethod
    def validate_status(cls, v):
        if v and v not in VALID_STATUSES:
            raise ValueError(f"Invalid status. Must be one of: {VALID_STATUSES}")
        return v

class OrderListResponse(BaseModel):
    items: List[dict]
    total: int
    page: int
    page_size: int
    pages: int
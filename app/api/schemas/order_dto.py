"""
Order Schemas (DTOs)
====================
Path: app/api/schemas/order_dto.py
"""
from pydantic import BaseModel, ConfigDict, Field
from typing import List, Optional, Dict, Any
from uuid import UUID
from app.enums.order_status import OrderStatus

class OrderCreateFromCartRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    shipping_address_id: UUID = Field(..., description="UUID of the selected shipping address")
    notes: Optional[str] = Field(None, max_length=1000, description="Optional customer instructions")
    idempotency_key: Optional[str] = Field(None, max_length=100, description="Prevent duplicate orders on network retry")

class OrderAdminUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    status: Optional[OrderStatus] = Field(None, description="New order status governed by state machine")
    tracking_number: Optional[str] = Field(None, max_length=100)
    notes: Optional[str] = Field(None, max_length=1000)

class OrderListResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    items: List[Dict[str, Any]]
    total: int
    page: int
    page_size: int
    pages: int

class OrderCancelResponse(BaseModel):
    status: str
    order_id: str
    message: str
"""
Order Schemas (DTOs)
====================
Path: app/api/schemas/order_dto.py
"""
from pydantic import BaseModel, ConfigDict, Field
from typing import List, Optional, Dict, Any
from app.enums.order_status import OrderStatus

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
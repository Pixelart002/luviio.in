"""
Inventory Schemas
=================
Pydantic models for inventory DTOs.
"""
from typing import List, Optional

from pydantic import BaseModel, Field


class StockLevel(BaseModel):
    product_id: str
    stock: int = Field(ge=0)
    low_stock_threshold: int = Field(default=10, ge=0)
    is_low_stock: bool = False
    is_out_of_stock: bool = False


class ReservationItem(BaseModel):
    product_id: str
    quantity: int = Field(gt=0)
    price: float = Field(gt=0)


class ReservationRequest(BaseModel):
    order_id: str
    items: List[ReservationItem]


class ReservationResult(BaseModel):
    success: bool
    order_id: str
    reserved_items: List[ReservationItem]
    message: Optional[str] = None


class StockAdjustment(BaseModel):
    product_id: str
    delta: int
    reason: str
    previous_stock: int
    new_stock: int


class StockAdjustmentRequest(BaseModel):
    product_id: str
    delta: int = Field(..., ne=0, ge=-1000000, le=1000000)
    reason: str = Field(..., min_length=3, max_length=500)


class AvailabilityCheck(BaseModel):
    product_id: str
    available: bool
    stock: int
    is_active: bool
    message: Optional[str] = None

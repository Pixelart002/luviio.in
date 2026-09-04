"""
Inventory Schemas
=================
Path: app/domains/inventory/schemas.py

Pydantic models for inventory DTOs.
"""
from typing import Optional, List
from pydantic import BaseModel, Field


class StockLevel(BaseModel):
    """Current stock level for a product."""
    product_id: str
    stock: int = Field(ge=0)
    low_stock_threshold: int = Field(default=10, ge=0)
    is_low_stock: bool = False
    is_out_of_stock: bool = False


class ReservationItem(BaseModel):
    """Single item in a stock reservation."""
    product_id: str
    quantity: int = Field(gt=0)
    price: float = Field(gt=0)


class ReservationRequest(BaseModel):
    """Request to reserve stock for an order."""
    order_id: str
    items: List[ReservationItem]


class ReservationResult(BaseModel):
    """Result of a stock reservation operation."""
    success: bool
    order_id: str
    reserved_items: List[ReservationItem]
    message: Optional[str] = None


class StockAdjustment(BaseModel):
    """Record of a stock adjustment."""
    product_id: str
    delta: int  # Positive for additions, negative for reductions
    reason: str
    previous_stock: int
    new_stock: int


class AvailabilityCheck(BaseModel):
    """Result of checking product availability."""
    product_id: str
    available: bool
    stock: int
    is_active: bool
    message: Optional[str] = None

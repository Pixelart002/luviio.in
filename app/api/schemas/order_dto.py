"""
Order Schemas (DTOs)
====================
Path: app/api/schemas/order_dto.py
"""
from pydantic import BaseModel, Field
from typing import List, Optional, Any
from uuid import UUID

VALID_STATUSES = frozenset({"pending", "paid", "shipped", "delivered", "cancelled", "refunded"})

# ── Write DTOs (Sirf Admin use karega) ─────────────────────────────────────────

class OrderAdminUpdate(BaseModel):
    status: Optional[str] = Field(None, description="New order status")
    tracking_number: Optional[str] = Field(None, max_length=100)
    notes: Optional[str] = Field(None)

# ── Read DTOs (Responses ke liye) ──────────────────────────────────────────────

class OrderListResponse(BaseModel):
    items: List[dict[str, Any]]
    total: int
    page: int
    page_size: int
    pages: int
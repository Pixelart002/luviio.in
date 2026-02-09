from enum import Enum
from uuid import UUID
from typing import List, Optional
from pydantic import BaseModel, Field, ConfigDict, computed_field

class OrderStatus(str, Enum):
    PLACED = "placed"
    PICKING = "picking"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"

class StateMachine:
    """Deterministic transition rules"""
    RULES = {
        OrderStatus.PLACED: [OrderStatus.PICKING, OrderStatus.CANCELLED],
        OrderStatus.PICKING: [OrderStatus.SHIPPED],
        OrderStatus.SHIPPED: [OrderStatus.DELIVERED],
        OrderStatus.DELIVERED: [],
        OrderStatus.CANCELLED: []
    }

    @classmethod
    def can_transition(cls, current: OrderStatus, target: OrderStatus) -> bool:
        return target in cls.RULES.get(current, [])

class ProductSchema(BaseModel):
    model_config = ConfigDict(strict=True)
    id: UUID
    name: str
    price: float = Field(gt=0)
    stock: int = Field(ge=0)

class OrderCreate(BaseModel):
    store_id: UUID
    items: List[dict] # List of product_ids and quantities
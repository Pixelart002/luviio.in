"""
Subscription Domain — Schemas
==============================
Path: app/domains/subscriptions/schemas.py
"""
from __future__ import annotations

from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field


class SubscriptionPlanCreate(BaseModel):
    tier: str = Field(..., description="free | premium | platinum")
    name: str
    price_inr: Decimal = Field(..., gt=0)
    duration_days: int = Field(30, gt=0)
    description: Optional[str] = None
    is_active: bool = True


class SubscriptionPlanUpdate(BaseModel):
    name: Optional[str] = None
    price_inr: Optional[Decimal] = Field(None, gt=0)
    duration_days: Optional[int] = Field(None, gt=0)
    description: Optional[str] = None
    is_active: Optional[bool] = None


class SubscribeRequest(BaseModel):
    plan_id: str


class TierPublic(BaseModel):
    tier: str
    label: str
    free_shipping: bool
    discount_percent: float
    can_access_premium: bool
    can_access_platinum: bool
    extra_actions: list[str] = []


class SubscriptionInfo(BaseModel):
    tier: str
    plan_id: Optional[str] = None
    plan_name: Optional[str] = None
    price_inr: Optional[Decimal] = None
    starts_at: Optional[str] = None
    ends_at: Optional[str] = None
    active: bool = False
    perks: Optional[TierPublic] = None

"""
Admin Verification Schemas (DTOs)
=================================
Path: app/api/schemas/admin_dto.py
"""
from pydantic import BaseModel
from typing import Dict, Any
from datetime import datetime

class AdminProfile(BaseModel):
    id: str
    email: str
    full_name: str | None = None
    role: str
    is_active: bool
    created_at: datetime | str | None = None

class AdminVerifyResponse(BaseModel):
    verified: bool
    profile: AdminProfile
    timestamp: str

class AdminDashboardStats(BaseModel):
    products: int | float
    orders: int | float
    pending_orders: int | float
    users: int | float
    revenue: float

class AdminStatsResponse(BaseModel):
    verified: bool
    stats: AdminDashboardStats
    timestamp: str
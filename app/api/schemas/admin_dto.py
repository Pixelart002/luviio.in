"""
Admin Verification Schemas (DTOs)
=================================
Path: app/api/schemas/admin_dto.py
"""
from pydantic import BaseModel, ConfigDict
from typing import Optional

class AdminProfile(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    email: str
    full_name: Optional[str] = None
    role: str
    is_active: bool
    created_at: Optional[str] = None

class AdminDashboardStats(BaseModel):
    products: int
    orders: int
    pending_orders: int
    users: int
    revenue: float
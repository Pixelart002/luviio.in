"""
Admin Verification Schemas (DTOs)
=================================
Path: app/api/schemas/admin_dto.py
"""
from pydantic import BaseModel, ConfigDict, Field
from typing import Optional

class AdminProfile(BaseModel):
    model_config = ConfigDict(from_attributes=True, str_strip_whitespace=True)
    id: str
    email: str
    full_name: Optional[str] = None
    role: str
    is_active: bool
    created_at: Optional[str] = None

class AdminDashboardStats(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    products: int = Field(default=0, ge=0)
    orders: int = Field(default=0, ge=0)
    pending_orders: int = Field(default=0, ge=0)
    users: int = Field(default=0, ge=0)
    revenue: float = Field(default=0.0, ge=0.0)

class AdminVerifyResponse(BaseModel):
    verified: bool
    profile: AdminProfile
    timestamp: str

class AdminStatsResponse(BaseModel):
    verified: bool
    stats: AdminDashboardStats
    timestamp: str
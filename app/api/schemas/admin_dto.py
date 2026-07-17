"""
Admin Verification Schemas (DTOs)
=================================
Path: app/api/schemas/admin_dto.py
"""
from pydantic import BaseModel, ConfigDict, Field
from typing import Dict, Any, Optional

class AdminProfile(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: str
    email: str
    full_name: Optional[str] = None
    role: str
    is_active: bool
    created_at: Optional[str] = None  # Strictly str to accommodate ts_to_iso formatted output

class AdminVerifyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    verified: bool = Field(..., description="Confirmation of active admin status")
    profile: AdminProfile
    timestamp: str = Field(..., description="ISO-8601 UTC timestamp string")

class AdminDashboardStats(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    products: int = 0
    orders: int = 0
    pending_orders: int = 0
    users: int = 0
    revenue: float = 0.0

class AdminStatsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    verified: bool
    stats: AdminDashboardStats
    timestamp: str
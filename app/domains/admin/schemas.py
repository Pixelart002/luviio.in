"""
Admin Verification Schemas (DTOs)
=================================
Path: app/api/schemas/admin_dto.py
"""
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


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
DashboardWidgetId = Literal[
    "metrics",
    "revenue",
    "status",
    "orders",
    "inventory",
    "payments",
    "audit",
    "notifications",
    "stripe",
]

_DASHBOARD_WIDGET_IDS = frozenset({
    "metrics",
    "revenue",
    "status",
    "orders",
    "inventory",
    "payments",
    "audit",
    "notifications",
    "stripe",
})


class AdminDashboardLayout(BaseModel):
    """Strict DTO for per-admin dashboard layout persistence."""

    model_config = ConfigDict(extra="forbid")

    order: list[DashboardWidgetId] = Field(min_length=9, max_length=9)
    hidden: list[DashboardWidgetId] = Field(default_factory=list, max_length=9)
    sizes: dict[DashboardWidgetId, Literal["half", "full"]]

    @model_validator(mode="after")
    def validate_widget_layout(self) -> "AdminDashboardLayout":
        if len(set(self.order)) != len(self.order) or set(self.order) != _DASHBOARD_WIDGET_IDS:
            raise ValueError("order must contain each supported dashboard widget exactly once")
        if len(set(self.hidden)) != len(self.hidden):
            raise ValueError("hidden widgets must not contain duplicates")
        if set(self.sizes) != _DASHBOARD_WIDGET_IDS:
            raise ValueError("sizes must specify every supported dashboard widget")
        return self

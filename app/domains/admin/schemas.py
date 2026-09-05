"""
Admin Domain Schemas (DTOs)
===========================
Path: app/domains/admin/schemas.py
"""
from app.api.schemas.admin_dto import (
    AdminProfile,
    AdminDashboardStats,
    AdminVerifyResponse,
    AdminStatsResponse,
)

__all__ = [
    "AdminProfile",
    "AdminDashboardStats",
    "AdminVerifyResponse",
    "AdminStatsResponse",
]

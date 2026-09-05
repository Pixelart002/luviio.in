"""
RBAC Domain — Schemas (DTOs)
============================
Path: app/domains/rbac/schemas.py
"""
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class RolePermissionToggle(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    role: str = Field(..., description="Role to adjust (admin, manager, support, customer)")
    permission: str = Field(..., description="Permission key, e.g. 'coupons.create'")
    enabled: bool = Field(..., description="true = grant, false = revoke (overrides the static default)")


class UserActionControlUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    action: str = Field(..., description="Action key, e.g. 'checkout', 'access_premium_products'")
    enabled: bool = Field(..., description="false blocks this specific user from this action")
    reason: str = Field(default="", max_length=300, description="Why this control was set")


class MessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    message: str

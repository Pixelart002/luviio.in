"""
User Schemas (DTOs)
===================
Path: app/api/schemas/user_dto.py
"""
from pydantic import BaseModel, Field, field_validator
from typing import Any, List
from datetime import datetime

# ── Requests ──────────────────────────────────────────────────────────────────

class ProfileUpdate(BaseModel):
    full_name: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=20)

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: str | None) -> str | None:
        if v is not None:
            cleaned = ''.join(c for c in v if c.isdigit() or c == '+')
            if len(cleaned.replace('+', '')) < 10:
                raise ValueError("Phone number must be at least 10 digits")
            return cleaned
        return v

class AddressCreate(BaseModel):
    line1: str = Field(max_length=255)
    line2: str | None = Field(default=None, max_length=255)
    city: str = Field(max_length=100)
    state: str | None = Field(default=None, max_length=100)
    postal_code: str = Field(max_length=20)
    country: str = Field(min_length=2, max_length=2)
    is_default: bool = False

    @field_validator("country")
    @classmethod
    def validate_country(cls, v: str) -> str:
        return v.upper()

    @field_validator("postal_code")
    @classmethod
    def validate_postal(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Postal code is required")
        return v.strip()

class AdminUserUpdate(BaseModel):
    is_active: bool | None = None
    role: str | None = Field(default=None, pattern="^(customer|admin)$")

# ── Responses ─────────────────────────────────────────────────────────────────

class MessageResponse(BaseModel):
    message: str

class UserListResponse(BaseModel):
    items: List[dict]
    total: int
    page: int
    page_size: int
    pages: int
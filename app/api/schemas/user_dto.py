"""
User Schemas — Strict Pydantic DTOs
===================================
Path: app/api/schemas/user_dto.py
"""
from pydantic import BaseModel, ConfigDict, Field, field_validator
from typing import Any, Dict, List, Optional
from app.constants.user_messages import UserSecurityMessages

class ProfileUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    
    full_name: Optional[str] = Field(default=None, max_length=255)
    phone: Optional[str] = Field(default=None, max_length=20)

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            cleaned = ''.join(c for c in v if c.isdigit() or c == '+')
            if len(cleaned.replace('+', '')) < 10:
                raise ValueError(UserSecurityMessages.INVALID_PHONE)
            return cleaned
        return v

class AddressCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    
    line1: str = Field(..., max_length=255)
    line2: Optional[str] = Field(default=None, max_length=255)
    city: str = Field(..., max_length=100)
    state: Optional[str] = Field(default=None, max_length=100)
    postal_code: str = Field(..., max_length=20)
    country: str = Field(..., min_length=2, max_length=2)
    is_default: bool = False

    @field_validator("country")
    @classmethod
    def validate_country(cls, v: str) -> str:
        return v.upper()

    @field_validator("postal_code")
    @classmethod
    def validate_postal(cls, v: str) -> str:
        if not v.strip():
            raise ValueError(UserSecurityMessages.INVALID_POSTAL)
        return v.strip()

class AdminUserUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    
    is_active: Optional[bool] = None
    role: Optional[str] = Field(default=None, pattern="^(customer|admin|manager|support)$")

class MessageResponse(BaseModel):
    message: str

class UserListResponse(BaseModel):
    items: List[Dict[str, Any]]
    total: int
    page: int
    page_size: int
    pages: int
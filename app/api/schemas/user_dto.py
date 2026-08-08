"""
User Schemas (DTOs)
===================
Path: app/api/schemas/user_dto.py
"""
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator
from typing import Any, List, Optional
from app.constants.user_messages import UserSecurityMessages
from app.enums.roles import UserRole

class ProfileUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    full_name: Optional[str] = Field(default=None, min_length=2, max_length=255)
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
    
    # ── Core Address Fields ──
    line1: str = Field(..., min_length=3, max_length=255)
    line2: Optional[str] = Field(default=None, max_length=255)
    city: str = Field(..., min_length=2, max_length=100)
    state: Optional[str] = Field(default=None, max_length=100)
    postal_code: str = Field(..., min_length=3, max_length=20)
    country: str = Field(..., min_length=2, max_length=2)
    is_default: bool = False
    
    # ── 🔥 Enterprise B2B / Detail Fields ──
    full_name: Optional[str] = Field(default=None, max_length=255, description="Specific recipient name for this address")
    phone: Optional[str] = Field(default=None, max_length=20, description="Specific phone for this address")
    email: Optional[EmailStr] = Field(default=None, description="Specific email for this address")
    landmark: Optional[str] = Field(default=None, max_length=255)
    address_type: Optional[str] = Field(default="home", max_length=50, description="e.g., home, work, warehouse")
    company_name: Optional[str] = Field(default=None, max_length=255)
    gstin: Optional[str] = Field(default=None, max_length=15, description="Indian GST Identification Number")

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

    @field_validator("phone")
    @classmethod
    def validate_address_phone(cls, v: Optional[str]) -> Optional[str]:
        if v:
            cleaned = ''.join(c for c in v if c.isdigit() or c == '+')
            if len(cleaned.replace('+', '')) < 10:
                raise ValueError(UserSecurityMessages.INVALID_PHONE)
            return cleaned
        return v

    @field_validator("gstin")
    @classmethod
    def validate_gstin(cls, v: Optional[str]) -> Optional[str]:
        if v:
            cleaned = v.upper().strip()
            # Basic structural check for 15 digit Indian GSTIN format
            if len(cleaned) != 15:
                raise ValueError("GSTIN must be exactly 15 characters long.")
            return cleaned
        return v

class AdminUserUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    is_active: Optional[bool] = None
    role: Optional[UserRole] = None

class MessageResponse(BaseModel):
    message: str

class UserListResponse(BaseModel):
    items: List[dict[str, Any]]
    total: int
    page: int
    page_size: int
    pages: int
"""
Auth Schemas — Strict Pydantic DTOs
===================================
Path: app/api/schemas/auth_dto.py
"""
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator
from typing import Dict, Optional
from app.constants.auth_messages import AuthSecurityMessages

class RegisterRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)
    full_name: Optional[str] = Field(default=None, max_length=255)

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        if not any(c.isupper() for c in v) or not any(c.islower() for c in v) or not any(c.isdigit() for c in v):
            raise ValueError(AuthSecurityMessages.PASSWORD_STRENGTH)
            
        common_passwords = {"password", "password123", "12345678", "qwerty123", "admin123", "letmein123"}
        if v.lower() in common_passwords:
            raise ValueError(AuthSecurityMessages.PASSWORD_COMMON)
        return v

class LoginRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    email: EmailStr
    password: str

class ForgotPasswordRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    email: EmailStr

class ResetPasswordRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    new_password: str = Field(..., min_length=8, max_length=128)

    @field_validator("new_password")
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        if not any(c.isupper() for c in v) or not any(c.islower() for c in v) or not any(c.isdigit() for c in v):
            raise ValueError(AuthSecurityMessages.PASSWORD_STRENGTH)
        return v

class TokenResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    access_token: str
    token_type: str = "bearer"
    expires_in: Optional[int] = None

class LoginResponse(TokenResponse):
    user: Dict[str, str]

class MessageResponse(BaseModel):
    message: str

class SessionResponse(BaseModel):
    authenticated: bool
    user_id: str
    email: str
    expires_at: Optional[str] = None
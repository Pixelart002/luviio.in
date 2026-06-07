"""
Auth Schemas (DTOs)
===================
Path: app/api/schemas/auth_dto.py
"""
from pydantic import BaseModel, EmailStr, Field, field_validator

class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str | None = Field(default=None, max_length=255)

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit")
        if not any(c.islower() for c in v):
            raise ValueError("Password must contain at least one lowercase letter")
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
            
        common_passwords = {"password", "password123", "12345678", "qwerty123", "admin123", "letmein123"}
        if v.lower() in common_passwords:
            raise ValueError("This password is too common — please choose a stronger one")
        return v

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class ForgotPasswordRequest(BaseModel):
    email: EmailStr

class ResetPasswordRequest(BaseModel):
    new_password: str = Field(min_length=8, max_length=128)

    @field_validator("new_password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit")
        return v

class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    expires_in: int | None = None

class LoginResponse(TokenResponse):
    user: dict[str, str]

class MessageResponse(BaseModel):
    message: str
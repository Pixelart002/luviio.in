"""
Auth Schemas (DTOs)
===================
Path: app/api/schemas/auth_dto.py
"""
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator
from app.constants.auth_messages import AuthSecurityMessages, AuthRules

class RegisterRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str | None = Field(default=None, max_length=255)

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if not any(c.isupper() for c in v): raise ValueError(AuthSecurityMessages.PWD_UPPERCASE)
        if not any(c.isdigit() for c in v): raise ValueError(AuthSecurityMessages.PWD_DIGIT)
        if not any(c.islower() for c in v): raise ValueError(AuthSecurityMessages.PWD_LOWERCASE)
        if len(v) < 8: raise ValueError(AuthSecurityMessages.PWD_LENGTH)
            
        if v.lower() in AuthRules.COMMON_PASSWORDS:
            raise ValueError(AuthSecurityMessages.PWD_COMMON)
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
    new_password: str = Field(min_length=8, max_length=128)

    @field_validator("new_password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if not any(c.isupper() for c in v): raise ValueError(AuthSecurityMessages.PWD_UPPERCASE)
        if not any(c.isdigit() for c in v): raise ValueError(AuthSecurityMessages.PWD_DIGIT)
        if not any(c.islower() for c in v): raise ValueError(AuthSecurityMessages.PWD_LOWERCASE)
        return v
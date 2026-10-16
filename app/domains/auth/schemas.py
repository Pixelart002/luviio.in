"""
Auth Schemas (DTOs)
===================
Path: app/api/schemas/auth_dto.py
"""
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.constants.auth_messages import AuthRules, AuthSecurityMessages


class RegisterRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str | None = Field(default=None, max_length=255)
    terms_accepted: bool

    @field_validator("terms_accepted")
    @classmethod
    def require_terms_acceptance(cls, value: bool) -> bool:
        if not value:
            raise ValueError("You must accept the Terms & Conditions and Privacy Policy to register.")
        return value

    @field_validator("email")
    @classmethod
    def normalize_email(cls, v: str) -> str:
        return v.lower().strip()

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

    @field_validator("email")
    @classmethod
    def normalize_email(cls, v: str) -> str:
        return v.lower().strip()

class ForgotPasswordRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    email: EmailStr

    @field_validator("email")
    @classmethod
    def normalize_email(cls, v: str) -> str:
        return v.lower().strip()

class ResetPasswordRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    new_password: str = Field(min_length=8, max_length=128)

    @field_validator("new_password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if not any(c.isupper() for c in v): raise ValueError(AuthSecurityMessages.PWD_UPPERCASE)
        if not any(c.isdigit() for c in v): raise ValueError(AuthSecurityMessages.PWD_DIGIT)
        if not any(c.islower() for c in v): raise ValueError(AuthSecurityMessages.PWD_LOWERCASE)
        if len(v) < 8: raise ValueError(AuthSecurityMessages.PWD_LENGTH)
        if v.lower() in AuthRules.COMMON_PASSWORDS: raise ValueError(AuthSecurityMessages.PWD_COMMON)
        return v

class DeleteAccountRequest(BaseModel):
    password: str = Field(min_length=1, max_length=128)
    confirmation: str = Field(min_length=1, max_length=40)

    @field_validator("confirmation")
    @classmethod
    def require_confirmation_phrase(cls, value: str) -> str:
        if value.strip() != "DELETE MY ACCOUNT":
            raise ValueError("Type DELETE MY ACCOUNT to confirm account deletion.")
        return value.strip()

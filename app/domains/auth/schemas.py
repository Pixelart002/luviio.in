"""
Auth Domain Schemas (DTOs)
==========================
Path: app/domains/auth/schemas.py

Re-exports auth DTOs from the legacy api/schemas location so routers and
services can import them from the domain home.
"""
from app.api.schemas.auth_dto import (
    RegisterRequest,
    LoginRequest,
    ForgotPasswordRequest,
    ResetPasswordRequest,
)

__all__ = [
    "RegisterRequest",
    "LoginRequest",
    "ForgotPasswordRequest",
    "ResetPasswordRequest",
]

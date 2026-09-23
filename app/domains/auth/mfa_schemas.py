"""Request/response schemas for privileged MFA."""
from __future__ import annotations

from pydantic import BaseModel, Field


class MFAEnrollRequest(BaseModel):
    friendly_name: str = Field(default="Luviio Admin", min_length=1, max_length=80)


class MFAVerifyRequest(BaseModel):
    code: str = Field(min_length=6, max_length=8, pattern=r"^\d{6,8}$")


class MFAUnenrollRequest(BaseModel):
    factor_id: str = Field(min_length=1, max_length=100)

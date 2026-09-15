"""Admin DTOs for payment plugin management."""
from typing import Any, Dict

from pydantic import BaseModel, Field, field_validator


class ProviderToggleRequest(BaseModel):
    enabled: bool


class MethodToggleRequest(BaseModel):
    enabled: bool


class ProviderRegistrationRequest(BaseModel):
    provider_key: str = Field(min_length=2, max_length=64)
    display_name: str = Field(min_length=1, max_length=120)
    capabilities: Dict[str, Any] = Field(default_factory=dict)
    priority: int = Field(default=100, ge=0, le=10000)

    @field_validator("provider_key")
    @classmethod
    def normalize_key(cls, value: str) -> str:
        value = value.strip().lower()
        if not value.replace("_", "").replace("-", "").isalnum():
            raise ValueError("provider_key contains invalid characters")
        return value

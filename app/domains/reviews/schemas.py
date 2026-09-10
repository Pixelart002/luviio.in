"""Review DTOs."""
from pydantic import BaseModel, ConfigDict, Field, field_validator


class ReviewCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    rating: int = Field(..., ge=1, le=5)
    title: str | None = Field(default=None, max_length=120)
    body: str = Field(..., min_length=3, max_length=2000)

    @field_validator("body")
    @classmethod
    def body_not_blank(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 3:
            raise ValueError("Review must contain at least 3 characters.")
        return value


class ReviewModerationUpdate(BaseModel):
    status: str = Field(..., pattern=r"^(pending|approved|rejected)$")

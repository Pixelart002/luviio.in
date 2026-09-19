"""Product HTTP schemas owned by the Products domain."""
from typing import Any, Dict, List, Optional
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.constants.product_messages import ProductSecurityMessages


class CategoryCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    name: str = Field(..., min_length=2, max_length=100)
    slug: Optional[str] = Field(default=None, min_length=2, max_length=120, pattern=r"^[a-z0-9-]+$")
    description: Optional[str] = Field(default=None, max_length=1000)
    image_url: Optional[str] = None


class ProductAttributes(BaseModel):
    model_config = ConfigDict(extra="allow")
    color: Optional[str] = Field(default=None, alias="Color")
    material: Optional[str] = Field(default=None, alias="Material")
    finish_type: Optional[str] = Field(default=None, alias="Finish Type")
    weight: Optional[str] = Field(default=None, alias="Weight")
    dimensions: Optional[str] = Field(default=None, alias="Dimensions")


class ProductCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    name: str = Field(..., min_length=2, max_length=255)
    slug: Optional[str] = Field(default=None, min_length=2, max_length=280, pattern=r"^[a-z0-9-]+$")
    description: Optional[str] = None
    short_description: Optional[str] = Field(default=None, max_length=500)
    sku: Optional[str] = Field(default=None, max_length=100)
    category_id: Optional[str] = None
    price: Decimal = Field(..., gt=0, decimal_places=2)
    compare_price: Optional[Decimal] = Field(default=None, gt=0, decimal_places=2)
    stock: int = Field(default=0, ge=0)
    low_stock_threshold: int = Field(default=10, ge=0)
    weight_grams: Optional[int] = Field(default=None, ge=0)
    image_url: Optional[str] = None
    images: List[str] = Field(default_factory=list)
    attributes: Optional[Dict[str, Any]] = Field(default_factory=dict)
    hsn_code: str = Field(..., min_length=1, max_length=20)
    gst_percentage: int = Field(..., ge=0, le=100)
    country_of_origin: Optional[str] = Field(default=None, min_length=2, max_length=100)
    seo_title: Optional[str] = Field(default=None, max_length=70)
    seo_description: Optional[str] = Field(default=None, max_length=170)
    seo_keywords: Optional[str] = Field(default=None, max_length=500)
    canonical_url: Optional[str] = Field(default=None, max_length=2048)
    is_active: bool = True

    @field_validator("hsn_code")
    @classmethod
    def validate_hsn(cls, v: str) -> str:
        value = v.strip()
        if not value:
            raise ValueError("HSN code is required for every product.")
        return value

    @field_validator("country_of_origin")
    @classmethod
    def validate_country_of_origin(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        value = v.strip()
        return value or None

    @model_validator(mode="after")
    def compare_must_exceed_price(self):
        if self.compare_price and self.price and self.compare_price <= self.price:
            raise ValueError(ProductSecurityMessages.INVALID_COMPARE_PRICE)
        return self


class ProductUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    name: Optional[str] = Field(default=None, min_length=2, max_length=255)
    description: Optional[str] = None
    short_description: Optional[str] = Field(default=None, max_length=500)
    price: Optional[Decimal] = Field(default=None, gt=0, decimal_places=2)
    compare_price: Optional[Decimal] = Field(default=None, gt=0, decimal_places=2)
    stock: Optional[int] = Field(default=None, ge=0)
    low_stock_threshold: Optional[int] = Field(default=None, ge=0)
    weight_grams: Optional[int] = Field(default=None, ge=0)
    image_url: Optional[str] = None
    images: Optional[List[str]] = None
    attributes: Optional[Dict[str, Any]] = None
    category_id: Optional[str] = None
    hsn_code: Optional[str] = Field(default=None, min_length=1, max_length=20)
    gst_percentage: Optional[int] = Field(default=None, ge=0, le=100)
    country_of_origin: Optional[str] = Field(default=None, min_length=2, max_length=100)
    seo_title: Optional[str] = Field(default=None, max_length=70)
    seo_description: Optional[str] = Field(default=None, max_length=170)
    seo_keywords: Optional[str] = Field(default=None, max_length=500)
    canonical_url: Optional[str] = Field(default=None, max_length=2048)
    is_active: Optional[bool] = None

    @field_validator("hsn_code")
    @classmethod
    def validate_hsn(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        value = v.strip()
        if not value:
            raise ValueError("HSN code cannot be empty.")
        return value

    @field_validator("country_of_origin")
    @classmethod
    def validate_country_of_origin(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        value = v.strip()
        return value or None

    @model_validator(mode="after")
    def compare_must_exceed_price(self):
        if self.compare_price and self.price and self.compare_price <= self.price:
            raise ValueError(ProductSecurityMessages.INVALID_COMPARE_PRICE)
        return self

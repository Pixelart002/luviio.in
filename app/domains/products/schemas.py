"""Product HTTP schemas owned by the Products domain.

The public Product API is intentionally hardware-focused. Operational fields
such as SEO metadata, low-stock thresholds and derived discounts belong to
their owning domains/services and are not part of the product contract.
"""

from typing import Any, Dict, List, Optional
from uuid import UUID
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.constants.product_messages import ProductSecurityMessages


class CategoryCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    name: str = Field(..., min_length=2, max_length=100)
    slug: Optional[str] = Field(default=None, min_length=2, max_length=120, pattern=r"^[a-z0-9-]+$")
    description: Optional[str] = Field(default=None, max_length=1000)
    image_url: Optional[str] = None


class ProductSpecifications(BaseModel):
    """Common hardware attributes.

    Category-specific attributes belong in "specifications" rather than
    adding dozens of nullable columns to the products table.
    """

    model_config = ConfigDict(extra="allow", str_strip_whitespace=True, protected_namespaces=())

    brand: Optional[str] = Field(default=None, max_length=120)
    manufacturer: Optional[str] = Field(default=None, max_length=160)
    model_number: Optional[str] = Field(default=None, max_length=120)
    gtin: Optional[str] = Field(default=None, max_length=32)
    ean: Optional[str] = Field(default=None, max_length=32)
    part_number: Optional[str] = Field(default=None, max_length=120)
    key_features: List[str] = Field(default_factory=list, max_length=20)
    material: Optional[str] = Field(default=None, max_length=160)
    finish: Optional[str] = Field(default=None, max_length=120)
    color: Optional[str] = Field(default=None, max_length=80)
    size: Optional[str] = Field(default=None, max_length=120)
    dimensions: Optional[str] = Field(default=None, max_length=160)
    warranty: Optional[str] = Field(default=None, max_length=500)


class ProductCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid", protected_namespaces=())

    name: str = Field(..., min_length=2, max_length=255)
    slug: Optional[str] = Field(default=None, min_length=2, max_length=280, pattern=r"^[a-z0-9-]+$")
    sku: Optional[str] = Field(default=None, max_length=100)
    category_id: Optional[UUID] = None

    description: Optional[str] = None
    short_description: Optional[str] = Field(default=None, max_length=500)

    brand: Optional[str] = Field(default=None, max_length=120)
    manufacturer: Optional[str] = Field(default=None, max_length=160)
    model_number: Optional[str] = Field(default=None, max_length=120)
    gtin: Optional[str] = Field(default=None, max_length=32)
    ean: Optional[str] = Field(default=None, max_length=32)
    part_number: Optional[str] = Field(default=None, max_length=120)
    key_features: List[str] = Field(default_factory=list, max_length=20)
    material: Optional[str] = Field(default=None, max_length=160)
    finish: Optional[str] = Field(default=None, max_length=120)
    color: Optional[str] = Field(default=None, max_length=80)
    size: Optional[str] = Field(default=None, max_length=120)
    dimensions: Optional[str] = Field(default=None, max_length=160)
    specifications: Dict[str, Any] = Field(default_factory=dict)
    warranty: Optional[str] = Field(default=None, max_length=500)

    price: Decimal = Field(..., gt=0, decimal_places=2)
    compare_price: Optional[Decimal] = Field(default=None, gt=0, decimal_places=2)
    stock: int = Field(default=0, ge=0)
    weight_grams: Optional[int] = Field(default=None, ge=0)

    image_url: Optional[str] = Field(default=None, max_length=2048)
    images: List[str] = Field(default_factory=list, max_length=10)

    hsn_code: str = Field(..., min_length=4, max_length=8, pattern=r"^\d{4,8}$")
    gst_percentage: int = Field(..., ge=0, le=100)
    country_of_origin: Optional[str] = Field(default=None, min_length=2, max_length=100)
    is_active: bool = True

    @field_validator("hsn_code")
    @classmethod
    def validate_hsn(cls, value: str) -> str:
        value = value.strip()
        if not value.isdigit() or not 4 <= len(value) <= 8:
            raise ValueError("HSN code must contain 4-8 digits.")
        return value

    @field_validator("country_of_origin")
    @classmethod
    def validate_country_of_origin(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        value = value.strip()
        return value or None

    @model_validator(mode="after")
    def compare_must_exceed_price(self):
        if self.compare_price and self.compare_price <= self.price:
            raise ValueError(ProductSecurityMessages.INVALID_COMPARE_PRICE)
        return self


class ProductUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    name: Optional[str] = Field(default=None, min_length=2, max_length=255)
    slug: Optional[str] = Field(default=None, min_length=2, max_length=280, pattern=r"^[a-z0-9-]+$")
    sku: Optional[str] = Field(default=None, max_length=100, pattern=r"^\S(?:.*\S)?$")
    category_id: Optional[UUID] = None

    description: Optional[str] = None
    short_description: Optional[str] = Field(default=None, max_length=500)

    brand: Optional[str] = Field(default=None, max_length=120)
    manufacturer: Optional[str] = Field(default=None, max_length=160)
    model_number: Optional[str] = Field(default=None, max_length=120)
    gtin: Optional[str] = Field(default=None, max_length=32)
    ean: Optional[str] = Field(default=None, max_length=32)
    part_number: Optional[str] = Field(default=None, max_length=120)
    key_features: Optional[List[str]] = Field(default=None, max_length=20)
    material: Optional[str] = Field(default=None, max_length=160)
    finish: Optional[str] = Field(default=None, max_length=120)
    color: Optional[str] = Field(default=None, max_length=80)
    size: Optional[str] = Field(default=None, max_length=120)
    dimensions: Optional[str] = Field(default=None, max_length=160)
    specifications: Optional[Dict[str, Any]] = None
    warranty: Optional[str] = Field(default=None, max_length=500)

    price: Optional[Decimal] = Field(default=None, gt=0, decimal_places=2)
    compare_price: Optional[Decimal] = Field(default=None, gt=0, decimal_places=2)
    stock: Optional[int] = Field(default=None, ge=0)
    weight_grams: Optional[int] = Field(default=None, ge=0)

    image_url: Optional[str] = Field(default=None, max_length=2048)
    images: Optional[List[str]] = Field(default=None, max_length=10)

    hsn_code: Optional[str] = Field(default=None, min_length=4, max_length=8, pattern=r"^\d{4,8}$")
    gst_percentage: Optional[int] = Field(default=None, ge=0, le=100)
    country_of_origin: Optional[str] = Field(default=None, min_length=2, max_length=100)
    is_active: Optional[bool] = None

    @field_validator("hsn_code")
    @classmethod
    def validate_hsn(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        value = value.strip()
        if not value.isdigit() or not 4 <= len(value) <= 8:
            raise ValueError("HSN code must contain 4-8 digits.")
        return value

    @field_validator("country_of_origin")
    @classmethod
    def validate_country_of_origin(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        value = value.strip()
        return value or None

    @model_validator(mode="after")
    def compare_must_exceed_price(self):
        if self.compare_price is not None and self.price is not None and self.compare_price <= self.price:
            raise ValueError(ProductSecurityMessages.INVALID_COMPARE_PRICE)
        return self

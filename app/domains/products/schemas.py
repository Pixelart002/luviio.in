"""Product HTTP schemas owned by the Products domain."""

from decimal import Decimal
from typing import List, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.constants.product_messages import ProductRules, ProductSecurityMessages


class CategoryCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    name: str = Field(..., min_length=2, max_length=100)
    slug: Optional[str] = Field(default=None, min_length=2, max_length=120, pattern=r"^[a-z0-9-]+$")
    description: Optional[str] = Field(default=None, max_length=1000)
    image_url: Optional[str] = None


class ProductSpecifications(BaseModel):
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
    volume: Optional[Decimal] = Field(default=None, ge=0, decimal_places=3)
    volume_unit: Optional[Literal["ml", "L"]] = None
    quantity: Optional[Decimal] = Field(default=None, ge=0, decimal_places=3)
    quantity_unit: Optional[Literal["piece", "pack", "set", "pair", "box"]] = None
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
    volume: Optional[Decimal] = Field(default=None, ge=0, decimal_places=3)
    volume_unit: Optional[Literal["ml", "L"]] = None
    quantity: Optional[Decimal] = Field(default=None, ge=0, decimal_places=3)
    quantity_unit: Optional[Literal["piece", "pack", "set", "pair", "box"]] = None
    warranty: Optional[str] = Field(default=None, max_length=500)
    price: Decimal = Field(..., gt=0, decimal_places=2)
    compare_price: Optional[Decimal] = Field(default=None, gt=0, decimal_places=2)
    stock: int = Field(default=0, ge=0)
    weight: Optional[Decimal] = Field(default=None, ge=0, decimal_places=3)
    weight_unit: Optional[Literal["g", "kg"]] = None
    measurement_type: Optional[str] = Field(default=None, min_length=2, max_length=32)
    measurement_value: Optional[Decimal] = Field(default=None, ge=0, decimal_places=6)
    measurement_unit: Optional[str] = Field(default=None, min_length=1, max_length=32)
    image_url: Optional[str] = Field(default=None, max_length=2048)
    images: List[str] = Field(default_factory=list, max_length=10)
    hsn_code: str = Field(..., min_length=4, max_length=8, pattern=r"^\d{4,8}$")
    gst_percentage: int = Field(..., ge=0, le=100)
    country_of_origin: Optional[str] = Field(default=None, min_length=2, max_length=100)
    seo_title: Optional[str] = Field(default=None, min_length=1, max_length=70)
    seo_description: Optional[str] = Field(default=None, min_length=1, max_length=170)
    canonical_url: Optional[str] = Field(default=None, max_length=2048)
    is_active: bool = True

    @field_validator("hsn_code")
    @classmethod
    def validate_hsn(cls, value: str) -> str:
        value = value.strip()
        if not value.isdigit() or not 4 <= len(value) <= 8:
            raise ValueError("HSN code must contain 4-8 digits.")
        return value

    @field_validator("gst_percentage")
    @classmethod
    def validate_gst(cls, value: int) -> int:
        if value not in ProductRules.LEGAL_GST_SLABS:
            raise ValueError(ProductSecurityMessages.INVALID_GST_SLAB)
        return value

    @model_validator(mode="after")
    def validate_measurement_units(self):
        if self.measurement_value is not None and (self.measurement_type is None or self.measurement_unit is None):
            raise ValueError("measurement_type and measurement_unit are required when measurement_value is provided.")
        if self.measurement_type is not None and self.measurement_unit is None:
            raise ValueError("measurement_unit is required when measurement_type is provided.")
        if self.measurement_unit is not None and self.measurement_type is None:
            raise ValueError("measurement_type is required when measurement_unit is provided.")
        if self.volume is not None and self.volume_unit is None:
            raise ValueError("volume_unit is required when volume is provided.")
        if self.quantity is not None and self.quantity_unit is None:
            raise ValueError("quantity_unit is required when quantity is provided.")
        if self.weight is not None and self.weight_unit is None:
            raise ValueError("weight_unit is required when weight is provided.")
        return self

    @model_validator(mode="after")
    def compare_must_exceed_price(self):
        if self.compare_price and self.compare_price <= self.price:
            raise ValueError(ProductSecurityMessages.INVALID_COMPARE_PRICE)
        return self


class ProductUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid", protected_namespaces=())
    name: Optional[str] = Field(default=None, min_length=2, max_length=255)
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
    key_features: Optional[List[str]] = Field(default=None, max_length=20)
    material: Optional[str] = Field(default=None, max_length=160)
    finish: Optional[str] = Field(default=None, max_length=120)
    color: Optional[str] = Field(default=None, max_length=80)
    size: Optional[str] = Field(default=None, max_length=120)
    dimensions: Optional[str] = Field(default=None, max_length=160)
    volume: Optional[Decimal] = Field(default=None, ge=0, decimal_places=3)
    volume_unit: Optional[Literal["ml", "L"]] = None
    quantity: Optional[Decimal] = Field(default=None, ge=0, decimal_places=3)
    quantity_unit: Optional[Literal["piece", "pack", "set", "pair", "box"]] = None
    warranty: Optional[str] = Field(default=None, max_length=500)
    price: Optional[Decimal] = Field(default=None, gt=0, decimal_places=2)
    compare_price: Optional[Decimal] = Field(default=None, gt=0, decimal_places=2)
    stock: Optional[int] = Field(default=None, ge=0)
    weight: Optional[Decimal] = Field(default=None, ge=0, decimal_places=3)
    weight_unit: Optional[Literal["g", "kg"]] = None
    measurement_type: Optional[str] = Field(default=None, min_length=2, max_length=32)
    measurement_value: Optional[Decimal] = Field(default=None, ge=0, decimal_places=6)
    measurement_unit: Optional[str] = Field(default=None, min_length=1, max_length=32)
    image_url: Optional[str] = Field(default=None, max_length=2048)
    images: Optional[List[str]] = Field(default=None, max_length=10)
    hsn_code: Optional[str] = Field(default=None, min_length=4, max_length=8, pattern=r"^\d{4,8}$")
    gst_percentage: Optional[int] = Field(default=None, ge=0, le=100)
    country_of_origin: Optional[str] = Field(default=None, min_length=2, max_length=100)
    seo_title: Optional[str] = Field(default=None, min_length=1, max_length=70)
    seo_description: Optional[str] = Field(default=None, min_length=1, max_length=170)
    canonical_url: Optional[str] = Field(default=None, max_length=2048)
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

    @field_validator("gst_percentage")
    @classmethod
    def validate_gst(cls, value: Optional[int]) -> Optional[int]:
        if value is not None and value not in ProductRules.LEGAL_GST_SLABS:
            raise ValueError(ProductSecurityMessages.INVALID_GST_SLAB)
        return value

    @model_validator(mode="after")
    def validate_measurement_units(self):
        if self.measurement_value is not None and (self.measurement_type is None or self.measurement_unit is None):
            raise ValueError("measurement_type and measurement_unit are required when measurement_value is provided.")
        if self.measurement_type is not None and self.measurement_unit is None:
            raise ValueError("measurement_unit is required when measurement_type is provided.")
        if self.measurement_unit is not None and self.measurement_type is None:
            raise ValueError("measurement_type is required when measurement_unit is provided.")
        if self.volume is not None and self.volume_unit is None:
            raise ValueError("volume_unit is required when volume is provided.")
        if self.quantity is not None and self.quantity_unit is None:
            raise ValueError("quantity_unit is required when quantity is provided.")
        return self

    @model_validator(mode="after")
    def compare_must_exceed_price(self):
        if self.compare_price is not None and self.price is not None and self.compare_price <= self.price:
            raise ValueError(ProductSecurityMessages.INVALID_COMPARE_PRICE)
        return self

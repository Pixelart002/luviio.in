from decimal import Decimal
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.constants.product_messages import ProductRules, ProductSecurityMessages
from app.domains.products.measurements import ProductPackage


class CategoryCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    name: str = Field(..., min_length=2, max_length=100)
    slug: str = Field(..., min_length=2, max_length=120, pattern=r"^[a-z0-9-]+$")
    description: Optional[str] = Field(default=None, max_length=1000)
    image_url: Optional[str] = None


class ProductAttributes(BaseModel):
    model_config = ConfigDict(extra="allow")
    color: Optional[str] = Field(default=None, alias="Color")
    material: Optional[str] = Field(default=None, alias="Material")
    finish_type: Optional[str] = Field(default=None, alias="Finish Type")
    weight: Optional[str] = Field(default=None, alias="Weight")
    dimensions: Optional[str] = Field(default=None, alias="Dimensions")


class ProductFields(BaseModel):
    description: Optional[str] = None
    short_description: Optional[str] = Field(default=None, max_length=500)
    sku: Optional[str] = Field(default=None, max_length=100)
    category_id: Optional[str] = None
    price: Optional[Decimal] = Field(default=None, gt=0, decimal_places=2)
    compare_price: Optional[Decimal] = Field(default=None, gt=0, decimal_places=2)
    stock: Optional[int] = Field(default=None, ge=0)
    low_stock_threshold: Optional[int] = Field(default=10, ge=0)
    weight_grams: Optional[int] = Field(default=None, ge=0)
    weight: Optional[Decimal] = Field(default=None, gt=0)
    weight_unit: Optional[str] = Field(default=None, pattern=r"^(g|kg)$")
    volume: Optional[Decimal] = Field(default=None, gt=0)
    volume_unit: Optional[str] = Field(default=None, pattern=r"^(ml|L)$")
    length: Optional[Decimal] = Field(default=None, gt=0)
    width: Optional[Decimal] = Field(default=None, gt=0)
    height: Optional[Decimal] = Field(default=None, gt=0)
    dimension_unit: Optional[str] = Field(default=None, pattern=r"^(mm|cm|in)$")
    quantity: Optional[Decimal] = Field(default=None, gt=0)
    quantity_unit: Optional[str] = Field(default=None, pattern=r"^(piece|pack|set)$")
    package: Optional[ProductPackage] = None
    image_url: Optional[str] = None
    images: List[str] = Field(default_factory=list)
    attributes: Dict[str, Any] = Field(default_factory=dict)
    hsn_code: Optional[str] = Field(default="9988", min_length=4, max_length=20, pattern=r"^[0-9]+$")
    gst_percentage: Optional[int] = Field(default=18)
    brand: Optional[str] = Field(default=None, max_length=120)
    manufacturer: Optional[str] = Field(default=None, max_length=120)
    model_number: Optional[str] = Field(default=None, max_length=120)
    gtin: Optional[str] = Field(default=None, max_length=20)
    ean: Optional[str] = Field(default=None, max_length=20)
    part_number: Optional[str] = Field(default=None, max_length=120)
    key_features: List[str] = Field(default_factory=list)
    material: Optional[str] = Field(default=None, max_length=120)
    finish: Optional[str] = Field(default=None, max_length=120)
    color: Optional[str] = Field(default=None, max_length=80)
    size: Optional[str] = Field(default=None, max_length=80)
    dimensions: Optional[str] = Field(default=None, max_length=120)
    specifications: Dict[str, Any] = Field(default_factory=dict)
    warranty: Optional[str] = Field(default=None, max_length=120)
    country_of_origin: Optional[str] = Field(default=None, max_length=80)
    is_active: Optional[bool] = True

    @field_validator("gst_percentage")
    @classmethod
    def validate_gst(cls, value: Optional[int]) -> Optional[int]:
        if value is not None and value not in ProductRules.LEGAL_GST_SLABS:
            raise ValueError(ProductSecurityMessages.INVALID_GST_SLAB)
        return value


class ProductCreate(ProductFields):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    name: str = Field(..., min_length=2, max_length=255)
    slug: Optional[str] = Field(default=None, min_length=2, max_length=280, pattern=r"^[a-z0-9-]+$")
    price: Decimal = Field(..., gt=0, decimal_places=2)
    compare_price: Optional[Decimal] = Field(default=None, gt=0, decimal_places=2)
    stock: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def compare_must_exceed_price(self):
        if self.compare_price is not None and self.compare_price <= self.price:
            raise ValueError(ProductSecurityMessages.INVALID_COMPARE_PRICE)
        return self

    @model_validator(mode="after")
    def require_measurement_units(self):
        if self.volume is not None and self.volume_unit is None:
            raise ValueError("volume_unit is required when volume is provided")
        if any(value is not None for value in (self.length, self.width, self.height)) and self.dimension_unit is None:
            raise ValueError("dimension_unit is required when dimensions are provided")
        if self.quantity is not None and self.quantity_unit is None:
            raise ValueError("quantity_unit is required when quantity is provided")
        return self


class ProductUpdate(ProductFields):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    name: Optional[str] = Field(default=None, min_length=2, max_length=255)
    slug: Optional[str] = Field(default=None, min_length=2, max_length=280, pattern=r"^[a-z0-9-]+$")
    is_active: Optional[bool] = None

    @model_validator(mode="after")
    def compare_must_exceed_price(self):
        if self.price is not None and self.compare_price is not None and self.compare_price <= self.price:
            raise ValueError(ProductSecurityMessages.INVALID_COMPARE_PRICE)
        return self

    @model_validator(mode="after")
    def require_measurement_units(self):
        if self.volume is not None and self.volume_unit is None:
            raise ValueError("volume_unit is required when volume is provided")
        if any(value is not None for value in (self.length, self.width, self.height)) and self.dimension_unit is None:
            raise ValueError("dimension_unit is required when dimensions are provided")
        if self.quantity is not None and self.quantity_unit is None:
            raise ValueError("quantity_unit is required when quantity is provided")
        return self

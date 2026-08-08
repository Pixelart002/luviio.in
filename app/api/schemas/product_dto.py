"""
Product Schemas (DTOs)
======================
Path: app/api/schemas/product_dto.py
"""
from pydantic import BaseModel, ConfigDict, Field, model_validator, field_validator
from decimal import Decimal
from typing import Any, Dict, List, Optional
from app.constants.product_messages import ProductSecurityMessages, ProductRules

class CategoryCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    name: str = Field(..., min_length=2, max_length=100)
    slug: str = Field(..., min_length=2, max_length=120, pattern=r"^[a-z0-9-]+$")
    description: Optional[str] = Field(default=None, max_length=1000)
    image_url: Optional[str] = None

# 🔥 SMART ATTRIBUTES SCHEMA
class ProductAttributes(BaseModel):
    # 'extra="allow"' ka matlab: Jo keys define nahi hain (custom), unko block mat karo, accept kar lo!
    model_config = ConfigDict(extra='allow')

    # 🟢 Native / Pre-defined Attributes (Admin inko directly use kar sakta hai)
    color: Optional[str] = Field(default=None, alias="Color")
    material: Optional[str] = Field(default=None, alias="Material")
    finish_type: Optional[str] = Field(default=None, alias="Finish Type")
    weight: Optional[str] = Field(default=None, alias="Weight")
    dimensions: Optional[str] = Field(default=None, alias="Dimensions")


class ProductCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    name: str = Field(..., min_length=2, max_length=255)
    slug: str = Field(..., min_length=2, max_length=280, pattern=r"^[a-z0-9-]+$")
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
    
    # 🔥 Accept ProductAttributes model, but convert to dict on validation
    attributes: Optional[Dict[str, Any]] = Field(default_factory=dict)
    
    hsn_code: Optional[str] = Field(default="9988", max_length=20)
    gst_percentage: Optional[int] = Field(default=18)
    is_active: bool = True

    @field_validator("gst_percentage")
    @classmethod
    def validate_gst(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and v not in ProductRules.LEGAL_GST_SLABS:
            raise ValueError(ProductSecurityMessages.INVALID_GST_SLAB)
        return v

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
    
    # 🔥 Same update logic
    attributes: Optional[Dict[str, Any]] = None
    
    category_id: Optional[str] = None
    hsn_code: Optional[str] = Field(default=None, max_length=20)
    gst_percentage: Optional[int] = None
    is_active: Optional[bool] = None

    @field_validator("gst_percentage")
    @classmethod
    def validate_gst(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and v not in ProductRules.LEGAL_GST_SLABS:
            raise ValueError(ProductSecurityMessages.INVALID_GST_SLAB)
        return v

    @model_validator(mode="after")
    def compare_must_exceed_price(self):
        if self.compare_price and self.price and self.compare_price <= self.price:
            raise ValueError(ProductSecurityMessages.INVALID_COMPARE_PRICE)
        return self
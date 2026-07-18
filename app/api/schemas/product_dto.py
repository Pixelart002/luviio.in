"""
Product Schemas (DTOs)
======================
Path: app/api/schemas/product_dto.py
"""
from pydantic import BaseModel, ConfigDict, Field, model_validator
from decimal import Decimal
from typing import List, Optional
from app.constants.product_messages import ProductSecurityMessages

class CategoryCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    name: str = Field(max_length=100)
    slug: str = Field(max_length=120, pattern=r"^[a-z0-9-]+$")
    description: Optional[str] = None
    image_url: Optional[str] = None

class ProductCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    name: str = Field(max_length=255)
    slug: str = Field(max_length=280, pattern=r"^[a-z0-9-]+$")
    description: Optional[str] = None
    short_description: Optional[str] = None
    sku: Optional[str] = Field(default=None, max_length=100)
    category_id: Optional[str] = None
    price: Decimal = Field(gt=0, decimal_places=2)
    compare_price: Optional[Decimal] = Field(default=None, gt=0, decimal_places=2)
    stock: int = Field(ge=0, default=0)
    low_stock_threshold: int = Field(default=10, ge=0)
    weight_grams: Optional[int] = Field(default=None, ge=0)
    image_url: Optional[str] = None
    images: List[str] = Field(default_factory=list)
    is_active: bool = True

    @model_validator(mode="after")
    def compare_must_exceed_price(self):
        if self.compare_price and self.price and self.compare_price <= self.price:
            raise ValueError(ProductSecurityMessages.INVALID_COMPARE_PRICE)
        return self

class ProductUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    name: Optional[str] = None
    description: Optional[str] = None
    short_description: Optional[str] = None
    price: Optional[Decimal] = Field(default=None, gt=0)
    compare_price: Optional[Decimal] = None
    stock: Optional[int] = Field(default=None, ge=0)
    low_stock_threshold: Optional[int] = None
    image_url: Optional[str] = None
    images: Optional[List[str]] = None
    category_id: Optional[str] = None
    is_active: Optional[bool] = None
    weight_grams: Optional[int] = None

    @model_validator(mode="after")
    def compare_must_exceed_price(self):
        if self.compare_price and self.price and self.compare_price <= self.price:
            raise ValueError(ProductSecurityMessages.INVALID_COMPARE_PRICE)
        return self

class MessageResponse(BaseModel):
    message: str
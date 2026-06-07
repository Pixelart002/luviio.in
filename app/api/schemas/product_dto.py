"""
Product Schemas (DTOs)
======================
Path: app/api/schemas/product_dto.py
"""
from pydantic import BaseModel, Field, model_validator
from decimal import Decimal
from typing import List, Optional

class CategoryCreate(BaseModel):
    name: str = Field(max_length=100)
    slug: str = Field(max_length=120, pattern=r"^[a-z0-9-]+$")
    description: str | None = None
    image_url: str | None = None

class ProductCreate(BaseModel):
    name: str = Field(max_length=255)
    slug: str = Field(max_length=280, pattern=r"^[a-z0-9-]+$")
    description: str | None = None
    short_description: str | None = None
    sku: str | None = Field(default=None, max_length=100)
    category_id: str | None = None
    price: Decimal = Field(gt=0, decimal_places=2)
    compare_price: Decimal | None = Field(default=None, gt=0, decimal_places=2)
    stock: int = Field(ge=0, default=0)
    low_stock_threshold: int = Field(default=10, ge=0)
    weight_grams: int | None = Field(default=None, ge=0)
    image_url: str | None = None
    images: list[str] = Field(default_factory=list)
    is_active: bool = True

    @model_validator(mode="after")
    def compare_must_exceed_price(self):
        if self.compare_price and self.price and self.compare_price <= self.price:
            raise ValueError("compare_price must be greater than price")
        return self

class ProductUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    short_description: str | None = None
    price: Decimal | None = Field(default=None, gt=0)
    compare_price: Decimal | None = None
    stock: int | None = Field(default=None, ge=0)
    low_stock_threshold: int | None = None
    image_url: str | None = None
    images: list[str] | None = None
    category_id: str | None = None
    is_active: bool | None = None
    weight_grams: int | None = None

    @model_validator(mode="after")
    def compare_must_exceed_price(self):
        if self.compare_price and self.price and self.compare_price <= self.price:
            raise ValueError("compare_price must be greater than price")
        return self

class MessageResponse(BaseModel):
    message: str
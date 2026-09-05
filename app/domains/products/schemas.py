"""
Products Domain Schemas (DTOs)
==============================
Path: app/domains/products/schemas.py
"""
from app.api.schemas.product_dto import (
    CategoryCreate,
    ProductAttributes,
    ProductCreate,
    ProductUpdate,
)

__all__ = [
    "CategoryCreate",
    "ProductAttributes",
    "ProductCreate",
    "ProductUpdate",
]

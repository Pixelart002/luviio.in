"""
Products Domain
===============
Path: app/domains/products/__init__.py

Catalog: product CRUD, image processing, public listing & search.
"""
from app.domains.products.service import ProductService
from app.domains.products.policy import ProductPolicy
from app.domains.products.repository import AsyncProductRepository

__all__ = ["ProductService", "ProductPolicy", "AsyncProductRepository"]

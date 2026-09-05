"""
Cart Domain Router
==================
Path: app/domains/cart/router.py

FastAPI router exposing /api/v1/cart/* endpoints.
"""
from app.api.v1.routers.cart import router

__all__ = ["router"]

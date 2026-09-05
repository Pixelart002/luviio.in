"""
Products Domain Router
======================
Path: app/domains/products/router.py

FastAPI router exposing /api/v1/products/* endpoints.
"""
from app.api.v1.routers.products import router

__all__ = ["router"]

"""
Orders Domain Router
====================
Path: app/domains/orders/router.py

FastAPI router exposing /api/v1/orders/* endpoints.
"""
from app.api.v1.routers.orders import router

__all__ = ["router"]

"""
Payments Domain Router
======================
Path: app/domains/payments/router.py

FastAPI router exposing /api/v1/payments/* endpoints.
"""
from app.api.v1.routers.payments import router

__all__ = ["router"]

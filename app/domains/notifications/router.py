"""
Notifications Domain Router
===========================
Path: app/domains/notifications/router.py

FastAPI router exposing /api/v1/push/* endpoints.
"""
from app.api.v1.routers.push import router

__all__ = ["router"]

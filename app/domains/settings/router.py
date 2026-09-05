"""
Settings Domain Router
======================
Path: app/domains/settings/router.py

FastAPI router exposing /api/v1/settings/* endpoints.
"""
from app.api.v1.routers.settings import router

__all__ = ["router"]

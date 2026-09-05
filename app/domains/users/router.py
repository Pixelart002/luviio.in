"""
Users Domain Router
===================
Path: app/domains/users/router.py

FastAPI router exposing /api/v1/users/* endpoints.
"""
from app.api.v1.routers.users import router

__all__ = ["router"]

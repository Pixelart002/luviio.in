"""
Auth Domain Router
==================
Path: app/domains/auth/router.py

FastAPI router exposing /api/v1/auth/* endpoints. Re-exports the legacy
router under the domain namespace.
"""
from app.api.v1.routers.auth import router

__all__ = ["router"]

"""
Admin Domain Router
===================
Path: app/domains/admin/router.py

FastAPI router exposing /api/v1/admin/* verification endpoints.
"""
from app.api.v1.routers.admin_verify import router

__all__ = ["router"]

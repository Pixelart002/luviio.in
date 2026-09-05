"""
Settings Domain — Admin Settings Service
========================================
Path: app/domains/settings/admin_service.py

Re-exports AdminSettingsService (admin-scoped settings view/mutation).
"""
from app.services.settings.admin_service import AdminSettingsService

__all__ = ["AdminSettingsService"]

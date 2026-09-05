"""
Settings Domain — Manager Settings Service
==========================================
Path: app/domains/settings/manager_service.py

Re-exports ManagerSettingsService (manager-scoped settings view).
"""
from app.services.settings.manager_service import ManagerSettingsService

__all__ = ["ManagerSettingsService"]

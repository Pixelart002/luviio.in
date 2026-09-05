"""
Settings Domain Service
=======================
Path: app/domains/settings/service.py

Facade re-exporting the legacy SettingsService.
"""
from app.services.settings.service import SettingsService

__all__ = ["SettingsService"]

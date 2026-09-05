"""
Settings Domain — Customer Settings Service
===========================================
Path: app/domains/settings/customer_service.py

Re-exports CustomerSettingsService (public/customer-visible settings).
"""
from app.services.settings.customer_service import CustomerSettingsService

__all__ = ["CustomerSettingsService"]

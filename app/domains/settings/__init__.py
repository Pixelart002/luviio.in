"""
Settings Domain
===============
Path: app/domains/settings/__init__.py

Owns dynamic system settings: the settings core engine, plus role-scoped
views (admin / manager / customer) and the persistence repository.
"""
from app.domains.settings.service import SettingsService
from app.domains.settings.policy import SettingsPolicy
from app.domains.settings.repository import AsyncSettingsRepository
from app.domains.settings.core_engine import SettingsCoreEngine
from app.domains.settings.admin_service import AdminSettingsService
from app.domains.settings.customer_service import CustomerSettingsService
from app.domains.settings.manager_service import ManagerSettingsService

__all__ = [
    "SettingsService",
    "SettingsPolicy",
    "AsyncSettingsRepository",
    "SettingsCoreEngine",
    "AdminSettingsService",
    "CustomerSettingsService",
    "ManagerSettingsService",
]

"""
Settings Domain Policy
======================
Path: app/domains/settings/policy.py

ABAC policy governing who may read/update which settings.
"""
from app.permissions.policies.settings_policies import SettingsPolicy

__all__ = ["SettingsPolicy"]

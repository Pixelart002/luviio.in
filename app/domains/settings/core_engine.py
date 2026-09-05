"""
Settings Domain — Core Engine
=============================
Path: app/domains/settings/core_engine.py

Re-exports the canonical SettingsCoreEngine that resolves setting values,
defaults, and type coercion.
"""
from app.services.settings.core_engine import SettingsCoreEngine

__all__ = ["SettingsCoreEngine"]

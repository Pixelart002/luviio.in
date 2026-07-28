"""
Settings Domain Events
======================
Path: app/events/settings_events.py
"""
from dataclasses import dataclass
from typing import Any

@dataclass
class SettingUpdatedEvent:
    key: str
    old_value: Any
    new_value: Any
    updated_by: str
    reason: str

@dataclass
class SettingResetEvent:
    key: str
    restored_value: Any
    reset_by: str
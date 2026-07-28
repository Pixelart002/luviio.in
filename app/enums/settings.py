"""
Settings Enums
==============
Path: app/enums/settings.py
"""
from enum import Enum

class SettingCategory(str, Enum):
    GENERAL = "general"
    FINANCIAL = "financial"
    FEATURE_FLAG = "feature_flag"
    OPERATIONAL = "operational"
    UI_UX = "ui_ux"

class SettingDataType(str, Enum):
    BOOLEAN = "boolean"
    INTEGER = "integer"
    DECIMAL = "decimal"
    STRING = "string"
    JSON = "json"
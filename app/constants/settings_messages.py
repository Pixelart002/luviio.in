"""
Settings Messages & Rules (SSOT)
================================
Path: app/constants/settings_messages.py
"""

class SettingsMessages:
    UPDATED = "System setting updated successfully."
    RESET = "System setting restored to default value."
    FETCHED = "System settings retrieved successfully."

class SettingsSecurityMessages:
    NOT_FOUND = "The requested setting key does not exist in the master registry."
    LOCKED_SETTING = "Security Block: This is a system-locked setting. Only Super Admins can modify it."
    TYPE_MISMATCH = "Invalid data type provided. Expected {expected_type}."
    UNAUTHORIZED_ACCESS = "You do not have permission to modify settings in this category."
    DB_OPERATION_FAILED = "An internal database error occurred while updating system settings."

class SettingsRules:
    CACHE_TTL_SECONDS = 300  # 5 minutes in-memory cache
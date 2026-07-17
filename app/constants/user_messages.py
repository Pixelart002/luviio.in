"""
User Profile Messages & Security Strings (SSOT)
===============================================
Path: app/constants/user_messages.py
"""

class UserMessages:
    PROFILE_UPDATED = "Profile metadata successfully synchronized."
    ADDRESS_ADDED = "New shipping address securely persisted to vault."
    ADDRESS_DELETED = "Address successfully purged from your profile."
    USER_UPDATED = "User profile override successfully committed."

class UserSecurityMessages:
    ADDRESS_NOT_FOUND = "The requested address does not exist or has been removed."
    ADDRESS_LOCKED = "Cannot delete this address because it is currently linked to a pending or shipped order."
    ADDRESS_LIMIT_EXCEEDED = "You have reached the maximum allowed limit of 10 addresses."
    USER_NOT_FOUND = "The requested user profile could not be found."
    SELF_DEMOTION_PREVENTED = "Security Guard: You cannot demote your own role or deactivate your own account."
    NO_FIELDS_TO_UPDATE = "No valid fields were provided for the update operation."
    INVALID_PHONE = "Phone number must contain at least 10 valid digits."
    INVALID_POSTAL = "Postal code is required and cannot be empty."
    DB_OPERATION_FAILED = "An internal database error occurred. Please try again."
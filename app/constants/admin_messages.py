"""
Admin Messages & Security Rules (SSOT)
======================================
Path: app/constants/admin_messages.py
"""

class AdminSecurityMessages:
    PROFILE_NOT_FOUND = "No active database profile mapped to this UID."
    UNAUTHORIZED_ROLE = "Security Violation: Non-admin or inactive access attempt blocked."

class AdminMessages:
    VERIFIED = "Administrator access verified successfully."
    STATS_FETCHED = "Dashboard metrics aggregated successfully."
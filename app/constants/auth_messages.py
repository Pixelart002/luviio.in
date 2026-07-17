"""
Authentication Messages & Security Strings (SSOT)
=================================================
Path: app/constants/auth_messages.py
"""

class AuthMessages:
    REGISTER_SUCCESS = "If this email is new, a confirmation link has been sent."
    LOGOUT_SUCCESS = "Logged out successfully."
    FORGOT_SUCCESS = "If this email exists, a password reset link has been sent."
    RESET_SUCCESS = "Password updated successfully."

class AuthSecurityMessages:
    INVALID_CREDENTIALS = "Invalid email or password."
    INVALID_REFRESH = "Invalid or expired session token. Please sign in again."
    TOO_MANY_ATTEMPTS = "Too many failed attempts. Please try again later."
    EMAIL_IN_USE = "Registration failed: This email address is already registered."
    PASSWORD_COMMON = "This password is too common — please choose a stronger one."
    PASSWORD_STRENGTH = "Password must contain at least one uppercase letter, one lowercase letter, and one digit."
    UNAUTHORIZED_RESET = "Security Violation: You are not authorized to reset another user's password."
    SESSION_VALID = "Active session authenticated successfully."
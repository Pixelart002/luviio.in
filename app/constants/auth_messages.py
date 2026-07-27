"""
Auth Messages & Security Rules (SSOT)
=====================================
Path: app/constants/auth_messages.py
"""

class AuthMessages:
    REGISTER_SUCCESS = "If this email is new, a confirmation link has been sent."
    LOGOUT_SUCCESS = "Logged out successfully."
    FORGOT_PWD_SUCCESS = "If this email exists, a password reset link has been sent."
    RESET_PWD_SUCCESS = "Password updated successfully."
    SESSION_VALID = "Session is valid and active."

class AuthSecurityMessages:
    TOO_MANY_REQUESTS = "Too many attempts. Please try again later."
    INVALID_CREDENTIALS = "Invalid email or password."
    INVALID_REFRESH_TOKEN = "Invalid or expired refresh token."
    REGISTRATION_FAILED = "Registration failed: Email may already be in use or invalid."
    RESET_FAILED = "Password reset failed: {reason}"
    MISSING_AUTH_HEADER = "Missing or invalid Authorization Bearer token."
    
    # Password Complexity Rules
    PWD_UPPERCASE = "Password must contain at least one uppercase letter."
    PWD_DIGIT = "Password must contain at least one digit."
    PWD_LOWERCASE = "Password must contain at least one lowercase letter."
    PWD_LENGTH = "Password must be at least 8 characters long."
    PWD_COMMON = "This password is too common — please choose a stronger one."

class AuthRules:
    MAX_LOGIN_ATTEMPTS = 5
    LOGIN_WINDOW_SECONDS = 300
    LOGIN_COOLDOWN_SECONDS = 900
    COMMON_PASSWORDS = {
        "password", "password123", "12345678", "qwerty123", 
        "admin123", "letmein123", "luviio123", "welcome123"
    }
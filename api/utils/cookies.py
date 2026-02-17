import os
from fastapi import Response

# --- 1. THE STANDARD (Constants) ---
# Enterprise Rule: Hardcoded strings se bacho. Constants use karo.
IS_PROD = os.environ.get("VERCEL_ENV") == "production"

class CookieConfig:
    ACCESS_KEY = "access_token"
    REFRESH_KEY = "refresh_token"
    SESSION_KEY = "session_id"
    STATE_KEY = "oauth_state"  # OAuth Security ke liye
    
    # Lifetimes (Seconds)
    ACCESS_LIFETIME = 3600        # 1 Hour
    REFRESH_LIFETIME = 2592000    # 30 Days
    STATE_LIFETIME = 300          # 5 Minutes (Short lived for security)

    # Security Flags (The Enterprise Standard)
    # HttpOnly: JavaScript access block karta hai (XSS Protection)
    # Secure: Sirf HTTPS pe chalega (Production me)
    # SameSite: CSRF Protection ('Lax' auth ke liye best hai)
    BASE_FLAGS = {
        "httponly": True,
        "secure": IS_PROD, 
        "samesite": "lax",
        "path": "/",
        # "domain": ".luviio.in"  # Uncomment agar subdomains (app.luviio.in) share karna ho
    }

# --- 2. THE DELEGATION (Manager Functions) ---

def set_login_cookies(response: Response, access: str, refresh: str, session_id: str):
    """
    Standard function to attach Authentication Cookies to any response.
    Delegates the complexity of flags and lifetimes here.
    """
    # 1. Access Token (Short Lived)
    response.set_cookie(
        key=CookieConfig.ACCESS_KEY,
        value=access,
        max_age=CookieConfig.ACCESS_LIFETIME,
        **CookieConfig.BASE_FLAGS
    )
    
    # 2. Refresh Token (Long Lived)
    response.set_cookie(
        key=CookieConfig.REFRESH_KEY,
        value=refresh,
        max_age=CookieConfig.REFRESH_LIFETIME,
        **CookieConfig.BASE_FLAGS
    )
    
    # 3. Session ID (Database Tracking)
    response.set_cookie(
        key=CookieConfig.SESSION_KEY,
        value=session_id,
        max_age=CookieConfig.REFRESH_LIFETIME,
        **CookieConfig.BASE_FLAGS
    )

def set_oauth_state_cookie(response: Response, state: str):
    """
    Sets the temporary state cookie for OAuth security flow.
    """
    response.set_cookie(
        key=CookieConfig.STATE_KEY,
        value=state,
        max_age=CookieConfig.STATE_LIFETIME,
        **CookieConfig.BASE_FLAGS
    )

def clear_auth_cookies(response: Response):
    """
    Standard Logout Mechanism.
    Browsers requires explicit instructions to delete cookies.
    """
    for key in [CookieConfig.ACCESS_KEY, CookieConfig.REFRESH_KEY, CookieConfig.SESSION_KEY]:
        response.delete_cookie(
            key=key,
            path=CookieConfig.BASE_FLAGS["path"],
            domain=CookieConfig.BASE_FLAGS.get("domain"),
            httponly=CookieConfig.BASE_FLAGS["httponly"],
            secure=CookieConfig.BASE_FLAGS["secure"],
            samesite=CookieConfig.BASE_FLAGS["samesite"]
        )

def clear_oauth_state(response: Response):
    """Cleans up the state cookie after callback verification"""
    response.delete_cookie(
        key=CookieConfig.STATE_KEY,
        path=CookieConfig.BASE_FLAGS["path"],
        httponly=CookieConfig.BASE_FLAGS["httponly"],
        secure=CookieConfig.BASE_FLAGS["secure"],
        samesite=CookieConfig.BASE_FLAGS["samesite"]
    )
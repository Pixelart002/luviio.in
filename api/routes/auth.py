import os
import secrets
import hashlib
import base64
import logging
from datetime import datetime, timedelta
from typing import Optional
from fastapi import APIRouter, Request, HTTPException, Query, Response
from fastapi.responses import RedirectResponse, JSONResponse
from api.utils.oauth_client import SupabaseAuthClient

# --- Enterprise Configuration ---
logger = logging.getLogger("AUTH-SYSTEM")
router = APIRouter()

# Environment Validation
SB_URL = os.environ.get("SB_URL")
SB_KEY = os.environ.get("SB_KEY")
BASE_URL = os.environ.get("BASE_URL", "https://luviio.in").rstrip('/')
REDIRECT_URI = f"{BASE_URL}/api/auth/callback"

if not all([SB_URL, SB_KEY]):
    logger.critical("❌ CRITICAL: Missing required Supabase environment variables.")

# Initialize Singleton Client
auth_engine = SupabaseAuthClient(SB_URL, SB_KEY)

# --- Cookie Security Policy ---
COOKIE_CONFIG = {
    "httponly": True,
    "secure": True,
    "samesite": "lax",
    "domain": None if "localhost" in BASE_URL else "luviio.in"
}

def set_auth_cookies(response: Response, tokens: dict):
    """Utility to set secure authentication cookies."""
    access_token = tokens.get("access_token")
    refresh_token = tokens.get("refresh_token")
    expires_in = tokens.get("expires_in", 3600)

    # Access Token (Short-lived)
    response.set_cookie(
        key="sb-access-token",
        value=access_token,
        max_age=expires_in,
        **COOKIE_CONFIG
    )
    # Refresh Token (Long-lived)
    response.set_cookie(
        key="sb-refresh-token",
        value=refresh_token,
        max_age=604800, # 7 Days
        **COOKIE_CONFIG
    )

# --- Routes ---

@router.get("/login")
async def initiate_oauth(request: Request, provider: str = "google"):
    """
    Enterprise OAuth Initiation.
    Generates PKCE cryptographically secure verifier and stores in encrypted session.
    """
    try:
        # 1. PKCE Generation
        verifier = secrets.token_urlsafe(64)
        challenge = base64.urlsafe_b64encode(
            hashlib.sha256(verifier.encode()).digest()
        ).decode().replace('=', '')

        # 2. State Management
        request.session["pkce_verifier"] = verifier
        request.session["auth_provider"] = provider
        
        # 3. Construct Secure Auth URL
        auth_url = (
            f"{SB_URL}/auth/v1/authorize?provider={provider}"
            f"&redirect_to={REDIRECT_URI}"
            f"&code_challenge={challenge}"
            f"&code_challenge_method=S256"
        )
        
        logger.info(f"🚀 Auth Initiation: {provider} flow started.")
        return RedirectResponse(url=auth_url)
    except Exception as e:
        logger.error(f"❌ Failed to initiate OAuth: {str(e)}")
        return RedirectResponse("/login?error=init_failed")

@router.get("/auth/callback")
async def oauth_callback(
    request: Request,
    code: str = Query(None),
    error: str = Query(None),
    error_description: str = Query(None)
):
    """
    Enterprise OAuth Callback Handler.
    Exchanges code for tokens, verifies integrity, and establishes secure session.
    """
    # 1. Check for provider-level errors
    if error:
        logger.error(f"❌ Provider Error: {error} - {error_description}")
        return RedirectResponse(f"/login?error={error}&msg={error_description}")

    if not code:
        return RedirectResponse("/login?error=missing_code")

    # 2. Retrieve & Validate PKCE Verifier
    verifier = request.session.pop("pkce_verifier", None)
    if not verifier:
        logger.warning("⚠️ Security Alert: PKCE verifier missing in session (Possible CSRF or Timeout).")
        return RedirectResponse("/login?error=session_expired")

    # 3. Token Exchange
    result = await auth_engine.exchange_code_for_token(code, verifier, REDIRECT_URI)
    
    if not result["success"]:
        logger.error(f"❌ Token Exchange Failed: {result.get('error')}")
        return RedirectResponse("/login?error=exchange_failed")

    # 4. Establish Session
    response = RedirectResponse(url="/dashboard")
    set_auth_cookies(response, result["tokens"])
    
    logger.info("✅ Session Established: User authenticated successfully.")
    return response

@router.get("/logout")
async def logout():
    """Securely terminates the user session by clearing all auth cookies."""
    response = RedirectResponse(url="/login")
    response.delete_cookie("sb-access-token", **COOKIE_CONFIG)
    response.delete_cookie("sb-refresh-token", **COOKIE_CONFIG)
    logger.info("🚪 Session Terminated.")
    return response

@router.get("/me")
async def get_current_user(request: Request):
    """
    Enterprise Identity Endpoint.
    Handles automatic token refresh if the access token is expired.
    """
    access_token = request.cookies.get("sb-access-token")
    refresh_token = request.cookies.get("sb-refresh-token")

    if not access_token:
        if not refresh_token:
            return JSONResponse(status_code=401, content={"authenticated": False})
        
        # Attempt Auto-Refresh
        refresh_result = await auth_engine.refresh_session(refresh_token)
        if not refresh_result["success"]:
            return JSONResponse(status_code=401, content={"authenticated": False})
        
        # New Tokens Obtained
        tokens = refresh_result["tokens"]
        access_token = tokens.get("access_token")
        
        # Prepare response with new cookies
        user_result = await auth_engine.get_user_profile(access_token)
        response = JSONResponse(content={"authenticated": True, "user": user_result.get("user")})
        set_auth_cookies(response, tokens)
        return response

    # Validate existing token
    user_result = await auth_engine.get_user_profile(access_token)
    if not user_result["success"]:
        # Token might be invalid/expired, try refresh
        if refresh_token:
            refresh_result = await auth_engine.refresh_session(refresh_token)
            if refresh_result["success"]:
                tokens = refresh_result["tokens"]
                user_result = await auth_engine.get_user_profile(tokens.get("access_token"))
                response = JSONResponse(content={"authenticated": True, "user": user_result.get("user")})
                set_auth_cookies(response, tokens)
                return response
        
        return JSONResponse(status_code=401, content={"authenticated": False})

    return {"authenticated": True, "user": user_result["user"]}

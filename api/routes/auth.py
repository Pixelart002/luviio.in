import os
import secrets
import hashlib
import base64
import logging
from fastapi import APIRouter, Request, HTTPException, Query
from fastapi.responses import RedirectResponse
from api.utils.oauth_client import SupabaseOAuthClient

# --- Setup ---
logger = logging.getLogger("AUTH-ROUTER")
router = APIRouter()

# Environment Variables
SB_URL = os.environ.get("SB_URL")
SB_KEY = os.environ.get("SB_KEY")
# Base URL for redirects - fallback to luviio.in if not set
BASE_URL = os.environ.get("BASE_URL", "https://luviio.in").rstrip('/')
REDIRECT_URI = f"{BASE_URL}/api/auth/callback"

# Initialize Client
oauth_client = SupabaseOAuthClient(SB_URL, SB_KEY) if SB_URL and SB_KEY else None

@router.get("/login")
async def login(request: Request, provider: str = "google"):
    """
    Step 1: Initiation - Generate PKCE and redirect to Supabase
    """
    if not oauth_client:
        raise HTTPException(status_code=500, detail="OAuth client not configured")

    # 1. Generate PKCE Verifier and Challenge
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()
    ).decode().replace('=', '')

    # 2. Store verifier in session for Step 2
    request.session["pkce_verifier"] = verifier
    
    # 3. Build Supabase Authorize URL
    auth_url = (
        f"{SB_URL}/auth/v1/authorize?provider={provider}"
        f"&redirect_to={REDIRECT_URI}"
        f"&code_challenge={challenge}"
        f"&code_challenge_method=S256"
    )
    
    logger.info(f"Initiating {provider} login. Redirecting to Supabase.")
    return RedirectResponse(url=auth_url)

@router.get("/auth/callback")
async def callback(
    request: Request, 
    code: str = Query(None), 
    error: str = Query(None), 
    error_description: str = Query(None)
):
    """
    Step 2: Callback - Exchange code for tokens
    """
    # 1. Handle errors from provider
    if error:
        logger.error(f"OAuth Error: {error} - {error_description}")
        return RedirectResponse(f"/login?error={error}")

    if not code:
        return RedirectResponse("/login?error=no_code")

    # 2. Retrieve PKCE verifier from session
    verifier = request.session.pop("pkce_verifier", None)
    if not verifier:
        logger.error("PKCE verifier missing in session")
        return RedirectResponse("/login?error=session_expired")

    # 3. Exchange code for tokens
    result = await oauth_client.exchange_code(code, verifier, REDIRECT_URI)
    
    if not result["success"]:
        return RedirectResponse(f"/login?error=token_exchange_failed")

    # 4. Success! Set tokens in cookies and redirect
    data = result["data"]
    access_token = data.get("access_token")
    refresh_token = data.get("refresh_token")

    response = RedirectResponse(url="/dashboard")
    
    # Set secure cookies
    cookie_params = {
        "httponly": True,
        "secure": True, # Always True for production
        "samesite": "lax",
        "max_age": 3600 * 24 * 7 # 7 days
    }
    
    response.set_cookie(key="sb-access-token", value=access_token, **cookie_params)
    response.set_cookie(key="sb-refresh-token", value=refresh_token, **cookie_params)
    
    logger.info("Login successful. Tokens set in cookies.")
    return response

@router.get("/logout")
async def logout():
    """
    Clear session and cookies
    """
    response = RedirectResponse(url="/login")
    response.delete_cookie("sb-access-token")
    response.delete_cookie("sb-refresh-token")
    return response

@router.get("/status")
async def status(request: Request):
    """
    Check if user is logged in
    """
    token = request.cookies.get("sb-access-token")
    if not token:
        return {"authenticated": False}
    
    user_result = await oauth_client.get_user(token)
    if not user_result["success"]:
        return {"authenticated": False}
        
    return {"authenticated": True, "user": user_result["data"]}

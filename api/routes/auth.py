import os
import secrets
import httpx
import logging
import time
from typing import Optional, Dict, Any
from fastapi import APIRouter, Response, HTTPException, Request, status, Depends
from fastapi.responses import RedirectResponse, JSONResponse
from jose import jwt, JWTError
from pydantic import BaseModel, EmailStr

# --- INTERNAL MODULES (Absolute Imports) ---
from api.utils.security import (
    hash_password, 
    verify_password, 
    get_auth_tokens, 
    SECRET_KEY, 
    ALGORITHM
)
from api.routes.database import (
    supabase_admin, 
    create_user_profile, 
    save_onboarding_data,
    log_audit_event
)
from api.utils.deps import get_current_user

# ==========================================
# 1. ADVANCED LOGGING & CONFIGURATION
# ==========================================

# Production-grade logging format with millisecond precision
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s.%(msecs)03d | %(name)s | %(levelname)s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("AUTH-ULTRABEAST")

router = APIRouter()

# Environment Checks
IS_PROD = os.environ.get("VERCEL_ENV") == "production"
REDIRECT_BASE = os.environ.get("REDIRECT_URI_BASE", "https://luviio.in/api/auth/callback")

# Route Constants
DASHBOARD_URL = "/dashboard"
ONBOARDING_URL = "/onboarding"
LOGIN_URL = "/login"

# OAuth Provider Configuration (The "Source of Truth")
PROVIDERS = {
    "google": {
        "auth_url": "https://accounts.google.com/o/oauth2/v2/auth",
        "token_url": "https://oauth2.googleapis.com/token",
        "user_info_url": "https://www.googleapis.com/oauth2/v3/userinfo",
        "scopes": "openid email profile"
    },
    "github": {
        "auth_url": "https://github.com/login/oauth/authorize",
        "token_url": "https://github.com/login/oauth/access_token",
        "user_info_url": "https://api.github.com/user",
        "scopes": "user:email"
    }
}

# Input Validation Models
class LoginSchema(BaseModel):
    email: EmailStr
    password: str

class RegisterSchema(BaseModel):
    email: EmailStr
    password: str

# ==========================================
# 2. CORE SECURITY HELPERS
# ==========================================

def set_auth_cookies(response: Response, access: str, refresh: str):
    """
    Sets HttpOnly cookies with 'Lax' SameSite policy.
    CRITICAL: Uses 'secure=IS_PROD' to ensure functionality on both Localhost and Vercel.
    """
    logger.info(f"🍪 [COOKIE-ENGINE] Setting secure session cookies. Secure Mode: {IS_PROD}")
    
    # 1. Access Token (Short Term - 1 Hour)
    response.set_cookie(
        key="access_token",
        value=access,
        httponly=True,
        secure=IS_PROD,
        samesite="lax",
        max_age=3600,
        path="/"
    )
    
    # 2. Refresh Token (Long Term - 30 Days)
    response.set_cookie(
        key="refresh_token",
        value=refresh,
        httponly=True,
        secure=IS_PROD,
        samesite="lax",
        max_age=2592000,
        path="/"
    )

def generate_csrf_state() -> str:
    """ Generates a cryptographically secure random string for OAuth state. """
    return secrets.token_urlsafe(32)

# ==========================================
# 3. SELF-HOSTED OAUTH FLOW (No Supabase Auth Wrapper)
# ==========================================

@router.get("/login/{provider}")
async def login_oauth(provider: str, request: Request):
    """
    Step 1: Initiates the OAuth handshake directly with the Provider (Google/GitHub).
    - Generates a random 'state' to prevent CSRF attacks.
    - Stores 'state' in a temporary cookie.
    - Redirects user to the Provider's Consent Screen.
    """
    start_time = time.time()
    
    # A. Validate Provider
    if provider not in PROVIDERS:
        logger.error(f"❌ [OAUTH-INIT] Blocked attempt for unknown provider: {provider}")
        raise HTTPException(status_code=400, detail="Provider not supported")
    
    # B. Configuration Load
    try:
        client_id = os.environ[f"{provider.upper()}_CLIENT_ID"]
    except KeyError:
        logger.critical(f"🔥 [CONFIG-FATAL] Missing Client ID for {provider}")
        raise HTTPException(status_code=500, detail="Server misconfiguration")

    # C. Generate CSRF State
    state = generate_csrf_state()
    redirect_uri = f"{REDIRECT_BASE}/{provider}"
    
    # D. Construct Auth URL
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": PROVIDERS[provider]["scopes"],
        "state": state,
        "access_type": "offline", # Crucial for Google Refresh Tokens
        "prompt": "consent"       # Forces consent screen to ensure refresh token is returned
    }
    
    # Manual query string construction to ensure encoding correctness
    query_string = "&".join([f"{k}={v}" for k, v in params.items()])
    auth_url = f"{PROVIDERS[provider]['auth_url']}?{query_string}"
    
    logger.info(f"🔗 [OAUTH-INIT] Redirecting to {provider} | State: {state[:6]}... | Time: {time.time() - start_time:.4f}s")
    
    # E. Redirect & Set State Cookie
    response = RedirectResponse(url=auth_url)
    response.set_cookie(
        key="oauth_state",
        value=state,
        httponly=True,
        secure=IS_PROD,
        samesite="lax",
        max_age=300 # 5 Minutes expiration for security
    )
    
    return response

@router.get("/callback/{provider}")
async def oauth_callback(request: Request, provider: str, code: str = None, state: str = None, error: str = None):
    """
    Step 2: Handles the Callback from the Provider.
    - Verifies 'state' against the cookie (Anti-CSRF).
    - Exchanges 'code' for 'access_token' via direct HTTP call.
    - Fetches User Profile.
    - Upserts User into Supabase DB (as a database only).
    - Issues Session Cookies.
    """
    logger.info(f"📥 [OAUTH-CALLBACK] Received callback for {provider}")

    # A. Error Handling from Provider
    if error:
        logger.warning(f"⚠️ [OAUTH-FAIL] Provider returned error: {error}")
        return RedirectResponse(f"{LOGIN_URL}?error=oauth_provider_error")

    if not code or not state:
        logger.error("❌ [OAUTH-FAIL] Missing code or state parameter")
        return RedirectResponse(f"{LOGIN_URL}?error=invalid_request")

    # B. Verify CSRF State
    cookie_state = request.cookies.get("oauth_state")
    if not cookie_state or cookie_state != state:
        logger.critical("🛡️ [SECURITY-ALERT] CSRF State Mismatch! Possible Attack.")
        return RedirectResponse(f"{LOGIN_URL}?error=csrf_mismatch")

    # C. Prepare for Token Exchange
    config = PROVIDERS[provider]
    client_id = os.environ.get(f"{provider.upper()}_CLIENT_ID")
    client_secret = os.environ.get(f"{provider.upper()}_CLIENT_SECRET")
    redirect_uri = f"{REDIRECT_BASE}/{provider}"

    user_email = None
    
    async with httpx.AsyncClient() as client:
        try:
            # D. Exchange Code for Token
            logger.info(f"🔄 [OAUTH-EXCHANGE] Swapping code for token with {provider}")
            token_res = await client.post(config["token_url"], data={
                "client_id": client_id,
                "client_secret": client_secret,
                "code": code,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code"
            }, headers={"Accept": "application/json"})
            
            token_data = token_res.json()
            
            if "error" in token_data:
                logger.error(f"❌ [OAUTH-EXCHANGE] Failed: {token_data}")
                return RedirectResponse(f"{LOGIN_URL}?error=token_exchange_failed")
            
            provider_token = token_data['access_token']

            # E. Fetch User Info
            logger.info(f"👤 [OAUTH-FETCH] Retrieving user profile")
            user_res = await client.get(config["user_info_url"], headers={"Authorization": f"Bearer {provider_token}"})
            user_info = user_res.json()
            
            user_email = user_info.get("email")

            # GitHub Fallback: Fetch private emails if main is hidden
            if not user_email and provider == "github":
                logger.info("🕵️ [GITHUB-FALLBACK] Fetching private emails")
                emails_res = await client.get("https://api.github.com/user/emails", headers={"Authorization": f"Bearer {provider_token}"})
                for e in emails_res.json():
                    if e["primary"] and e["verified"]:
                        user_email = e["email"]
                        break
            
        except httpx.RequestError as e:
            logger.error(f"❌ [NETWORK-FAIL] HTTP Error during OAuth: {str(e)}")
            return RedirectResponse(f"{LOGIN_URL}?error=connection_failed")

    if not user_email:
        logger.error("❌ [DATA-FAIL] Could not retrieve email from provider")
        return RedirectResponse(f"{LOGIN_URL}?error=no_email")

    # F. Database Synchronization (Self-Hosted Logic)
    # We use Supabase Service Role Key to bypass RLS and perform Admin actions
    logger.info(f"🗄️ [DB-SYNC] Ensuring user record for {user_email}")
    
    try:
        # Check existence
        existing_user = supabase_admin.table("users").select("*").eq("email", user_email).execute()
        
        if existing_user.data:
            user = existing_user.data[0]
            logger.info(f"✅ [DB-FOUND] Existing user {user['id']} found")
        else:
            # Create New User
            logger.info(f"🆕 [DB-CREATE] creating new user entry")
            user_data = {
                "email": user_email,
                "provider": provider,
                "onboarded": False,
                "created_at": "now()"
            }
            # Insert and return ID
            user = supabase_admin.table("users").insert(user_data).execute().data[0]
            
            # Create Skeleton Profile
            await create_user_profile(user_id=user["id"], email=user_email)
            logger.info(f"👤 [DB-PROFILE] Profile skeleton created")

    except Exception as e:
        logger.critical(f"💀 [DB-FATAL] Database Sync Failed: {str(e)}")
        return RedirectResponse(f"{LOGIN_URL}?error=server_error")

    # G. Finalize Session
    access, refresh = get_auth_tokens(user["id"])
    redirect_target = DASHBOARD_URL if user.get("onboarded") else ONBOARDING_URL
    
    response = RedirectResponse(url=redirect_target)
    set_auth_cookies(response, access, refresh)
    
    # Cleanup State Cookie
    response.delete_cookie("oauth_state")
    
    await log_audit_event(user_id=user["id"], action=f"login_{provider}", request=request)
    logger.info(f"🚀 [AUTH-SUCCESS] {user_email} authenticated. Redirecting to {redirect_target}")
    
    return response

# ==========================================
# 4. MANUAL AUTHENTICATION (Strict JSONResponse)
# ==========================================

@router.post("/register")
async def register(payload: RegisterSchema, request: Request):
    """
    Registers a new user with Email/Password.
    """
    email = payload.email.lower()
    logger.info(f"📝 [REGISTER] Attempt for {email}")
    
    # 1. Existence Check
    exists = supabase_admin.table("users").select("id").eq("email", email).execute()
    if exists.data:
        logger.warning(f"⚠️ [REGISTER] Conflict: {email} already exists")
        raise HTTPException(status_code=400, detail="User already registered")

    # 2. Hash & Store
    hashed = hash_password(payload.password)
    try:
        new_user = supabase_admin.table("users").insert({
            "email": email,
            "password": hashed,
            "onboarded": False,
            "provider": "email"
        }).execute()
        
        user_id = new_user.data[0]["id"]
        
        # 3. Profile & Logs
        await create_user_profile(user_id=user_id, email=email)
        await log_audit_event(user_id=user_id, action="signup_email", request=request)
        
        logger.info(f"✅ [REGISTER] Success for {user_id}")
        return {"msg": "Account created successfully"}
        
    except Exception as e:
        logger.error(f"❌ [REGISTER] DB Error: {str(e)}")
        raise HTTPException(status_code=500, detail="Registration failed")

@router.post("/login")
async def login(payload: LoginSchema, request: Request):
    """
    Logs in a user and returns a JSONResponse with Cookies.
    NOTE: We return 'JSONResponse' explicitly to ensure cookies are attached.
    """
    email = payload.email.lower()
    logger.info(f"🔑 [LOGIN] Attempt for {email}")
    
    # 1. Fetch User
    user_query = supabase_admin.table("users").select("*").eq("email", email).execute()
    
    # 2. Verify Credentials
    if not user_query.data:
        logger.warning(f"❌ [LOGIN] User not found: {email}")
        raise HTTPException(status_code=401, detail="Invalid credentials")
        
    user = user_query.data[0]
    
    if not verify_password(payload.password, user.get("password") or ""):
        logger.warning(f"❌ [LOGIN] Password mismatch for {email}")
        raise HTTPException(status_code=401, detail="Invalid credentials")

    # 3. Generate Session
    access, refresh = get_auth_tokens(user["id"])
    
    # 4. Create Response with Cookies
    content = {
        "status": "ok", 
        "user_id": user["id"], 
        "onboarded": user.get("onboarded", False)
    }
    response = JSONResponse(content=content)
    set_auth_cookies(response, access, refresh)
    
    await log_audit_event(user_id=user["id"], action="login_email", request=request)
    logger.info(f"✅ [LOGIN] Session created for {email}")
    
    return response

# ==========================================
# 5. ONBOARDING & SESSION MANAGEMENT
# ==========================================

@router.post("/complete-onboarding")
async def complete_onboarding(request: Request, payload: Dict[str, Any], user: dict = Depends(get_current_user)):
    """
    Finalizes user profile and optionally creates a store.
    """
    user_id = user["id"]
    logger.info(f"🚀 [ONBOARDING] Finalizing for {user['email']}")
    
    # Extract Data
    profile_updates = {
        "full_name": payload.get("fullName"),
        "role": payload.get("role")
    }
    
    store_data = None
    if payload.get("role") == "seller":
        store_data = {
            "name": payload.get("storeName"),
            "contact": payload.get("storeContact"),
            "category": payload.get("category")
        }
        
    # Atomic Save via Database Route
    try:
        res = await save_onboarding_data(user_id, profile_updates, store_data)
        
        if not res.get("success"):
            raise Exception("Database reported failure")
            
        await log_audit_event(user_id=user_id, action="onboarding_complete", request=request)
        logger.info(f"✅ [ONBOARDING] Success. Teleporting to Dashboard.")
        
        return {"status": "success", "redirect": DASHBOARD_URL}
        
    except Exception as e:
        logger.error(f"❌ [ONBOARDING] Save Failed: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to save data")

@router.post("/refresh")
async def refresh_session(request: Request):
    """
    Rotates access token using a valid refresh token.
    """
    rf_token = request.cookies.get("refresh_token")
    if not rf_token:
        logger.warning("⏳ [REFRESH] No token found")
        raise HTTPException(status_code=401, detail="Session expired")

    try:
        # Verify old refresh token
        payload = jwt.decode(rf_token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
        
        # Issue new pair
        new_access, new_refresh = get_auth_tokens(user_id)
        
        # Return new cookies
        response = JSONResponse(content={"status": "refreshed"})
        set_auth_cookies(response, new_access, new_refresh)
        
        logger.info(f"🔄 [REFRESH] Token rotated for {user_id}")
        return response
        
    except JWTError:
        logger.error("❌ [REFRESH] Invalid or Expired Refresh Token")
        raise HTTPException(status_code=401, detail="Invalid session")

@router.get("/logout")
async def logout():
    """
    Destroys session by clearing cookies and redirecting to login.
    """
    logger.info("🚪 [LOGOUT] Clearing session...")
    response = RedirectResponse(url=LOGIN_URL)
    response.delete_cookie("access_token")
    response.delete_cookie("refresh_token")
    return response
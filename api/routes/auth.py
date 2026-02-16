import os
import httpx
import logging
from fastapi import APIRouter, Response, HTTPException, Request, status, Depends
from fastapi.responses import RedirectResponse, JSONResponse
from jose import jwt, JWTError
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

# --- 🪵 PRODUCTION LOGGING SETUP ---
# Timestamps aur level-specific formatting taaki Vercel logs readable rahein
logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(name)s | %(levelname)s | %(message)s')
logger = logging.getLogger("AUTH-PRODUCTION")

router = APIRouter()

# --- ⚙️ GLOBAL CONFIGURATION ---
# Subdomains ko hata kar strictly relative paths use kar rahe hain
IS_PROD = os.environ.get("VERCEL_ENV") == "production"
DASHBOARD_URL = "/dashboard"
ONBOARDING_URL = "/onboarding"
LOGIN_URL = "/login"

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

# Redirect base must be the root domain for OAuth handshake
REDIRECT_BASE = os.environ.get("REDIRECT_URI_BASE", "https://luviio.in/api/auth/callback")

# --- 🛠️ HELPER: Secure Cookie Setter ---
def set_auth_cookies(response: Response, access: str, refresh: str):
    """
    Sets HttpOnly cookies strictly for the root domain.
    Logic: Secure=True only in production to allow localhost testing.
    """
    logger.info(f"🍪 [AUTH] Step: Attaching HttpOnly cookies (Secure={IS_PROD})")
    
    # Access Token: Short-lived session security
    response.set_cookie(
        key="access_token", value=access,
        httponly=True, 
        secure=IS_PROD, # False on localhost to prevent cookie blocking
        samesite="lax",
        max_age=3600
    )
    # Refresh Token: Long-lived persistence
    response.set_cookie(
        key="refresh_token", value=refresh,
        httponly=True, 
        secure=IS_PROD, 
        samesite="lax",
        max_age=2592000
    )

# ==========================================
# 1. MANUAL AUTH & ONBOARDING
# ==========================================

@router.post("/register")
async def register(request: Request, payload: dict):
    """ Handles new user creation and skeleton profile setup. """
    email = payload.get("email").lower()
    password = payload.get("password")
    
    logger.info(f"📨 [AUTH] Step: Processing registration for {email}")
    
    # Check if user already exists in Supabase
    exists = supabase_admin.table("users").select("id").eq("email", email).execute()
    if exists.data:
        logger.warning(f"⚠️ [AUTH] Conflict: Registration blocked for existing email {email}")
        raise HTTPException(status_code=400, detail="User already registered")

    # Hash password and insert into core users table
    hashed = hash_password(password)
    new_user_res = supabase_admin.table("users").insert({
        "email": email, "password": hashed, "onboarded": False, "provider": "email"
    }).execute()

    if not new_user_res.data:
        logger.error(f"❌ [AUTH] Fatal: Database failed to insert user {email}")
        raise HTTPException(status_code=500, detail="Registration failed")

    user_id = new_user_res.data[0]["id"]
    
    # 🔥 Atomic Setup: Ensure profile row exists before onboarding
    await create_user_profile(user_id=user_id, email=email)
    await log_audit_event(user_id=user_id, action="signup_email", request=request)

    logger.info(f"✅ [AUTH] Success: User {user_id} registered and profile skeleton created")
    return {"msg": "Account created successfully"}

@router.post("/login")
async def login(request: Request, payload: dict):
    """ 
    Manually authenticates user and issues HttpOnly cookies via JSONResponse.
    Note: Dictionary return is avoided to prevent cookie discarding.
    """
    email = payload.get("email").lower()
    password = payload.get("password")
    
    logger.info(f"📨 [AUTH] Step: Manual login attempt for {email}")

    # Fetch user from DB
    user_query = supabase_admin.table("users").select("*").eq("email", email).execute()
    if not user_query.data or not verify_password(password, user_query.data[0]["password"]):
        logger.warning(f"❌ [AUTH] Denied: Invalid credentials for {email}")
        raise HTTPException(status_code=401, detail="Invalid credentials")

    user = user_query.data[0]
    access, refresh = get_auth_tokens(user["id"])
    
    # 🔥 CORE FIX: Use JSONResponse to ensure cookies are actually sent
    content = {"status": "ok", "onboarded": user.get("onboarded")}
    response = JSONResponse(content=content)
    
    set_auth_cookies(response, access, refresh)
    await log_audit_event(user_id=user["id"], action="login_email", request=request)
    
    logger.info(f"✅ [AUTH] Success: Session started and cookies set for {email}")
    return response

@router.post("/complete-onboarding")
async def complete_onboarding(request: Request, payload: dict, user: dict = Depends(get_current_user)):
    """ Atomic profile and store finalization using UPSERT logic. """
    user_id = user["id"]
    logger.info(f"🚀 [AUTH] Step: Processing onboarding data for {user['email']}")

    profile_updates = {"full_name": payload.get("fullName"), "role": payload.get("role")}
    store_data = None
    if payload.get("role") == "seller":
        store_data = {
            "name": payload.get("storeName"),
            "contact": payload.get("storeContact"),
            "category": payload.get("category")
        }

    # Atomic DB call to update profile, create store, and mark 'onboarded' = true
    db_result = await save_onboarding_data(user_id, profile_updates, store_data)
    
    if not db_result.get("success"):
        logger.error(f"❌ [AUTH] Fatal: Onboarding DB save failed for {user_id}")
        raise HTTPException(status_code=500, detail="Failed to save data")
    
    await log_audit_event(user_id=user_id, action="onboarding_complete", request=request)
    
    logger.info(f"✅ [AUTH] Success: User {user['email']} fully onboarded. Redirecting...")
    return {"status": "success", "redirect": DASHBOARD_URL}

# ==========================================
# 2. THIRD-PARTY OAUTH
# ==========================================

@router.get("/login/{provider}")
async def login_oauth(provider: str):
    """ Triggers OAuth flow for Google or GitHub. """
    if provider not in PROVIDERS:
        logger.error(f"❌ [AUTH] Blocked: Attempted unsupported provider '{provider}'")
        raise HTTPException(status_code=400, detail="Provider not supported")
    
    client_id = os.environ.get(f"{provider.upper()}_CLIENT_ID")
    redirect_uri = f"{REDIRECT_BASE}/{provider}"
    
    url = f"{PROVIDERS[provider]['auth_url']}?client_id={client_id}&redirect_uri={redirect_uri}&response_type=code&scope={PROVIDERS[provider]['scopes']}"
    logger.info(f"🔗 [AUTH] Generating OAuth redirect for {provider}")
    return RedirectResponse(url=url)

@router.get("/callback/{provider}")
async def oauth_callback(request: Request, provider: str, code: str):
    """ Handles OAuth token exchange and user synchronization. """
    logger.info(f"📥 [AUTH] Step: Handling {provider} OAuth callback")
    config = PROVIDERS[provider]
    
    async with httpx.AsyncClient() as client:
        # A. Exchange authorization code for tokens
        token_res = await client.post(config["token_url"], data={
            "client_id": os.environ.get(f"{provider.upper()}_CLIENT_ID"),
            "client_secret": os.environ.get(f"{provider.upper()}_CLIENT_SECRET"),
            "code": code, "redirect_uri": f"{REDIRECT_BASE}/{provider}",
            "grant_type": "authorization_code"
        }, headers={"Accept": "application/json"})
        
        token_data = token_res.json()
        if "error" in token_data:
            logger.error(f"❌ [AUTH] OAuth Error during token exchange: {token_data}")
            return RedirectResponse(f"{LOGIN_URL}?error=oauth_failed")

        # B. Fetch User details from provider API
        user_res = await client.get(config["user_info_url"], headers={"Authorization": f"Bearer {token_data['access_token']}"})
        user_info = user_res.json()
        email = user_info.get("email")
        
        # GitHub email fallback for private profiles
        if not email and provider == "github":
            email_res = await client.get("https://api.github.com/user/emails", headers={"Authorization": f"Bearer {token_data['access_token']}"})
            email = next(e["email"] for e in email_res.json() if e["primary"])

    # C. Database Synchronization (Create or Fetch)
    user_res = supabase_admin.table("users").select("*").eq("email", email).execute()
    
    if not user_res.data:
        logger.info(f"🆕 [AUTH] OAuth: Creating new user account for {email}")
        user = supabase_admin.table("users").insert({"email": email, "provider": provider, "onboarded": False}).execute().data[0]
        await create_user_profile(user_id=user["id"], email=email)
    else:
        user = user_res.data[0]

    await log_audit_event(user_id=user["id"], action=f"login_{provider}", request=request)

    # D. Issue Cookies and Redirect (Relative Paths)
    access, refresh = get_auth_tokens(user["id"])
    redirect_target = DASHBOARD_URL if user.get("onboarded") else ONBOARDING_URL
    
    logger.info(f"🚀 [AUTH] Success: OAuth authenticated. Redirecting to {redirect_target}")
    response = RedirectResponse(url=redirect_target)
    set_auth_cookies(response, access, refresh)
    return response

# ==========================================
# 3. SESSION ROTATION & LOGOUT
# ==========================================

@router.post("/refresh")
async def refresh_session(request: Request):
    """ Rotates Access and Refresh tokens to maintain session persistence. """
    rf_token = request.cookies.get("refresh_token")
    if not rf_token:
        logger.warning("⏳ [AUTH] Session Refresh Blocked: No refresh token found")
        raise HTTPException(status_code=401, detail="Session expired")

    try:
        payload = jwt.decode(rf_token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
        
        new_access, new_refresh = get_auth_tokens(user_id)
        
        response = JSONResponse(content={"status": "refreshed"})
        set_auth_cookies(response, new_access, new_refresh)
        
        logger.info(f"🔄 [AUTH] Success: Token rotation completed for {user_id}")
        return response
    except JWTError:
        logger.error("❌ [AUTH] Token rotation failed: Invalid refresh token signature")
        raise HTTPException(status_code=401, detail="Invalid session")

@router.get("/logout")
async def logout():
    """ 
    Clears global session cookies.
    Redirects back to login page on the root domain.
    """
    logger.info("🚪 [AUTH] Step: Global Logout triggered. Clearing cookies.")
    response = RedirectResponse(url=LOGIN_URL)
    response.delete_cookie("access_token")
    response.delete_cookie("refresh_token")
    return response
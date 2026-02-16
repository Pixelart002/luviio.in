import os
import secrets
import httpx
import logging
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any

from fastapi import APIRouter, Response, HTTPException, Request, status, Depends, BackgroundTasks
from fastapi.responses import RedirectResponse, JSONResponse
from jose import jwt, JWTError, ExpiredSignatureError
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

# ==========================================
# 1. ADVANCED LOGGING & CONFIGURATION
# ==========================================

logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s.%(msecs)03d | %(name)s | %(levelname)s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("AUTH-ULTRABEAST")
auth_guard_logger = logging.getLogger("AUTH-GUARD")

router = APIRouter()

IS_PROD = os.environ.get("VERCEL_ENV") == "production"
REDIRECT_BASE = os.environ.get("REDIRECT_URI_BASE", "https://luviio.in/api/auth/callback")

DASHBOARD_URL = "/dashboard"
ONBOARDING_URL = "/onboarding"
LOGIN_URL = "/login"
COOKIE_DOMAIN = ".luviio.in" if IS_PROD else None

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

class LoginSchema(BaseModel):
    email: EmailStr
    password: str

class RegisterSchema(BaseModel):
    email: EmailStr
    password: str

# ==========================================
# 2. AUTH & SESSION DEPENDENCIES (The Guard)
# ==========================================

async def get_current_user(request: Request):
    """
    ULTRA-BEAST VERIFICATION:
    1. JWT Signature Check
    2. Session Table Persistence Check (Revocation check)
    3. User Integrity Check
    """
    access_token = request.cookies.get("access_token")
    session_id = request.cookies.get("session_id")
    
    if not access_token:
        auth_guard_logger.warning("🚫 [AUTH] Access token missing. Redirecting to login.")
        raise HTTPException(status_code=401, detail="Authentication required")

    try:
        # 🟢 STEP 1: JWT Signature Verification
        payload = jwt.decode(access_token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")
        
        if not user_id:
            raise JWTError("Missing subject")
            
    except ExpiredSignatureError:
        auth_guard_logger.info(f"⏳ [AUTH] Access token expired for user. Hinting refresh.")
        raise HTTPException(status_code=401, detail="token_expired")
    except JWTError:
        auth_guard_logger.error("❌ [AUTH] Malformed JWT detected.")
        raise HTTPException(status_code=401, detail="Invalid session")

    # 🟢 STEP 2: Database Persistence & Revocation Check
    if session_id:
        auth_guard_logger.info(f"🔍 [AUTH] Verifying Session ID: {session_id[:8]} in DB")
        sess_check = supabase_admin.table("sessions").select("is_revoked").eq("id", session_id).single().execute()
        
        if not sess_check.data or sess_check.data.get("is_revoked"):
            auth_guard_logger.warning(f"🛡️ [SECURITY-ALERT] Revoked or Zombie session attempt: {session_id}")
            raise HTTPException(status_code=401, detail="Session revoked")

    # 🟢 STEP 3: User Retrieval
    user_res = supabase_admin.table("users").select("*").eq("id", user_id).execute()

    if not user_res.data:
        auth_guard_logger.error(f"❌ [AUTH] User {user_id} not found in DB.")
        raise HTTPException(status_code=401, detail="User not found")

    user = user_res.data[0]
    auth_guard_logger.info(f"✅ [AUTH] User {user['email']} verified.")
    return user

async def require_onboarded(user: dict = Depends(get_current_user)):
    """
    Ensures user has completed onboarding before accessing protected routes.
    """
    if not user.get("onboarded"):
        auth_guard_logger.warning(f"⚠️ [AUTH] Onboarding pending for {user['email']}. Redirecting.")
        raise HTTPException(
            status_code=status.HTTP_307_TEMPORARY_REDIRECT, 
            detail="onboarding_required"
        )
    return user

# ==========================================
# 3. CORE SECURITY HELPERS
# ==========================================

async def create_server_session(user_id: str, request: Request, refresh_token: str) -> str:
    session_id = str(uuid.uuid4())
    user_agent = request.headers.get("user-agent", "Unknown")
    ip_address = request.client.host
    expires_at = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()

    try:
        supabase_admin.table("sessions").insert({
            "id": session_id,
            "user_id": user_id,
            "refresh_token": refresh_token,
            "is_revoked": False,
            "expires_at": expires_at,
            "user_agent": user_agent,
            "ip_address": ip_address
        }).execute()
        
        logger.info(f"💾 [SESSION-DB] Persistent session created: {session_id} for User: {user_id}")
        return session_id
    except Exception as e:
        logger.critical(f"🔥 [DB-FATAL] Session creation failed: {str(e)}")
        return session_id

def set_auth_cookies(response: Response, access: str, refresh: str, session_id: str):
    logger.info(f"🍪 [COOKIE-ENGINE] Setting secure session cookies. Secure Mode: {IS_PROD}")
    cookie_params = {
        "httponly": True,
        "secure": IS_PROD,
        "samesite": "lax",
        "path": "/"
    }
    response.set_cookie(key="access_token", value=access, max_age=3600, **cookie_params)
    response.set_cookie(key="refresh_token", value=refresh, max_age=2592000, **cookie_params)
    response.set_cookie(key="session_id", value=session_id, max_age=2592000, **cookie_params)

def generate_csrf_state() -> str:
    return secrets.token_urlsafe(32)

# ==========================================
# 4. OAUTH FLOW
# ==========================================

@router.get("/login/{provider}")
async def login_oauth(provider: str, request: Request):
    if provider not in PROVIDERS:
        raise HTTPException(status_code=400, detail="Provider not supported")
    
    try:
        client_id = os.environ[f"{provider.upper()}_CLIENT_ID"]
    except KeyError:
        logger.critical(f"🔥 [CONFIG-FATAL] Missing Client ID for {provider}")
        raise HTTPException(status_code=500, detail="Server misconfiguration")

    state = generate_csrf_state()
    redirect_uri = f"{REDIRECT_BASE}/{provider}"
    
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": PROVIDERS[provider]["scopes"],
        "state": state,
        "access_type": "offline",
        "prompt": "consent"
    }
    
    query_string = "&".join([f"{k}={v}" for k, v in params.items()])
    auth_url = f"{PROVIDERS[provider]['auth_url']}?{query_string}"
    
    response = RedirectResponse(url=auth_url)
    response.set_cookie(
        key="oauth_state",
        value=state,
        httponly=True,
        secure=IS_PROD,
        samesite="lax",
        max_age=300
    )
    return response

@router.get("/callback/{provider}")
async def oauth_callback(
    request: Request, 
    provider: str, 
    background_tasks: BackgroundTasks,
    code: str = None, 
    state: str = None, 
    error: str = None
):
    if error: return RedirectResponse(f"{LOGIN_URL}?error=oauth_provider_error")
    if not code or not state: return RedirectResponse(f"{LOGIN_URL}?error=invalid_request")

    cookie_state = request.cookies.get("oauth_state")
    if not cookie_state or cookie_state != state:
        logger.critical("🛡️ [SECURITY-ALERT] CSRF State Mismatch!")
        return RedirectResponse(f"{LOGIN_URL}?error=csrf_mismatch")

    config = PROVIDERS[provider]
    client_id = os.environ.get(f"{provider.upper()}_CLIENT_ID")
    client_secret = os.environ.get(f"{provider.upper()}_CLIENT_SECRET")
    redirect_uri = f"{REDIRECT_BASE}/{provider}"

    user_email = None
    
    async with httpx.AsyncClient() as client:
        try:
            token_res = await client.post(config["token_url"], data={
                "client_id": client_id, "client_secret": client_secret,
                "code": code, "redirect_uri": redirect_uri, "grant_type": "authorization_code"
            }, headers={"Accept": "application/json"})
            
            token_data = token_res.json()
            if "error" in token_data:
                return RedirectResponse(f"{LOGIN_URL}?error=token_exchange_failed")
            
            provider_token = token_data['access_token']
            user_res = await client.get(config["user_info_url"], headers={"Authorization": f"Bearer {provider_token}"})
            user_info = user_res.json()
            user_email = user_info.get("email")

            if not user_email and provider == "github":
                emails_res = await client.get("https://api.github.com/user/emails", headers={"Authorization": f"Bearer {provider_token}"})
                for e in emails_res.json():
                    if e["primary"] and e["verified"]:
                        user_email = e["email"]; break
            
        except httpx.RequestError:
            return RedirectResponse(f"{LOGIN_URL}?error=connection_failed")

    if not user_email: return RedirectResponse(f"{LOGIN_URL}?error=no_email")

    try:
        existing_user = supabase_admin.table("users").select("*").eq("email", user_email).execute()
        if existing_user.data:
            user = existing_user.data[0]
        else:
            user_data = {"email": user_email, "provider": provider, "onboarded": False}
            user = supabase_admin.table("users").insert(user_data).execute().data[0]
            await create_user_profile(user_id=user["id"], email=user_email)
    except Exception as e:
        logger.critical(f"💀 [DB-FATAL] Database Sync Failed: {str(e)}")
        return RedirectResponse(f"{LOGIN_URL}?error=server_error")

    access, refresh = get_auth_tokens(user["id"])
    session_id = await create_server_session(user["id"], request, refresh)

    redirect_target = DASHBOARD_URL if user.get("onboarded") else ONBOARDING_URL
    response = RedirectResponse(url=redirect_target, status_code=303)
    set_auth_cookies(response, access, refresh, session_id)
    response.delete_cookie("oauth_state"
        path="/",
        domain=COOKIE_DOMAIN
        ),
        
    
    background_tasks.add_task(log_audit_event, user_id=user["id"], action=f"login_{provider}", request=request)
    return response

# ==========================================
# 5. MANUAL AUTHENTICATION
# ==========================================

@router.post("/register")
async def register(payload: RegisterSchema, request: Request, background_tasks: BackgroundTasks):
    email = payload.email.lower()
    exists = supabase_admin.table("users").select("id").eq("email", email).execute()
    if exists.data:
        raise HTTPException(status_code=400, detail="User already registered")

    hashed = hash_password(payload.password)
    try:
        new_user = supabase_admin.table("users").insert({
            "email": email, "password": hashed, "onboarded": False, "provider": "email"
        }).execute()
        
        user_id = new_user.data[0]["id"]
        await create_user_profile(user_id=user_id, email=email)
        background_tasks.add_task(log_audit_event, user_id=user_id, action="signup_email", request=request)
        return {"msg": "Account created successfully"}
    except Exception as e:
        logger.error(f"❌ [REGISTER] DB Error: {str(e)}")
        raise HTTPException(status_code=500, detail="Registration failed")

@router.post("/login")
async def login(payload: LoginSchema, request: Request, background_tasks: BackgroundTasks):
    email = payload.email.lower()
    user_query = supabase_admin.table("users").select("*").eq("email", email).execute()
    if not user_query.data:
        raise HTTPException(status_code=401, detail="Invalid credentials")
        
    user = user_query.data[0]
    if not verify_password(payload.password, user.get("password") or ""):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    access, refresh = get_auth_tokens(user["id"])
    session_id = await create_server_session(user["id"], request, refresh)
    
    response = JSONResponse(content={"status": "ok", "user_id": user["id"], "onboarded": user.get("onboarded", False)})
    set_auth_cookies(response, access, refresh, session_id)
    background_tasks.add_task(log_audit_event, user_id=user["id"], action="login_email", request=request)
    return response

# ==========================================
# 6. ONBOARDING & SESSION MANAGEMENT
# ==========================================

@router.post("/complete-onboarding")
async def complete_onboarding(
    request: Request, 
    payload: Dict[str, Any], 
    background_tasks: BackgroundTasks,
    user: dict = Depends(get_current_user)
):
    user_id = user["id"]
    profile_updates = {"full_name": payload.get("fullName"), "role": payload.get("role")}
    store_data = None
    if payload.get("role") == "seller":
        store_data = {
            "name": payload.get("storeName"),
            "contact": payload.get("storeContact"),
            "category": payload.get("category")
        }
        
    try:
        res = await save_onboarding_data(user_id, profile_updates, store_data)
        if not res.get("success"): raise Exception("DB Failure")
        supabase_admin.table("users").update({"onboarded": True}).eq("id", user_id).execute()
        background_tasks.add_task(log_audit_event, user_id=user_id, action="onboarding_complete", request=request)
        return {"status": "success", "redirect": DASHBOARD_URL}
    except Exception as e:
        logger.error(f"❌ [ONBOARDING] Save Failed: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to save data")

@router.post("/refresh")
async def refresh_session(request: Request):
    rf_token = request.cookies.get("refresh_token")
    old_sid = request.cookies.get("session_id")

    if not rf_token or not old_sid:
        raise HTTPException(status_code=401, detail="Session expired")

    try:
        res = supabase_admin.table("sessions").select("*").eq("id", old_sid).eq("is_revoked", False).execute()
        if not res.data:
            raise HTTPException(status_code=401, detail="Invalid session")

        payload = jwt.decode(rf_token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
        
        supabase_admin.table("sessions").update({"is_revoked": True}).eq("id", old_sid).execute()
        
        new_access, new_refresh = get_auth_tokens(user_id)
        new_sid = await create_server_session(user_id, request, new_refresh)
        
        response = JSONResponse(content={"status": "refreshed"})
        set_auth_cookies(response, new_access, new_refresh, new_sid)
        return response
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

@router.get("/logout")
async def logout(request: Request):
    sid = request.cookies.get("session_id")
    if sid:
        supabase_admin.table("sessions").update({"is_revoked": True}).eq("id", sid).execute()

    response = RedirectResponse(url=LOGIN_URL, status_code=303)
    response.delete_cookie("access_token")
    response.delete_cookie("refresh_token")
    response.delete_cookie("session_id")
    return response
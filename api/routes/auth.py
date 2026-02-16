import os
import secrets
import httpx
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any

from fastapi import APIRouter, Response, HTTPException, Request, status, Depends, BackgroundTasks
from fastapi.responses import RedirectResponse, JSONResponse
from jose import jwt, JWTError, ExpiredSignatureError
from pydantic import BaseModel, EmailStr

# --- INTERNAL MODULES ---
from api.utils.security import (
    hash_password, verify_password, get_auth_tokens, SECRET_KEY, ALGORITHM
)
from api.routes.database import (
    supabase_admin, create_user_profile, save_onboarding_data, log_audit_event
)

# ==========================================
# 1. ELITE LOGGING CONFIG
# ==========================================
logger = logging.getLogger("AUTH-SYSTEM")
router = APIRouter()

IS_PROD = os.environ.get("VERCEL_ENV") == "production"
REDIRECT_BASE = os.environ.get("REDIRECT_URI_BASE", "https://luviio.in/api/auth/callback")

DASHBOARD_URL = "/dashboard"
ONBOARDING_URL = "/onboarding"
LOGIN_URL = "/login"

class LoginSchema(BaseModel):
    email: EmailStr
    password: str

class RegisterSchema(BaseModel):
    email: EmailStr
    password: str

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

# ==========================================
# 2. ROBUST HELPERS
# ==========================================

async def create_server_session(user_id: str, request: Request, refresh_token: str) -> str:
    session_id = str(uuid.uuid4())
    expires_at = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
    try:
        supabase_admin.table("sessions").insert({
            "id": session_id, "user_id": user_id, "refresh_token": refresh_token,
            "is_revoked": False, "expires_at": expires_at,
            "user_agent": request.headers.get("user-agent", "Unknown"),
            "ip_address": request.client.host
        }).execute()
        return session_id
    except Exception as e:
        logger.error(f"❌ [SessionError] Type: {type(e).__name__} | Details: {e}")
        return session_id

def set_auth_cookies(response: Response, access: str, refresh: str, session_id: str):
    # Strictly path="/" for unified domain tree
    params = {"httponly": True, "secure": IS_PROD, "samesite": "lax", "path": "/"}
    response.set_cookie(key="access_token", value=access, max_age=3600, **params)
    response.set_cookie(key="refresh_token", value=refresh, max_age=2592000, **params)
    response.set_cookie(key="session_id", value=session_id, max_age=2592000, **params)

# ==========================================
# 3. OAUTH FLOW (CSRF JAD SE KHATAM)
# ==========================================

@router.get("/login/{provider}")
async def login_oauth(provider: str):
    if provider not in PROVIDERS:
        raise HTTPException(status_code=400, detail=f"Provider {provider} not supported")
    
    state = secrets.token_urlsafe(32)
    query_params = {
        "client_id": os.environ.get(f"{provider.upper()}_CLIENT_ID"),
        "redirect_uri": f"{REDIRECT_BASE}/{provider}",
        "response_type": "code",
        "scope": PROVIDERS[provider]["scopes"],
        "state": state,
        "access_type": "offline", "prompt": "consent"
    }
    
    auth_url = f"{PROVIDERS[provider]['auth_url']}?{'&'.join([f'{k}={v}' for k, v in query_params.items()])}"
    response = RedirectResponse(url=auth_url)
    
    # 🔥 CSRF FIX: Strictly using path="/"
    response.set_cookie(
        key="oauth_state", value=state,
        httponly=True, secure=IS_PROD, samesite="lax",
        max_age=600, path="/"
    )
    return response

@router.get("/callback/{provider}")
async def oauth_callback(
    request: Request, provider: str, background_tasks: BackgroundTasks,
    code: str = None, state: str = None, error: str = None
):
    # 1. Capture Provider Errors
    if error:
        logger.error(f"❌ [OAuthProviderError] {provider} returned: {error}")
        return RedirectResponse(f"{LOGIN_URL}?error={error}")

    if not code or not state:
        return RedirectResponse(f"{LOGIN_URL}?error=invalid_request")

    # 2. Strictly Verify CSRF State
    cookie_state = request.cookies.get("oauth_state")
    if not cookie_state or cookie_state != state:
        logger.critical(f"🛡️ [CSRF_MISMATCH] Expected: {cookie_state} | Received: {state}")
        return RedirectResponse(f"{LOGIN_URL}?error=csrf_mismatch")

    async with httpx.AsyncClient() as client:
        try:
            config = PROVIDERS[provider]
            # Exchange Token
            token_res = await client.post(config["token_url"], data={
                "client_id": os.environ.get(f"{provider.upper()}_CLIENT_ID"),
                "client_secret": os.environ.get(f"{provider.upper()}_CLIENT_SECRET"),
                "code": code, "redirect_uri": f"{REDIRECT_BASE}/{provider}",
                "grant_type": "authorization_code"
            }, headers={"Accept": "application/json"})
            token_res.raise_for_status()
            
            # Fetch User Profile
            user_res = await client.get(
                config["user_info_url"], 
                headers={"Authorization": f"Bearer {token_res.json()['access_token']}"}
            )
            user_res.raise_for_status()
            user_email = user_res.json().get("email")
            
        except httpx.HTTPStatusError as e:
            logger.error(f"❌ [HTTPError] Type: {type(e).__name__} | Status: {e.response.status_code}")
            return RedirectResponse(f"{LOGIN_URL}?error=token_exchange_failed")
        except Exception as e:
            logger.error(f"❌ [CallbackFatal] Type: {type(e).__name__} | Details: {e}")
            return RedirectResponse(f"{LOGIN_URL}?error=server_error")

    # 3. Database Sync
    try:
        user_db = supabase_admin.table("users").select("*").eq("email", user_email).execute()
        if user_db.data:
            user = user_db.data[0]
        else:
            user = supabase_admin.table("users").insert({"email": user_email, "provider": provider, "onboarded": False}).execute().data[0]
            await create_user_profile(user_id=user["id"], email=user_email)
            
        access, refresh = get_auth_tokens(user["id"])
        session_id = await create_server_session(user["id"], request, refresh)

        response = RedirectResponse(url=DASHBOARD_URL if user.get("onboarded") else ONBOARDING_URL, status_code=303)
        set_auth_cookies(response, access, refresh, session_id)
        response.delete_cookie("oauth_state", path="/")
        return response
        
    except Exception as e:
        logger.error(f"❌ [DBSyncError] Type: {type(e).__name__} | Details: {e}")
        return RedirectResponse(f"{LOGIN_URL}?error=db_sync_error")

# ==========================================
# 4. MANUAL AUTH (JSON ERRORS)
# ==========================================

@router.post("/register")
async def register(payload: RegisterSchema):
    try:
        email = payload.email.lower()
        exists = supabase_admin.table("users").select("id").eq("email", email).execute()
        if exists.data:
            return JSONResponse(status_code=400, content={"error": "Email already registered", "type": "DuplicateUser"})

        supabase_admin.table("users").insert({
            "email": email, "password": hash_password(payload.password), "onboarded": False, "provider": "email"
        }).execute()
        return {"status": "success"}
    except Exception as e:
        logger.error(f"❌ [RegisterError] Type: {type(e).__name__}")
        return JSONResponse(status_code=500, content={"error": "Database error during registration", "type": type(e).__name__})

@router.post("/login")
async def login(payload: LoginSchema, request: Request):
    try:
        user_query = supabase_admin.table("users").select("*").eq("email", payload.email.lower()).execute()
        if not user_query.data or not verify_password(payload.password, user_query.data[0].get("password") or ""):
            return JSONResponse(status_code=401, content={"error": "Invalid credentials", "type": "AuthFailed"})
            
        user = user_query.data[0]
        access, refresh = get_auth_tokens(user["id"])
        session_id = await create_server_session(user["id"], request, refresh)
        
        response = JSONResponse(content={"status": "ok", "onboarded": user.get("onboarded", False)})
        set_auth_cookies(response, access, refresh, session_id)
        return response
    except Exception as e:
        logger.error(f"❌ [LoginFatal] Type: {type(e).__name__}")
        return JSONResponse(status_code=500, content={"error": "Internal login error", "type": type(e).__name__})

# ==========================================
# 5. REFRESH & LOGOUT
# ==========================================

@router.post("/refresh")
async def refresh_session(request: Request):
    try:
        rf_token = request.cookies.get("refresh_token")
        old_sid = request.cookies.get("session_id")
        
        if not rf_token or not old_sid:
            return JSONResponse(status_code=401, content={"error": "Missing session tokens"})

        # Verify DB Session
        sess = supabase_admin.table("sessions").select("*").eq("id", old_sid).eq("is_revoked", False).execute()
        if not sess.data:
            return JSONResponse(status_code=401, content={"error": "Session revoked"})

        # Token Rotation
        payload = jwt.decode(rf_token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
        
        supabase_admin.table("sessions").update({"is_revoked": True}).eq("id", old_sid).execute()
        new_access, new_refresh = get_auth_tokens(user_id)
        new_sid = await create_server_session(user_id, request, new_refresh)
        
        response = JSONResponse(content={"status": "refreshed"})
        set_auth_cookies(response, new_access, new_refresh, new_sid)
        return response
        
    except ExpiredSignatureError:
        return JSONResponse(status_code=401, content={"error": "Refresh token expired", "type": "ExpiredSignatureError"})
    except JWTError:
        return JSONResponse(status_code=401, content={"error": "Invalid refresh token", "type": "JWTError"})
    except Exception as e:
        logger.error(f"❌ [RefreshError] Type: {type(e).__name__}")
        return JSONResponse(status_code=500, content={"error": "Refresh process failed"})

@router.get("/logout")
async def logout(request: Request):
    sid = request.cookies.get("session_id")
    if sid:
        supabase_admin.table("sessions").update({"is_revoked": True}).eq("id", sid).execute()
    
    response = RedirectResponse(url=LOGIN_URL, status_code=303)
    for c in ["access_token", "refresh_token", "session_id"]:
        response.delete_cookie(c, path="/")
    return response
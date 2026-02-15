import os
import httpx
import logging
import json
import asyncio
import secrets
import base64
import hashlib
from fastapi import APIRouter, Request, Response, HTTPException
from fastapi.responses import RedirectResponse, JSONResponse
from supabase import create_client, Client
from datetime import datetime
from api.utils.oauth_client import SupabaseOAuthClient

# --- LOGGER SETUP ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("AUTH-ENGINE")

router = APIRouter()

# --- CONFIGURATION VALIDATION ---
SB_URL = os.environ.get("SB_URL")
SB_KEY = os.environ.get("SB_KEY")
SB_SERVICE_KEY = os.environ.get("SB_SERVICE_ROLE_KEY")

if not SB_URL or not SB_KEY or not SB_SERVICE_KEY:
    logger.critical("❌ Missing Supabase environment variables")

try:
    supabase_admin: Client = create_client(SB_URL, SB_SERVICE_KEY) if SB_URL and SB_SERVICE_KEY else None
except Exception as e:
    logger.error(f"⚠️ Supabase initialization error: {e}")
    supabase_admin = None

try:
    oauth_client = SupabaseOAuthClient(SB_URL, SB_KEY, SB_SERVICE_KEY) if SB_URL and SB_KEY and SB_SERVICE_KEY else None
except Exception as e:
    logger.error(f"⚠️ OAuth Client initialization error: {e}")
    oauth_client = None


# ==========================================
# HELPER: CHECK/CREATE PROFILE & DECIDE ROUTE
# ==========================================
async def get_next_path(user_id: str, email: str) -> str:
    if not supabase_admin:
        return "/dashboard"

    try:
        res = supabase_admin.table("profiles").select("onboarded").eq("id", user_id).execute()

        if not res.data:
            logger.info(f"✓ Creating new profile for {email}")
            supabase_admin.table("profiles").insert({
                "id": user_id,
                "email": email,
                "onboarded": False,
                "created_at": datetime.utcnow().isoformat()
            }).execute()
            return "/onboarding"

        is_onboarded = res.data[0].get("onboarded", False)
        return "/dashboard" if is_onboarded else "/onboarding"

    except Exception as e:
        logger.error(f"❌ Profile Check Failed: {str(e)}")
        return "/onboarding"


# ==========================================
# NEW: OAUTH INITIATION (PKCE Support)
# ==========================================
@router.get("/login")
async def login_init(request: Request, provider: str = "google"):
    """
    Initiates the OAuth flow by generating a PKCE code_verifier and challenge.
    """
    # 1. Generate PKCE Verifier and Challenge
    code_verifier = secrets.token_urlsafe(64)
    code_challenge = base64.urlsafe_b64encode(
        hashlib.sha256(code_verifier.encode()).digest()
    ).decode().replace('=', '')
    
    # 2. Store verifier in session
    request.session["code_verifier"] = code_verifier
    logger.info(f"🔑 Session Set: PKCE Verifier generated for {provider}")
    
    # 3. Construct Supabase Authorize URL
    redirect_uri = "https://luviio.in/api/auth/callback"
    auth_url = (
        f"{SB_URL}/auth/v1/authorize?provider={provider}"
        f"&redirect_to={redirect_uri}"
        f"&code_challenge={code_challenge}"
        f"&code_challenge_method=S256"
    )
    
    return RedirectResponse(url=auth_url)


# ==========================================
# 1. OAUTH CALLBACK (Upgraded for PKCE)
# ==========================================
@router.get("/auth/callback")
async def oauth_callback(request: Request, code: str = None, error: str = None, error_description: str = None):
    if error:
        logger.warning(f"OAuth Error: {error} - {error_description}")
        return RedirectResponse(f"/login?error={error}")

    if not code:
        logger.warning("No code received in callback")
        return RedirectResponse("/login?error=no_code")

    # --- PKCE UPGRADE: Retrieve verifier from session ---
    code_verifier = request.session.get("code_verifier")
    
    if not code_verifier:
        logger.error("❌ Token Grant Error: Code verifier missing in session")
        return RedirectResponse("/login?error=session_expired&msg=Please+try+logging+in+again")

    # This MUST match the redirect_uri used in login_init exactly
    REDIRECT_URI = "https://luviio.in/api/auth/callback"

    try:
        # A. Exchange Code, Verifier, AND Redirect URI for Tokens
        # Upgrade: Passing REDIRECT_URI to fix the 400 Bad Request error
        token_result = await oauth_client.exchange_authorization_code(code, code_verifier, REDIRECT_URI)
        
        # Clean up session verifier
        request.session.pop("code_verifier", None)
        
        if not token_result.get("success"):
            error_msg = token_result.get("message", "Token exchange failed")
            logger.error(f"❌ Exchange Failed: {error_msg}")
            return RedirectResponse(f"/login?error=token_exchange_failed&msg={error_msg}")

        access_token = token_result.get("access_token")
        refresh_token = token_result.get("refresh_token")
        user = token_result.get("user", {})
        user_id = user.get("id")
        email = user.get("email", "unknown")

        # B. Check Profile & Determine Next Route
        next_url = await get_next_path(user_id, email)
        logger.info(f"✓ Auth success for {email} -> Redirecting to {next_url}")
        
        response = RedirectResponse(url=next_url, status_code=302)

        # 🔒 Set Secure Cookies
        response.set_cookie(
            key="sb-access-token", value=access_token,
            httponly=True, secure=True, samesite="lax", max_age=3600, path="/"
        )

        if refresh_token:
            response.set_cookie(
                key="sb-refresh-token", value=refresh_token,
                httponly=True, secure=True, samesite="lax", max_age=2592000, path="/"
            )

        return response

    except Exception as e:
        logger.error(f"❌ Unexpected callback error: {str(e)}")
        return RedirectResponse("/login?error=server_error")


# ==========================================
# 2. MANUAL EMAIL/PASSWORD AUTH (Unchanged)
# ==========================================
@router.post("/auth/flow")
async def auth_flow_manual(request: Request):
    if not SB_URL or not SB_KEY:
        return JSONResponse(status_code=500, content={"error": "Server misconfigured"})

    try:
        body = await request.json()
        email, password, action = body.get("email", "").strip().lower(), body.get("password", ""), body.get("action", "").lower()

        async with httpx.AsyncClient(timeout=10.0) as client:
            if action == "signup":
                auth_res = await client.post(
                    f"{SB_URL}/auth/v1/signup",
                    headers={"apikey": SB_KEY, "Content-Type": "application/json"},
                    json={"email": email, "password": password}
                )
                if auth_res.status_code not in [200, 201]:
                    return JSONResponse(status_code=400, content={"error": auth_res.json().get("message", "Signup failed")})
                
                data = auth_res.json()
                await get_next_path(data.get("id") or data.get("user", {}).get("id"), email)
                return JSONResponse(status_code=200, content={"next": "onboarding", "msg": "Signup successful!"})

            else:
                auth_res = await client.post(
                    f"{SB_URL}/auth/v1/token?grant_type=password",
                    headers={"apikey": SB_KEY, "Content-Type": "application/json"},
                    json={"email": email, "password": password}
                )
                if auth_res.status_code != 200:
                    return JSONResponse(status_code=401, content={"error": "Invalid credentials"})

                data = auth_res.json()
                user_id = data.get("user", {}).get("id")
                next_url = await get_next_path(user_id, email)
                return JSONResponse(status_code=200, content={"next": next_url.strip("/"), "session": data})

    except Exception as e:
        return JSONResponse(status_code=500, content={"error": "Server error"})


# ==========================================
# 3. LOGOUT (Unchanged)
# ==========================================
@router.get("/auth/logout")
async def logout(request: Request):
    response = RedirectResponse(url="/login", status_code=302)
    response.delete_cookie("sb-access-token", path="/")
    response.delete_cookie("sb-refresh-token", path="/")
    logger.info("✓ User logged out")
    return response


# ==========================================
# 4. AUTH STATUS CHECK (Unchanged)
# ==========================================
@router.get("/auth/status")
async def auth_status(request: Request):
    access_token = request.cookies.get("sb-access-token")
    if not access_token:
        return JSONResponse(status_code=401, content={"authenticated": False})

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            user_res = await client.get(
                f"{SB_URL}/auth/v1/user",
                headers={"Authorization": f"Bearer {access_token}", "apikey": SB_KEY}
            )
        if user_res.status_code == 200:
            return JSONResponse(status_code=200, content={"authenticated": True, "user": user_res.json()})
        return JSONResponse(status_code=401, content={"authenticated": False})
    except Exception:
        return JSONResponse(status_code=500, content={"error": "Status check failed"})
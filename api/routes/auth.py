import os
import httpx
import logging
import json
import asyncio
from fastapi import APIRouter, Request, Response
from fastapi.responses import RedirectResponse, JSONResponse
from supabase import create_client, Client
from datetime import datetime
from api.utils.oauth_client import SupabaseOAuthClient

# --- LOGGER SETUP ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("AUTH-ENGINE")

router = APIRouter()

# --- CONFIGURATION VALIDATION (Load & Validate) ---
SB_URL = os.environ.get("SB_URL")
SB_KEY = os.environ.get("SB_KEY")  # Anon Key
SB_SERVICE_KEY = os.environ.get("SB_SERVICE_ROLE_KEY")  # Service Key

# Startup validation
if not SB_URL or not SB_KEY or not SB_SERVICE_KEY:
    logger.critical("❌ CRITICAL: Missing Supabase environment variables (SB_URL, SB_KEY, or SB_SERVICE_ROLE_KEY)")
    logger.critical("Setup Error: Check your Vercel environment variables in project settings")

# Supabase Admin Client (For Profile Checks & Admin Operations)
try:
    supabase_admin: Client = create_client(SB_URL, SB_SERVICE_KEY) if SB_URL and SB_SERVICE_KEY else None
except Exception as e:
    logger.error(f"⚠️ Supabase initialization error: {e}")
    supabase_admin = None

# Initialize OAuth Client
try:
    oauth_client = SupabaseOAuthClient(SB_URL, SB_KEY, SB_SERVICE_KEY) if SB_URL and SB_KEY and SB_SERVICE_KEY else None
except Exception as e:
    logger.error(f"⚠️ OAuth Client initialization error: {e}")
    oauth_client = None


# ==========================================
# HELPER: CHECK/CREATE PROFILE & DECIDE ROUTE
# ==========================================
async def get_next_path(user_id: str, email: str) -> str:
    """
    3-State Logic:
    - State A: New User → Create Profile (onboarded=False) → /onboarding
    - State B: Incomplete → onboarded=False → /onboarding
    - State C: Complete → onboarded=True → /dashboard
    """
    if not supabase_admin:
        logger.warning(f"Supabase admin client unavailable for user {email}")
        return "/dashboard"

    try:
        # Check if profile exists
        res = supabase_admin.table("profiles").select("onboarded").eq("id", user_id).execute()

        if not res.data:
            # STATE A: New User → Create Profile
            logger.info(f"✓ Creating new profile for {email} (User ID: {user_id})")
            supabase_admin.table("profiles").insert({
                "id": user_id,
                "email": email,
                "onboarded": False,
                "created_at": datetime.utcnow().isoformat()
            }).execute()
            return "/onboarding"

        # STATE B/C: Profile exists → Check onboarding status
        is_onboarded = res.data[0].get("onboarded", False)
        state = "C (Complete)" if is_onboarded else "B (Incomplete)"
        logger.info(f"✓ Existing profile for {email} - State {state}")
        return "/dashboard" if is_onboarded else "/onboarding"

    except Exception as e:
        logger.error(f"❌ Profile Check Failed for {email}: {str(e)}")
        # Failsafe: Redirect to onboarding to ensure profile gets created
        return "/onboarding"


# ==========================================
# 1. OAUTH CALLBACK (Authorization Code Flow)
# ==========================================
@router.get("/auth/callback")
async def oauth_callback(request: Request, code: str = None, error: str = None, error_description: str = None):
    """
    OAuth 2.0 Authorization Code Flow - Server-Side Callback
    OAuth Provider redirects here with 'code' parameter.
    We exchange it for tokens server-side (secure, not exposed to client).
    Uses the new SupabaseOAuthClient for secure, modular token exchange.
    """
    # Handle OAuth provider errors
    if error:
        logger.warning(f"OAuth Provider Error: {error} - {error_description}")
        return RedirectResponse(f"/login?error={error}")

    if not code:
        logger.warning("OAuth Callback: No authorization code received")
        return RedirectResponse("/login?error=no_code&msg=Authorization+failed")

    if not oauth_client:
        logger.error("OAuth Client unavailable")
        return RedirectResponse("/login?error=config_error&msg=Server+misconfigured")

    try:
        # A. Exchange Authorization Code for Session (using OAuth client)
        token_result = await oauth_client.exchange_authorization_code(code)
        
        if not token_result.get("success"):
            error_msg = token_result.get("message", "Token exchange failed")
            logger.error(f"❌ {error_msg}")
            return RedirectResponse(f"/login?error=token_exchange_failed&msg={error_msg}")

        access_token = token_result.get("access_token")
        refresh_token = token_result.get("refresh_token")
        user = token_result.get("user", {})
        user_id = user.get("id")
        email = user.get("email", "unknown")

        if not access_token or not user_id:
            logger.error("❌ Token response missing critical data")
            return RedirectResponse("/login?error=invalid_token_response")

        # B. Check Profile & Determine Next Route (3-State Logic)
        next_url = await get_next_path(user_id, email)
        logger.info(f"✓ OAuth successful for {email} → Redirecting to {next_url}")

        # C. Create Secure Response with HTTPOnly Cookies
        response = RedirectResponse(url=next_url, status_code=302)

        # 🔒 HTTPOnly Secure Cookies (XSS-safe, only sent over HTTPS)
        response.set_cookie(
            key="sb-access-token",
            value=access_token,
            httponly=True,
            secure=True,  # HTTPS only
            samesite="lax",  # CSRF protection
            max_age=3600,  # 1 hour
            path="/"
        )

        if refresh_token:
            response.set_cookie(
                key="sb-refresh-token",
                value=refresh_token,
                httponly=True,
                secure=True,
                samesite="lax",
                max_age=2592000,  # 30 days
                path="/"
            )

        return response

    except httpx.TimeoutException:
        logger.error("❌ Token exchange timeout - Supabase unreachable")
        return RedirectResponse("/login?error=timeout&msg=Server+unreachable")
    except httpx.RequestError as e:
        logger.error(f"❌ Network error during token exchange: {str(e)}")
        return RedirectResponse("/login?error=network_error")
    except Exception as e:
        logger.error(f"❌ Unexpected callback error: {str(e)}")
        return RedirectResponse("/login?error=server_error&msg=Try+again+later")


# ==========================================
# 2. MANUAL EMAIL/PASSWORD AUTH
# ==========================================
@router.post("/auth/flow")
async def auth_flow_manual(request: Request):
    """
    Handles manual signup and login via email/password.
    Returns next route and session data for frontend.
    """
    if not SB_URL or not SB_KEY:
        return JSONResponse(
            status_code=500,
            content={"error": "Server misconfigured - missing Supabase keys"}
        )

    try:
        body = await request.json()
        email = body.get("email", "").strip().lower()
        password = body.get("password", "").strip()
        action = body.get("action", "").lower()

        # Input validation
        if not email or not password:
            return JSONResponse(
                status_code=400,
                content={"error": "Email and password required"}
            )

        if len(password) < 6:
            return JSONResponse(
                status_code=400,
                content={"error": "Password must be at least 6 characters"}
            )

        if action not in ["signup", "login"]:
            return JSONResponse(
                status_code=400,
                content={"error": "Invalid action"}
            )

        async with httpx.AsyncClient(timeout=10.0) as client:
            if action == "signup":
                # --- SIGNUP FLOW ---
                auth_res = await client.post(
                    f"{SB_URL}/auth/v1/signup",
                    headers={"apikey": SB_KEY, "Content-Type": "application/json"},
                    json={"email": email, "password": password}
                )

                if auth_res.status_code not in [200, 201]:
                    error_data = auth_res.json()
                    error_msg = error_data.get("error_description") or error_data.get("message") or "Signup failed"
                    logger.warning(f"Signup failed for {email}: {error_msg}")
                    return JSONResponse(
                        status_code=400,
                        content={"error": error_msg}
                    )

                data = auth_res.json()
                user_id = data.get("id") or data.get("user", {}).get("id")

                if user_id:
                    # Trigger profile creation
                    await get_next_path(user_id, email)
                    logger.info(f"✓ Signup successful for {email}")

                return JSONResponse(
                    status_code=200,
                    content={
                        "next": "onboarding",
                        "msg": "Signup successful! Check email for confirmation."
                    }
                )

            else:
                # --- LOGIN FLOW ---
                auth_res = await client.post(
                    f"{SB_URL}/auth/v1/token?grant_type=password",
                    headers={"apikey": SB_KEY, "Content-Type": "application/json"},
                    json={"email": email, "password": password}
                )

                if auth_res.status_code != 200:
                    error_data = auth_res.json()
                    error_msg = error_data.get("error_description") or "Invalid credentials"
                    logger.warning(f"Login failed for {email}: {error_msg}")
                    return JSONResponse(
                        status_code=401,
                        content={"error": error_msg}
                    )

                data = auth_res.json()
                user_id = data.get("user", {}).get("id")
                
                if not user_id:
                    logger.error(f"Login successful but missing user_id for {email}")
                    return JSONResponse(
                        status_code=500,
                        content={"error": "Session error - missing user data"}
                    )

                # Check profile status (3-State Logic)
                next_url = await get_next_path(user_id, email)
                logger.info(f"✓ Login successful for {email} → {next_url}")

                return JSONResponse(
                    status_code=200,
                    content={
                        "next": next_url.strip("/"),
                        "session": {
                            "access_token": data.get("access_token"),
                            "refresh_token": data.get("refresh_token"),
                            "expires_in": data.get("expires_in"),
                            "user": data.get("user")
                        }
                    }
                )

    except httpx.TimeoutException:
        logger.error(f"Auth timeout for {email if 'email' in locals() else 'unknown'}")
        return JSONResponse(
            status_code=503,
            content={"error": "Server timeout - try again"}
        )
    except json.JSONDecodeError:
        return JSONResponse(
            status_code=400,
            content={"error": "Invalid request format"}
        )
    except Exception as e:
        logger.error(f"❌ Unexpected auth error: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={"error": "Server error - try again later"}
        )


# ==========================================
# 3. LOGOUT
# ==========================================
@router.get("/auth/logout")
async def logout(request: Request):
    """
    Clears authentication cookies and redirects to login.
    """
    response = RedirectResponse(url="/login", status_code=302)
    response.delete_cookie("sb-access-token", path="/")
    response.delete_cookie("sb-refresh-token", path="/")
    logger.info(f"✓ Logout - {request.client.host}")
    return response


# ==========================================
# 4. AUTH STATUS CHECK (Optional - for frontend)
# ==========================================
@router.get("/auth/status")
async def auth_status(request: Request):
    """
    Check if user has valid session via cookies.
    Returns user info if authenticated.
    """
    access_token = request.cookies.get("sb-access-token")

    if not access_token:
        return JSONResponse(
            status_code=401,
            content={"authenticated": False}
        )

    try:
        if not SB_URL or not SB_KEY:
            return JSONResponse(status_code=500, content={"error": "Server misconfigured"})

        async with httpx.AsyncClient(timeout=5.0) as client:
            user_res = await client.get(
                f"{SB_URL}/auth/v1/user",
                headers={"Authorization": f"Bearer {access_token}", "apikey": SB_KEY}
            )

        if user_res.status_code == 200:
            user_data = user_res.json()
            return JSONResponse(
                status_code=200,
                content={
                    "authenticated": True,
                    "user": {
                        "id": user_data.get("id"),
                        "email": user_data.get("email")
                    }
                }
            )
        else:
            return JSONResponse(status_code=401, content={"authenticated": False})

    except Exception as e:
        logger.error(f"Auth status check error: {str(e)}")
        return JSONResponse(status_code=500, content={"error": "Status check failed"})

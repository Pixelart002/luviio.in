import os
import httpx
import logging
from fastapi import APIRouter, Request, Response
from fastapi.responses import RedirectResponse, JSONResponse
from supabase import create_client, Client

# --- LOGGER SETUP ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("AUTH-ENGINE")

router = APIRouter()

# --- CONFIGURATION (Load once) ---
SB_URL = os.environ.get("SB_URL")
SB_KEY = os.environ.get("SB_KEY") # Anon Key
SB_SERVICE_KEY = os.environ.get("SB_SERVICE_ROLE_KEY") # Service Key

# Supabase Admin Client (For Profile Checks)
supabase_admin: Client = create_client(SB_URL, SB_SERVICE_KEY)

# --- HELPER: CHECK PROFILE & DECIDE ---
async def get_next_path(user_id: str, email: str) -> str:
    try:
        # 1. Profile dhoondo
        res = supabase_admin.table("profiles").select("onboarded").eq("id", user_id).execute()
        
        # 2. Agar profile nahi hai -> Create karo
        if not res.data:
            logger.info(f"Creating profile for {email}")
            supabase_admin.table("profiles").insert({
                "id": user_id, 
                "email": email, 
                "onboarded": False
            }).execute()
            return "/onboarding"
        
        # 3. Agar hai -> Status check karo
        is_onboarded = res.data[0].get("onboarded", False)
        return "/dashboard" if is_onboarded else "/onboarding"

    except Exception as e:
        logger.error(f"Profile Check Failed: {e}")
        return "/dashboard" # Failsafe

# ==========================================
# 1. OAUTH CALLBACK (The Magic Endpoint)
# ==========================================
@router.get("/auth/callback")
async def oauth_callback(request: Request, code: str = None):
    """
    Google/GitHub yahan redirect karenge 'code' ke saath.
    Hum code exchange karke cookie set karenge.
    """
    if not code:
        return RedirectResponse("/login?error=no_code")

    try:
        # A. Code Exchange (Standard Auth)
        async with httpx.AsyncClient() as client:
            token_res = await client.post(
                f"{SB_URL}/auth/v1/token?grant_type=authorization_code",
                headers={
                    "apikey": SB_KEY,
                    "Content-Type": "application/x-www-form-urlencoded"
                },
                data={
                    "code": code,
                    "client_id": SB_KEY,
                    "redirect_uri": f"{str(request.base_url)}api/auth/callback" # Must match exactly
                }
            )
            
        if token_res.status_code != 200:
            logger.error(f"Token Exchange Error: {token_res.text}")
            return RedirectResponse("/login?error=token_failed")

        data = token_res.json()
        access_token = data.get("access_token")
        refresh_token = data.get("refresh_token")
        user = data.get("user")

        # B. Decide Destination
        next_url = await get_next_path(user['id'], user['email'])

        # C. Set Secure Cookie & Redirect
        response = RedirectResponse(url=next_url)
        
        # 🔒 Secure HTTPOnly Cookie (JS cannot steal this)
        response.set_cookie(
            key="sb-access-token",
            value=access_token,
            httponly=True,
            secure=True,
            samesite="lax",
            max_age=3600
        )
        response.set_cookie(
            key="sb-refresh-token",
            value=refresh_token,
            httponly=True,
            secure=True,
            samesite="lax",
            max_age=3600 * 24 * 30
        )
        
        return response

    except Exception as e:
        logger.error(f"Callback Error: {e}")
        return RedirectResponse("/login?error=server_error")


# ==========================================
# 2. MANUAL LOGIN / SIGNUP (API)
# ==========================================
@router.post("/auth/flow")
async def auth_flow_manual(request: Request, response: Response):
    try:
        body = await request.json()
        email = body.get("email")
        password = body.get("password")
        action = body.get("action")

        if not email or not password:
            return JSONResponse(status_code=400, content={"error": "Missing fields"})

        async with httpx.AsyncClient() as client:
            # --- SIGNUP ---
            if action == 'signup':
                auth_res = await client.post(
                    f"{SB_URL}/auth/v1/signup",
                    headers={"apikey": SB_KEY, "Content-Type": "application/json"},
                    json={"email": email, "password": password}
                )
                if auth_res.status_code not in [200, 201]:
                     return JSONResponse(status_code=400, content={"error": "Signup failed"})
                
                data = auth_res.json()
                # Create Profile manually since we are backend
                user_id = data.get("id") or data.get("user", {}).get("id")
                if user_id:
                     await get_next_path(user_id, email) # Just to trigger creation
                
                return JSONResponse(content={"next": "onboarding", "msg": "Check email"})

            # --- LOGIN ---
            else:
                auth_res = await client.post(
                    f"{SB_URL}/auth/v1/token?grant_type=password",
                    headers={"apikey": SB_KEY, "Content-Type": "application/json"},
                    json={"email": email, "password": password}
                )
                
                if auth_res.status_code != 200:
                    return JSONResponse(status_code=401, content={"error": "Invalid credentials"})

                data = auth_res.json()
                
                # Check Profile
                user_id = data['user']['id']
                next_url = await get_next_path(user_id, email)
                
                # Frontend ko bolo cookie set karle ya token lele
                # Since ye fetch call hai, hum token return kar denge client handle karega
                return JSONResponse(content={"next": next_url.strip("/"), "session": data})

    except Exception as e:
        logger.error(f"Manual Auth Error: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})

# ==========================================
# 3. LOGOUT
# ==========================================
@router.get("/auth/logout")
async def logout():
    response = RedirectResponse("/login")
    response.delete_cookie("sb-access-token")
    response.delete_cookie("sb-refresh-token")
    return response
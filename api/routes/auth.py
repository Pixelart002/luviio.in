import os
import httpx
import logging
from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse

logger = logging.getLogger("LUVIIO-APP")
router = APIRouter()

# --- CONFIGURATION ---
SB_URL = os.getenv("SB_URL")
SB_SERVICE_KEY = os.getenv("SB_SERVICE_ROLE_KEY") # ⚠️ Zaroori hai Profile check ke liye
SB_ANON_KEY = os.getenv("SB_KEY") # Client Login ke liye

@router.post("/auth/flow")
async def auth_flow(request: Request, response: Response):
    try:
        body = await request.json()
        action = body.get("action") # 'signup', 'login', or 'oauth_check'
        
        email = body.get("email")
        password = body.get("password")
        
        # Google/GitHub data
        user_id = body.get("user_id")
        user_email = body.get("user_email")

        # Headers for Admin/Service Actions
        service_headers = {
            "apikey": SB_SERVICE_KEY,
            "Authorization": f"Bearer {SB_SERVICE_KEY}",
            "Content-Type": "application/json"
        }

        async with httpx.AsyncClient() as client:

            # ==========================================
            #  SCENARIO 1: GOOGLE/GITHUB RETURN CHECK
            # ==========================================
            if action == 'oauth_check':
                if not user_id:
                    return JSONResponse(status_code=400, content={"error": "User ID missing"})

                # 1. Check Profile Exists?
                profile_res = await client.get(
                    f"{SB_URL}/rest/v1/profiles?id=eq.{user_id}&select=onboarded",
                    headers=service_headers
                )
                profile_data = profile_res.json()
                
                # Agar Profile nahi hai (First time Google Login) -> Create & Send to Onboarding
                if not profile_data:
                    await client.post(
                        f"{SB_URL}/rest/v1/profiles",
                        headers=service_headers,
                        json={"id": user_id, "email": user_email, "onboarded": False}
                    )
                    return JSONResponse(content={"next": "onboarding"})
                
                # Agar Profile hai -> Check Status
                is_onboarded = profile_data[0].get("onboarded", False)
                return JSONResponse(content={"next": "dashboard" if is_onboarded else "onboarding"})


            # ==========================================
            #  SCENARIO 2: NEW USER SIGNUP
            # ==========================================
            elif action == 'signup':
                if not email or not password:
                    return JSONResponse(status_code=400, content={"error": "Missing fields"})
                
                # 1. Create Auth User
                auth_res = await client.post(
                    f"{SB_URL}/auth/v1/signup",
                    headers={"apikey": SB_ANON_KEY, "Content-Type": "application/json"},
                    json={"email": email, "password": password}
                )

                if auth_res.status_code not in [200, 201]:
                    return JSONResponse(status_code=400, content={"error": "Signup failed. Email already exists?"})

                data = auth_res.json()
                new_id = data.get("id") or data.get("user", {}).get("id")

                # 2. Create Profile (onboarded: False)
                if new_id:
                    await client.post(
                        f"{SB_URL}/rest/v1/profiles",
                        headers=service_headers,
                        json={"id": new_id, "email": email, "onboarded": False}
                    )

                return JSONResponse(content={"next": "onboarding", "session": data.get("session")})


            # ==========================================
            #  SCENARIO 3: EXISTING USER LOGIN
            # ==========================================
            else: # login
                if not email or not password:
                    return JSONResponse(status_code=400, content={"error": "Missing fields"})

                # 1. Verify Credentials
                login_res = await client.post(
                    f"{SB_URL}/auth/v1/token?grant_type=password",
                    headers={"apikey": SB_ANON_KEY, "Content-Type": "application/json"},
                    json={"email": email, "password": password}
                )
                
                if login_res.status_code != 200:
                    return JSONResponse(status_code=401, content={"error": "Invalid email or password"})
                
                data = login_res.json()
                uid = data.get("user", {}).get("id")

                # 2. Check Profile Status
                p_res = await client.get(
                    f"{SB_URL}/rest/v1/profiles?id=eq.{uid}&select=onboarded", 
                    headers=service_headers
                )
                p_data = p_res.json()
                
                is_done = False
                if p_data and len(p_data) > 0:
                    is_done = p_data[0].get("onboarded", False)

                return JSONResponse(content={"next": "dashboard" if is_done else "onboarding", "session": data})

    except Exception as e:
        logger.error(f"Auth Error: {str(e)}")
        # FAILSAFE: "Dashboard pr pel do" logic
        return JSONResponse(content={"next": "dashboard"})
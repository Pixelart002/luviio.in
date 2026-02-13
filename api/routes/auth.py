import os
import httpx
from fastapi import APIRouter, Request, Response, HTTPException
from fastapi.responses import RedirectResponse, JSONResponse

router = APIRouter()

# Environment Variables (Vercel/Local pe set hone chahiye)
SB_URL = os.getenv("SB_URL")
SB_ANON_KEY = os.getenv("SB_ANON_KEY")
# Edge Function URL jo aapne deploy kiya hai
EDGE_FUNC_URL = "https://enqcujmzxtrbfkaungpm.supabase.co/functions/v1/signup_or_login_flow"

@router.post("/api/auth/flow")
async def auth_flow(request: Request, response: Response):
    try:
        # 1. Get data from Frontend
        body = await request.json()
        email = body.get("email")
        password = body.get("password")
        action = body.get("action") # 'signup' or 'login'

        if not email or not password or not action:
            raise HTTPException(status_code=400, detail="Missing fields")

        # 2. Call Edge Function (Backend-to-Backend)
        # Hum SB_ANON_KEY bhej rahe hain function invoke karne ke liye
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {SB_ANON_KEY}"
        }
        
        async with httpx.AsyncClient() as client:
            edge_res = await client.post(
                EDGE_FUNC_URL, 
                json={"email": email, "password": password, "action": action},
                headers=headers,
                timeout=15.0
            )

        if edge_res.status_code != 200:
            return JSONResponse(status_code=edge_res.status_code, content=edge_res.json())

        data = edge_res.json()
        session = data.get("session")
        next_path = data.get("next") # 'onboard' or 'dashboard'

        # 3. Securely set the Session in a Cookie
        # Isse browser mein JavaScript session chura nahi payega
        res = JSONResponse(content={"next": next_path})
        if session:
            res.set_cookie(
                key="supabase-auth-token",
                value=session.get("access_token"),
                httponly=True,
                secure=True,
                samesite="lax",
                max_age=3600
            )
        return res

    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})
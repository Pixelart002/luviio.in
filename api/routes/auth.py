import uuid
import logging
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Response, HTTPException, Request, BackgroundTasks
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel, EmailStr

# --- INTERNAL MODULES ---
from api.utils.security import (
    hash_password, 
    verify_password, 
    get_auth_tokens
)
from api.routes.database import (
    supabase_admin, 
    create_user_profile,
    log_audit_event
)
from api.utils.cookies import set_login_cookies, clear_auth_cookies

# --- SETUP ---
router = APIRouter()
logger = logging.getLogger("AUTH-MANUAL")

# --- SCHEMAS ---
class LoginSchema(BaseModel):
    email: EmailStr
    password: str

class RegisterSchema(BaseModel):
    email: EmailStr
    password: str

# --- HELPER: CREATE SESSION ---
async def create_db_session(user_id: str, request: Request, refresh_token: str) -> str:
    """Session ID DB me save karta hai"""
    session_id = str(uuid.uuid4())
    try:
        supabase_admin.table("sessions").insert({
            "id": session_id,
            "user_id": user_id,
            "refresh_token": refresh_token,
            "is_revoked": False,
            "expires_at": (datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
            "user_agent": request.headers.get("user-agent", "Unknown"),
            "ip_address": request.client.host
        }).execute()
        return session_id
    except Exception as e:
        logger.error(f"⚠️ Session Create Failed: {e}")
        # Agar DB fail bhi ho, tab bhi session ID return karo taaki user login ho sake
        return session_id

# ==========================================
# 🔐 AUTH ROUTES
# ==========================================

@router.post("/register")
async def register(payload: RegisterSchema, background_tasks: BackgroundTasks):
    email = payload.email.lower()
    
    # 1. Check if user exists
    existing = supabase_admin.table("users").select("id").eq("email", email).execute()
    if existing.data:
        raise HTTPException(status_code=400, detail="User already registered")

    # 2. Create User in DB
    hashed_pw = hash_password(payload.password)
    try:
        user_data = {
            "email": email, 
            "password": hashed_pw, 
            "provider": "email",
            "onboarded": False
        }
        new_user = supabase_admin.table("users").insert(user_data).execute()
        user_id = new_user.data[0]["id"]
        
        # 3. Create Profile
        await create_user_profile(user_id=user_id, email=email)
        
        return {"msg": "Account created successfully. Please login."}
        
    except Exception as e:
        logger.error(f"❌ Register Error: {str(e)}")
        raise HTTPException(status_code=500, detail="Registration failed")

@router.post("/login")
async def login(payload: LoginSchema, response: Response, request: Request, background_tasks: BackgroundTasks):
    email = payload.email.lower()

    # 1. Find User
    user_res = supabase_admin.table("users").select("*").eq("email", email).execute()
    if not user_res.data:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    user = user_res.data[0]

    # 2. Verify Password
    if not verify_password(payload.password, user.get("password") or ""):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    # 3. Generate Tokens
    access_token, refresh_token = get_auth_tokens(user["id"])
    
    # 4. Create Session in DB
    session_id = await create_db_session(user["id"], request, refresh_token)

    # 5. Set Cookies (Standard & Delegation)
    # Hum seedha response object modify kar rahe hain, return nahi kar rahe
    final_response = JSONResponse(content={
        "status": "ok", 
        "user_id": user["id"],
        "onboarded": user.get("onboarded", False)
    })
    
    set_login_cookies(final_response, access_token, refresh_token, session_id)
    
    # 6. Logging
    background_tasks.add_task(log_audit_event, user_id=user["id"], action="login_email", request=request)
    
    return final_response

@router.get("/logout")
async def logout(response: Response, request: Request):
    # 1. Revoke Session in DB (Optional best practice)
    # (Abhi skip kar rahe hain taaki code simple rahe)
    
    # 2. Clear Cookies
    clear_auth_cookies(response)
    
    # 3. Redirect
    return {"msg": "Logged out"}
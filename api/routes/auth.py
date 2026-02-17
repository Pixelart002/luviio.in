import uuid
import logging
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Response, HTTPException, Request, BackgroundTasks
from fastapi.responses import JSONResponse
from pydantic import BaseModel, EmailStr

# --- MODULAR IMPORTS ---
from api.routes.database import supabase_admin, create_user_profile, log_audit_event
from api.utils.security import hash_password, verify_password, get_auth_tokens
from api.utils.cookies import set_login_cookies, clear_auth_cookies

router = APIRouter()
logger = logging.getLogger("AUTH-MODULAR")

# --- SCHEMAS ---
class LoginSchema(BaseModel):
    email: EmailStr
    password: str

class RegisterSchema(BaseModel):
    email: EmailStr
    password: str

# --- HELPER (Session is part of Auth Flow) ---
async def create_db_session(user_id: str, request: Request, refresh_token: str) -> str:
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
    except Exception as e:
        logger.error(f"Session DB Error: {e}")
    return session_id

# ==========================================
# 🚀 AUTH ROUTES
# ==========================================

@router.post("/register")
async def register(payload: RegisterSchema, background_tasks: BackgroundTasks):
    email = payload.email.lower()
    
    # Check User
    existing = supabase_admin.table("users").select("id").eq("email", email).execute()
    if existing.data:
        raise HTTPException(status_code=400, detail="User already registered")

    # Hash & Save
    hashed = hash_password(payload.password) # <-- Imported from security.py
    
    try:
        new_user = supabase_admin.table("users").insert({
            "email": email, "password": hashed, "provider": "email", "onboarded": False
        }).execute()
        
        user_id = new_user.data[0]["id"]
        await create_user_profile(user_id=user_id, email=email)
        return {"msg": "Registered successfully"}
    except Exception as e:
        logger.error(f"Register Failed: {e}")
        raise HTTPException(status_code=500, detail="Registration failed")

@router.post("/login")
async def login(payload: LoginSchema, request: Request, background_tasks: BackgroundTasks):
    email = payload.email.lower()

    # 1. DB Lookup
    user_res = supabase_admin.table("users").select("*").eq("email", email).execute()
    if not user_res.data:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    user = user_res.data[0]

    # 2. Logic Check (Modular)
    if not verify_password(payload.password, user.get("password") or ""): # <-- Imported
        raise HTTPException(status_code=401, detail="Invalid credentials")

    # 3. Token Gen (Modular)
    access, refresh = get_auth_tokens(user["id"]) # <-- Imported
    
    # 4. Session
    session_id = await create_db_session(user["id"], request, refresh)

    # 5. Delivery (Modular Cookies)
    response = JSONResponse(content={
        "status": "ok", "user_id": user["id"], "onboarded": user.get("onboarded", False)
    })
    set_login_cookies(response, access, refresh, session_id) # <-- Imported
    
    # 6. Audit
    background_tasks.add_task(log_audit_event, user_id=user["id"], action="login_email", request=request)
    return response

@router.get("/logout")
async def logout(response: Response):
    clear_auth_cookies(response)
    return {"msg": "Logged out"}
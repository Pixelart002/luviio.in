# backend/services/user_service.py
import os
import uuid
from datetime import datetime
from supabase import create_client, Client
from fastapi import HTTPException, status

# Import hamare banaye hue schemas aur security engine
from schemas.user import UserCreate
from core.security import get_password_hash

# 1. Supabase Connection Setup
# Dhyan rahe: Custom auth ke liye hum hamesha Service Role Key use karte hain
SB_URL = os.getenv("SB_URL", "")
SB_SERVICE_ROLE_KEY = os.getenv("SB_SERVICE_ROLE_KEY", "")

# Agar keys nahi mili toh code ko crash hone se bachane ke liye (Local dev ke liye safe)
if SB_URL and SB_SERVICE_ROLE_KEY:
    supabase: Client = create_client(SB_URL, SB_SERVICE_ROLE_KEY)
else:
    supabase = None
    print("⚠️ WARNING: Supabase keys not found in environment!")

def create_new_user(user_data: UserCreate):
    """Naye user ko validate aur encrypt karke database mein save karta hai"""
    
    if not supabase:
         raise HTTPException(status_code=500, detail="Database connection error")

    # STEP 1: Check karo ki kya yeh Email pehle se database mein hai?
    # Hum ek custom 'users' table banayenge public schema mein
    existing_user = supabase.table("users").select("*").eq("email", user_data.email).execute()

    if len(existing_user.data) > 0:
        # Agar user mil gaya, toh yahin se 400 Bad Request error phek do
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User with this email already exists!"
        )

    # STEP 2: Password Hash (Encrypt) Karo
    # Frontend se aaya plain password 'security.py' mein bheja aur ajeeb string wapas li
    hashed_password = get_password_hash(user_data.password)

    # STEP 3: Naya User Object Taiyaar Karo (Jo database columns se match karega)
    new_user_db_data = {
        "id": str(uuid.uuid4()),               # Ek random unique ID banayi
        "name": user_data.name,
        "email": user_data.email,
        "password_hash": hashed_password,      # Sirf hashed password jayega, asli wala nahi!
        "created_at": datetime.utcnow().isoformat(),
        "is_active": True
    }

    # STEP 4: Supabase ke 'users' table mein data Insert kar do
    response = supabase.table("users").insert(new_user_db_data).execute()

    # Insert hone ke baad jo record bana, usko return kar do
    return response.data[0]
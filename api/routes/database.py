import os
import logging
from functools import wraps
from typing import Optional, Dict, Any
from supabase import create_client, Client
from postgrest.exceptions import APIError

# --- 🪵 PRODUCTION LOGGING SETUP ---
# Har DB operation ko track karne ke liye detailed format
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(name)s | %(levelname)s | %(message)s'
)
logger = logging.getLogger("DATABASE-ENGINE")

# --- 🔑 CONFIGURATION ---
SB_URL = os.environ.get("SB_URL") or os.environ.get("SUPABASE_URL")
SB_ADMIN_KEY = os.environ.get("SB_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_SERVICE_ROLE_KEY")

if not SB_URL or not SB_ADMIN_KEY:
    logger.critical("❌ FATAL: Supabase Admin Credentials missing in Environment Variables!")

# --- 🚀 INITIALIZE ADMIN CLIENT ---
try:
    # Service Role Key use kar rahe hain taaki RLS bypass ho sake
    supabase_admin: Client = create_client(SB_URL, SB_ADMIN_KEY)
    logger.info("✅ Success: Supabase Admin Client initialized (Service Role Bypass Active)")
except Exception as e:
    logger.error(f"❌ Failure: Could not initialize Supabase Admin: {str(e)}")
    supabase_admin = None

# --- 🛡️ DATABASE WRAPPER (Heavy Logging) ---
def db_safe_execute(func):
    """
    Decorator jo har DB call ka post-mortem karta hai.
    """
    @wraps(func)
    async def wrapper(*args, **kwargs):
        func_name = func.__name__
        try:
            logger.info(f"🗄️ [DB-START] Triggering: {func_name} | Args: {args}")
            result = await func(*args, **kwargs)
            logger.info(f"✅ [DB-SUCCESS] Finished: {func_name}")
            return result
        except APIError as e:
            logger.error(f"❌ [DB-API-ERROR] Supabase rejected {func_name}: {e.message}")
            return {"success": False, "error": e.message}
        except Exception as e:
            logger.error(f"❌ [DB-FATAL-ERROR] Unexpected crash in {func_name}: {str(e)}")
            return {"success": False, "error": "Internal Database Error"}
    return wrapper

# --- 🛠️ PRODUCTION HELPER FUNCTIONS ---

@db_safe_execute
async def create_user_profile(user_id: str, email: str, username: Optional[str] = None):
    """
    Registration ke waqt initial profile row banane ke liye.
    """
    logger.info(f"🆕 Creating skeleton profile for User: {email}")
    profile_data = {
        "id": user_id,
        "full_name": email.split('@')[0],
        "username": username or f"user_{user_id[:8]}",
        "avatar_url": f"https://api.dicebear.com/7.x/avataaars/svg?seed={user_id}"
    }
    # .insert() use kar rahe hain kyunki ye first time setup hai
    res = supabase_admin.table("profiles").insert(profile_data).execute()
    logger.info(f"👤 Profile row inserted for {user_id}")
    return {"success": True, "data": res.data}

@db_safe_execute
async def save_onboarding_data(user_id: str, profile_updates: Dict[str, Any], store_data: Optional[Dict[str, Any]] = None):
    """
    🔥 THE ULTIMATE FIX: Profile aur Store ka data ek saath save karne ke liye.
    """
    logger.info(f"🚀 Processing atomic onboarding for UserID: {user_id}")
    
    # 1. Profile Update (UPSERT ensures row creation if registration failed)
    profile_updates["id"] = user_id
    logger.info(f"📝 Upserting profile for {user_id} with data: {profile_updates}")
    supabase_admin.table("profiles").upsert(profile_updates).execute()
    
    # 2. Store Entry (Agar User 'seller' hai)
    if store_data:
        logger.info(f"🏪 Inserting Store details for Seller: {user_id}")
        store_data["owner_id"] = user_id
        supabase_admin.table("stores").insert(store_data).execute()
    
    # 3. SET THE STAMP: Activate account for Dashboard
    logger.info(f"🏁 Final Step: Marking User {user_id} as onboarded in core table")
    supabase_admin.table("users").update({"onboarded": True}).eq("id", user_id).execute()
    
    return {"success": True}

@db_safe_execute
async def log_audit_event(user_id: str, action: str, request: Any):
    """
    Security aur access logs maintain karne ke liye.
    """
    client_ip = request.client.host if hasattr(request, 'client') else "0.0.0.0"
    user_agent = request.headers.get("user-agent", "unknown")
    
    log_data = {
        "user_id": user_id,
        "action": action,
        "ip_address": client_ip,
        "user_agent": user_agent
    }
    
    logger.info(f"📝 Recording audit log: {action} for user {user_id}")
    supabase_admin.table("audit_logs").insert(log_data).execute()
    return {"success": True}

@db_safe_execute
async def update_onboarding_status(user_id: str, status: bool = True):
    """
    Simple status toggle helper.
    """
    logger.info(f"⚙️ Toggling onboarding flag to {status} for {user_id}")
    res = supabase_admin.table("users").update({"onboarded": status}).eq("id", user_id).execute()
    return {"success": True, "data": res.data}
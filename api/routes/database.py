import os
from functools import wraps
from supabase import create_client, Client
from postgrest.exceptions import APIError

# Load Env Variables (Vercel ya Local .env se)
url: str = os.environ.get("SUPABASE_URL")
key: str = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")

# Initialize Client
supabase: Client = create_client(url, key)

# --- DATABASE WRAPPER (Decorator) ---
def db_safe_execute(func):
    """
    Ye wrapper har database call ko try-except mein wrap karega
    taaki app crash na ho aur clean error mile.
    """
    @wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except APIError as e:
            # Yahan logging add kar sakte ho
            print(f"Supabase API Error: {e.message}")
            return {"success": False, "error": e.message}
        except Exception as e:
            print(f"Unexpected DB Error: {str(e)}")
            return {"success": False, "error": "Internal Server Error"}
    return wrapper
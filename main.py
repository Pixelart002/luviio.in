# main.py

# Absolute import using "as" style
from backend.api import supabase as sb_router

# Access Supabase clients directly from the module
supabase = sb_router.supabase_client
supabase_service = sb_router.supabase_service_client

# ----------------------------
# Simple Health Check Function
# ----------------------------
def health_check():
    """
    Supabase health check:
    Try to fetch 1 row from a test table (e.g., 'users')
    to see if the connection is working.
    """
    try:
        response = supabase.table("users").select("*").limit(1).execute()
        if response.data is not None:
            return True, "Supabase connection is healthy ✅"
        else:
            return False, "Supabase connection ok, but table is empty ⚠️"
    except Exception as e:
        return False, f"Supabase connection failed ❌: {e}"

# ----------------------------
# Run health check automatically
# ----------------------------
status, message = health_check()
print(message)
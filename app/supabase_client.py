from supabase import create_client, Client
from app.config import settings

# Anon client — respects RLS (use for user-facing operations)
def get_supabase() -> Client:
    return create_client(settings.SB_URL, settings.SB_KEY)

# Service role client — bypasses RLS (use only in trusted server code)
def get_admin_supabase() -> Client:
    return create_client(settings.SB_URL, settings.SB_SERVICE_ROLE_KEY)

# Singleton instances
supabase: Client = None
admin_supabase: Client = None

def init_clients():
    global supabase, admin_supabase
    supabase = create_client(settings.SB_URL, settings.SB_KEY)
    admin_supabase = create_client(settings.SB_URL, settings.SB_SERVICE_ROLE_KEY)

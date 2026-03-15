from supabase import create_client, Client
from app.config import settings

# Singleton instances
supabase: Client = None
admin_supabase: Client = None


def init_clients():
    """App startup pe ek baar call hota hai — main.py lifespan mein"""
    global supabase, admin_supabase
    supabase = create_client(settings.SB_URL, settings.SB_KEY)
    admin_supabase = create_client(settings.SB_URL, settings.SB_SERVICE_ROLE_KEY)


def get_supabase() -> Client:
    """Anon client — RLS respect karta hai (user-facing operations)"""
    if supabase is None:
        raise RuntimeError("Supabase client not initialized. Call init_clients() first.")
    return supabase


def get_admin_supabase() -> Client:
    """Service role client — RLS bypass karta hai (trusted server code only)"""
    if admin_supabase is None:
        raise RuntimeError("Supabase admin client not initialized. Call init_clients() first.")
    return admin_supabase
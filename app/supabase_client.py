from supabase import create_client, Client
from app.config import settings

supabase: Client | None = None
admin_supabase: Client | None = None


def init_clients() -> None:
    """
    App startup pe ek baar call hota hai.
    Temp vars mein banao — partial init prevent karo.
    """
    global supabase, admin_supabase
    _sb    = create_client(settings.SB_URL, settings.SB_KEY)
    _admin = create_client(settings.SB_URL, settings.SB_SERVICE_ROLE_KEY)
    supabase, admin_supabase = _sb, _admin  # atomic


def get_supabase() -> Client:
    if supabase is None:
        raise RuntimeError("Supabase client not initialized. Call init_clients() first.")
    return supabase


def get_admin_supabase() -> Client:
    if admin_supabase is None:
        raise RuntimeError("Supabase admin client not initialized. Call init_clients() first.")
    return admin_supabase
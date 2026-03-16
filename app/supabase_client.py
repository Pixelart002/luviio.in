from supabase import create_client, Client
from app.config import settings

# Singleton instances
supabase: Client | None = None
admin_supabase: Client | None = None


def init_clients() -> None:
    """
    App startup pe ek baar call hota hai — main.py lifespan mein.
    Temp variables use karte hain taaki partial init na ho agar dusra fail kare.
    """
    global supabase, admin_supabase

    if not settings.SB_URL or not settings.SB_KEY or not settings.SB_SERVICE_ROLE_KEY:
        raise RuntimeError("SB_URL, SB_KEY, and SB_SERVICE_ROLE_KEY must all be set")

    # Build both first — agar koi fail ho toh global state touch nahi hoti
    _sb = create_client(settings.SB_URL, settings.SB_KEY)
    _admin = create_client(settings.SB_URL, settings.SB_SERVICE_ROLE_KEY)

    # Atomic assignment — dono ya koi nahi
    supabase, admin_supabase = _sb, _admin


def get_supabase() -> Client:
    """Anon client — RLS respect karta hai (user-facing operations)."""
    if supabase is None:
        raise RuntimeError("Supabase client not initialized. Call init_clients() first.")
    return supabase


def get_admin_supabase() -> Client:
    """Service role client — RLS bypass karta hai (trusted server code only)."""
    if admin_supabase is None:
        raise RuntimeError("Supabase admin client not initialized. Call init_clients() first.")
    return admin_supabase
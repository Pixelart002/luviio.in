from supabase import create_client, Client
from api.config import settings

def get_supabase_client(use_service_role: bool = False) -> Client:
    """
    Returns a Supabase client.
    If use_service_role=True, uses the service role key (for admin ops like seeding).
    Otherwise uses the anon key (for public data fetching).
    """
    key = settings.SUPABASE_SERVICE_ROLE_KEY if use_service_role else settings.SUPABASE_ANON_KEY
    return create_client(settings.SUPABASE_URL, key)
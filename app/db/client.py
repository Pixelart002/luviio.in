from functools import lru_cache
from supabase import create_client, Client
from app.core.config import settings

@lru_cache(maxsize=1)
def get_supabase_client() -> Client:
    """
    Returns a singleton Supabase client.
    Only creates the client when first called.
    """
    if not settings.SB_URL or not settings.SB_KEY:
        raise RuntimeError(
            "Supabase URL and KEY must be set in environment variables (SB_URL, SB_KEY)."
        )
    
    try:
        client = create_client(settings.SB_URL, settings.SB_KEY)
        return client
    except Exception as e:
        raise RuntimeError(f"Failed to create Supabase client: {e}")

# ⚠️ IMPORTANT: Do NOT create the client at module level
# Remove any line like: supabase_client = get_supabase_client()
# The client will be created only when get_supabase_client() is called
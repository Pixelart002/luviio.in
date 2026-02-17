from supabase import create_client, Client
from app.core.config import settings

# Singleton pattern for DB connection
class SupabaseService:
    _instance: Client = None

    @classmethod
    def get_client(cls) -> Client:
        if cls._instance is None:
            try:
                cls._instance = create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY)
            except Exception as e:
                print(f"Supabase connection failed (Check ENV): {e}")
                # Fallback for build/test environments without creds
                return None 
        return cls._instance
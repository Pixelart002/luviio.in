from supabase import create_client, Client
from app.core.config import settings

supabase_client: Client = create_client(
    settings.SB_URL,
    settings.SB_KEY
)

async def get_db() -> Client:
    return supabase_client
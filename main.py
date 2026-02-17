# main.py

# Absolute import using "as" style
from backend.api import supabase as sb_router

# Access Supabase clients directly from the module
supabase = sb_router.supabase_client
supabase_service = sb_router.supabase_service_client

# Print confirmation (optional, for demonstration)
print("Supabase clients initialized successfully:")
print("Regular client:", supabase)
print("Service role client:", supabase_service)
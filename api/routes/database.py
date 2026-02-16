import os
from supabase import create_client, Client

# --- 🔑 CONFIGURATION ---
# Get credentials from environment variables (checks for both common naming patterns)
SB_URL = os.environ.get("SB_URL") or os.environ.get("SUPABASE_URL")
SB_KEY = os.environ.get("SB_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_SERVICE_ROLE_KEY")

# Simple check to ensure keys exist
if not SB_URL or not SB_KEY:
    raise ValueError("❌ Fatal: Supabase URL or Key is missing.")

# --- 🚀 INITIALIZE CLIENT ---
try:
    # Create the connection
    supabase: Client = create_client(SB_URL, SB_KEY)
    print("✅ Supabase Client Initialized")
except Exception as e:
    print(f"❌ Connection Error: {e}")
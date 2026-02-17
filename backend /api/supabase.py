# supabase.py - Supabase connection module

import os
from supabase import create_client, Client

# ----------------------------
# Load environment variables
# ----------------------------
SB_URL = os.getenv("SB_URL")
SB_KEY = os.getenv("SB_KEY")
SB_SERVICE_ROLE_KEY = os.getenv("SB_SERVICE_ROLE_KEY")

# Validate environment variables
if not SB_URL or not SB_KEY or not SB_SERVICE_ROLE_KEY:
    raise ValueError(
        "Please set the following environment variables: "
        "SB_URL, SB_KEY, SB_SERVICE_ROLE_KEY"
    )

# ----------------------------
# Initialize Supabase clients
# ----------------------------
supabase_client: Client = create_client(SB_URL, SB_KEY)
supabase_service_client: Client = create_client(SB_URL, SB_SERVICE_ROLE_KEY)

# ----------------------------
# Optional: simple log to confirm initialization
# ----------------------------
print("Supabase clients initialized successfully:")
print("Regular client:", supabase_client)
print("Service role client:", supabase_service_client)
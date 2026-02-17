# supabase.py - Supabase connection module

import os
from supabase import create_client, Client

# Load env variables
SB_URL = os.getenv("SB_URL")
SB_KEY = os.getenv("SB_KEY")
SB_SERVICE_ROLE_KEY = os.getenv("SB_SERVICE_ROLE_KEY")

if not SB_URL or not SB_KEY or not SB_SERVICE_ROLE_KEY:
    raise ValueError("Please set SB_URL, SB_KEY, and SB_SERVICE_ROLE_KEY environment variables.")

# Initialize Supabase clients
supabase_client: Client = create_client(SB_URL, SB_KEY)
supabase_service_client: Client = create_client(SB_URL, SB_SERVICE_ROLE_KEY)
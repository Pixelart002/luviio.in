import os
from dotenv import load_dotenv
from supabase import create_client, Client

# .env file load karne ke liye
load_dotenv()

# Tumhare custom variables
SB_URL = os.getenv("SB_URL")
SB_KEY = os.getenv("SB_KEY") 
SB_SERVICE_ROLE_KEY = os.getenv("SB_SERVICE_ROLE_KEY")

# Check agar variables load nahi hue
if not SB_URL or not SB_KEY:
    raise ValueError("Bhai, Supabase credentials nahi mili! .env file check karo.")

# 1. Standard Client (Normal operations ke liye)
supabase: Client = create_client(SB_URL, SB_KEY)

# 2. Admin Client (Jab backend se admin level ka kaam karna ho, jaise RLS bypass)
supabase_admin: Client = create_client(SB_URL, SB_SERVICE_ROLE_KEY) if SB_SERVICE_ROLE_KEY else None

def get_db() -> Client:
    """
    Normal queries ke liye isko call karenge.
    """
    return supabase

def get_admin_db() -> Client:
    """
    High privilege queries (Auth/Admin) ke liye isko call karenge.
    """
    return supabase_admin
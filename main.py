from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
import os

# --- 1. THE CONNECTIONS (IMPORTS) ---
# We explicitly import every core module to ensure they are "connected" and valid.
# Pattern: From [folder] import [filename] as [alias]

# Connect Configuration
from app.core import config as config_settings

# Connect Database Client
from app.core import supabase as supabase_service

# Connect Schemas (Data Models)
from app.schemas import leads as leads_schema

# Connect Routers (Routes)
from app.routers import public as public_router

# --- 2. APP INITIALIZATION ---
app = FastAPI(
    title=config_settings.settings.PROJECT_NAME, # Using the config immediately
    docs_url=None, 
    redoc_url=None
)

# --- 3. STATIC FILES SETUP ---
# Robust way to find the 'static' folder relative to this file
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
static_path = os.path.join(BASE_DIR, "static")
os.makedirs(static_path, exist_ok=True) # Create if it doesn't exist to prevent errors

app.mount("/static", StaticFiles(directory=static_path), name="static")

# --- 4. ROUTER REGISTRATION ---
app.include_router(public_router.router)

# --- 5. STARTUP HEALTH CHECK ---
@app.on_event("startup")
async def startup_event():
    print(f"[{config_settings.settings.PROJECT_NAME}] Engine: STARTING...")
    
    # Verify Supabase Connection
    db_client = supabase_service.SupabaseService.get_client()
    if db_client:
        print(f"[{config_settings.settings.PROJECT_NAME}] Supabase: CONNECTED")
    else:
        print(f"[{config_settings.settings.PROJECT_NAME}] Supabase: WARNING - Connection Failed (Check .env)")

    # Verify Schemas are loaded
    print(f"[{config_settings.settings.PROJECT_NAME}] Schemas: LOADED ({leads_schema.__name__})")
    
    print(f"[{config_settings.settings.PROJECT_NAME}] System: ONLINE")

@app.get("/health")
async def health_check():
    """
    Production health check endpoint for Vercel/AWS/Render
    """
    return {
        "status": "healthy",
        "env": config_settings.settings.PROJECT_NAME,
        "database": "connected" if supabase_service.SupabaseService.get_client() else "offline"
    }
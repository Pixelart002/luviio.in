import os
import sys
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

# --- 🛠️ PATH SETUP ---
BASE_DIR = Path(__file__).resolve().parent
sys.path.append(str(BASE_DIR))

# --- 🔗 CONNECTING FILES ---
try:
    # 1. Database Connection Import
    from api.routes.database import supabase
    
    # 2. Mail Router Import
    from api.routes.resend_mail import router as mail_router
    
    print("✅ All Modules Imported Successfully")
except ImportError as e:
    print(f"⚠️ Import Error: {e} | Check your folder structure!")
    supabase = None
    mail_router = None

# --- 🚀 APP INIT ---
app = FastAPI(title="LUVIIO Clean Engine")

# --- 🔌 INCLUDE ROUTERS ---
if mail_router:
    app.include_router(mail_router, prefix="/api", tags=["Mail"])

# --- 🎨 TEMPLATES & STATIC ---
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

# ==========================================
# 🏥 HEALTH CHECK (Database Status)
# ==========================================
@app.get("/health")
async def health_check():
    """
    Checks Supabase Connection status.
    """
    db_status = "disconnected"
    
    if supabase:
        try:
            # Fake query to check connection
            supabase.table("users").select("count", count="exact").limit(1).execute()
            db_status = "connected"
        except Exception as e:
            db_status = f"error: {str(e)}"

    return {
        "server": "online",
        "database": db_status,
        "modules": {
            "mail_router": "loaded" if mail_router else "failed"
        }
    }

# ==========================================
# 🏠 HOME ROUTE
# ==========================================
@app.get("/")
async def home(request: Request):
    # Note: Ensure index.html exists in /templates root or change to pages/home.html
    return templates.TemplateResponse("pages/index.html", {"request": request})

# ==========================================
# 📊 DASHBOARD ROUTE (New Added)
# ==========================================
@app.get("/dashboard")
async def dashboard(request: Request):
    """
    Loads the Dashboard page from templates/pages/dashboard.html
    """
    return templates.TemplateResponse("pages/dashboard.html", {"request": request})
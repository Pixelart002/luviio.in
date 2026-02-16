import os
import sys
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

# ==========================================
# 🛠️ ROBUST PATH SETUP (The Fix)
# ==========================================
# Current file (main.py) location
CURRENT_FILE = Path(__file__).resolve()
CURRENT_DIR = CURRENT_FILE.parent

# Logic: Dhoondo 'templates' folder kahan hai
# 1. Check same folder (Localhost mostly)
if (CURRENT_DIR / "templates").is_dir():
    BASE_DIR = CURRENT_DIR
# 2. Check parent folder (Vercel / Production structure)
elif (CURRENT_DIR.parent / "templates").is_dir():
    BASE_DIR = CURRENT_DIR.parent
else:
    # Fallback (Agar kuch na mile)
    BASE_DIR = CURRENT_DIR
    print("⚠️ WARNING: Templates folder not found automatically!")

# System Path update taaki imports na fatein
sys.path.append(str(BASE_DIR))

print(f"📂 Project Root Detected: {BASE_DIR}")

# ==========================================
# 🔗 CONNECTING MODULES
# ==========================================
try:
    # 1. Database Connection
    from api.routes.database import supabase
    
    # 2. Mail Router
    from api.routes.resend_mail import router as mail_router
    
    print("✅ All Core Modules Imported Successfully")
except ImportError as e:
    # Fallback for flat structure
    try:
        from routes.database import supabase
        from routes.resend_mail import router as mail_router
        print("✅ Modules Imported via Fallback")
    except Exception as inner_e:
        print(f"⚠️ Import Error: {e} | {inner_e}")
        supabase = None
        mail_router = None

# --- 🚀 APP INIT ---
app = FastAPI(title="LUVIIO Clean Engine")

# --- 🔌 INCLUDE ROUTERS ---
if mail_router:
    app.include_router(mail_router, prefix="/api", tags=["Mail"])

# --- 🎨 TEMPLATES & STATIC SETUP ---
# Ab hum calculated BASE_DIR use kar rahe hain (Fixes TemplateNotFound)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

# ==========================================
# 🏥 HEALTH CHECK
# ==========================================
@app.get("/health")
async def health_check():
    """Checks Supabase Connection status."""
    db_status = "disconnected"
    
    if supabase:
        try:
            # Lightweight query to check connection
            supabase.table("users").select("count", count="exact").limit(1).execute()
            db_status = "connected"
        except Exception as e:
            db_status = f"error: {str(e)}"

    return {
        "status": "online",
        "database": db_status,
        "path_config": {
            "root": str(BASE_DIR),
            "templates": str(BASE_DIR / "templates")
        }
    }

# ==========================================
# 🏠 PUBLIC ROUTES
# ==========================================

@app.get("/")
async def home(request: Request):
    """
    Landing Page (templates/pages/index.html)
    """
    return templates.TemplateResponse("pages/index.html", {"request": request})

@app.get("/dashboard")
async def dashboard(request: Request):
    """
    Dashboard Page (templates/pages/dashboard.html)
    """
    return templates.TemplateResponse("pages/dashboard.html", {"request": request})

# ==========================================
# 🧩 COMPONENT ROUTES (For Unpoly/Modals)
# ==========================================

@app.get("/api/modal-test")
async def get_modal(request: Request):
    """
    Sidebar 'Open Popup' button yahan hit karega.
    Returns: HTML Fragment (Not full page)
    """
    return templates.TemplateResponse("components/modals/welcome_modal.html", {"request": request})
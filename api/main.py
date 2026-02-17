import sys
import logging
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse

# --- 📂 PATH SETUP ---
BASE_DIR = Path(__file__).resolve().parent 
ROOT_DIR = BASE_DIR.parent                  
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

# --- 🪵 LOGGING ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(name)s | %(levelname)s | %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("LUVIIO-CORE")

# --- 🛠️ IMPORTS ---
try:
    # Existing Resend Mail (No Changes)
    from api.routes.resend_mail import router as resend_router
    
    # ✅ NEW: Database Connection Added
    from api.routes.database import supabase_admin
    
except ImportError:
    # Fallback for local
    from routes.resend_mail import router as resend_router
    from routes.database import supabase_admin

# --- 🚀 APP INIT ---
app = FastAPI(title="LUVIIO Engine", version="4.5.0")

templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

# --- 🔗 ROUTERS ---
app.include_router(resend_router, prefix="/api", tags=["Utility"])
# Auth Router abhi hata hua hai (Clean State)

app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

# --- 🌐 PUBLIC ROUTES ---
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("app/pages/home.html", {"request": request, "active_page": "home"})

@app.get("/waitlist", response_class=HTMLResponse)
async def render_waitlist(request: Request):
    return templates.TemplateResponse("app/pages/waitlist.html", {"request": request})
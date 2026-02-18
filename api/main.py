import sys
import logging
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, EmailStr

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
    # Existing Resend Mail
    from api.routes.resend_mail import router as resend_router
    
    # ✅ Database Connection
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

app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

# --- 📝 SCHEMAS ---
class WaitlistSchema(BaseModel):
    email: EmailStr

# --- 🌐 PUBLIC ROUTES ---

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("app/pages/home.html", {"request": request, "active_page": "home"})

@app.get("/waitlist", response_class=HTMLResponse)
async def render_waitlist(request: Request):
    return templates.TemplateResponse("app/pages/waitlist.html", {"request": request})

# ✅ NEW: Handle Form Submission
@app.post("/waitlist")
async def join_waitlist(payload: WaitlistSchema):
    """
    Receives email from frontend and saves to Supabase 'waitlist' table.
    """
    if not supabase_admin:
        logger.error("❌ DB Connection missing during waitlist signup")
        return JSONResponse(status_code=500, content={"error": "Server error: Database not connected"})

    try:
        email = payload.email.lower()
        logger.info(f"📝 Adding to waitlist: {email}")
        
        # Insert into 'waitlist' table
        data = {"email": email}
        supabase_admin.table("waitlist").insert(data).execute()
        
        return JSONResponse(content={"message": "Successfully joined waitlist! 🚀"})
        
    except Exception as e:
        error_msg = str(e).lower()
        # Handle duplicate emails gracefully
        if "duplicate" in error_msg or "unique constraint" in error_msg:
            return JSONResponse(content={"message": "You are already on the list! ✨"})
            
        logger.error(f"❌ Waitlist Error: {e}")
        return JSONResponse(status_code=500, content={"error": "Could not join waitlist. Try again."})
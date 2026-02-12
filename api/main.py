import os
import sys
from pathlib import Path
from fastapi import FastAPI, Request, Header
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse

# 🛡️ THE PATH FIX (Vercel Compatibility)
# Ye ensure karega ki Vercel pe paths kabhi break na hon
BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

# --- IMPORT EXISTING ROUTERS ---
# Resend mail router ko safe import karte hain
try:
    from routes.resend_mail import router as resend_mail_router
except ImportError:
    resend_mail_router = None

app = FastAPI()

# Mount Static & Templates
# Path object use kar rahe hain taaki Linux/Windows/Vercel sab jagah chale
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

# Include Router if exists
if resend_mail_router:
    app.include_router(resend_mail_router)

# --- PAGE ROUTES ---

@app.get("/", response_class=HTMLResponse)
async def render_home(request: Request, x_up_target: str = Header(None)):
    return templates.TemplateResponse("app/pages/home.html", {
        "request": request,
        "title": "LUVIIO | Verified Markets",
        "active_page": "home",
        # Unpoly logic: Agar header hai toh true pass karo
        "up_fragment": x_up_target is not None
    })

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, x_up_target: str = Header(None)):
    return templates.TemplateResponse("app/auth/login.html", {
        "request": request,
        "title": "Login | LUVIIO",
        "up_fragment": x_up_target is not None,
        # Environment variables pass kar rahe hain (Future proofing)
        "supabase_url": os.environ.get("SUPABASE_URL"),
        "supabase_anon_key": os.environ.get("SUPABASE_ANON_KEY")
    })

@app.get("/signup", response_class=HTMLResponse)
async def signup_page(request: Request, x_up_target: str = Header(None)):
    return templates.TemplateResponse("app/auth/signup.html", {
        "request": request,
        "title": "Create Account | LUVIIO",
        "up_fragment": x_up_target is not None,
        "supabase_url": os.environ.get("SUPABASE_URL"),
        "supabase_anon_key": os.environ.get("SUPABASE_ANON_KEY")
    })

@app.get("/waitlist", response_class=HTMLResponse)
async def render_waitlist(request: Request, x_up_target: str = Header(None)):
    return templates.TemplateResponse("app/pages/waitlist.html", {
        "request": request,
        "title": "Join Waitlist | LUVIIO", 
        "active_page": "home",
        "up_fragment": x_up_target is not None
    })
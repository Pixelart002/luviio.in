import os
import sys
from pathlib import Path
from fastapi import FastAPI, Request, Header
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse

# ----------------------------------------------------------------
# 🛡️ THE VERCEL PATH FIX (Reddit Standard)
# ----------------------------------------------------------------
current_file_path = Path(__file__).resolve()
api_dir = current_file_path.parent 

if str(api_dir) not in sys.path:
    sys.path.insert(0, str(api_dir))

# --- IMPORT ROUTERS ---
# Note: Ensure api/routes/__init__.py exists!
try:
    from routes.resend_mail import router as resend_mail_router
    from routes.auth import router as auth_router
except ImportError as e:
    # Fallback for some Vercel environments
    from api.routes.resend_mail import router as resend_mail_router
    from api.routes.auth import router as auth_router

app = FastAPI()

# 1. Path Setup 
BASE_DIR = api_dir
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

# --- CONNECT ROUTERS ---
app.include_router(resend_mail_router)
app.include_router(auth_router)

# --- PAGE ROUTES (Existing Untouched) ---

@app.get("/", response_class=HTMLResponse)
async def render_home(request: Request, x_up_target: str = Header(None)):
    return templates.TemplateResponse("app/pages/home.html", {
        "request": request,
        "title": "LUVIIO | Verified Markets",
        "active_page": "home",
        "up_fragment": x_up_target is not None
    })

# Login route uses your auth router logic now
@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, x_up_target: str = Header(None)):
    return templates.TemplateResponse("app/auth/login.html", {
        "request": request,
        "title": "Login | LUVIIO",
        "up_fragment": x_up_target is not None,
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
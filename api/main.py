import os
import sys
from pathlib import Path
from fastapi import FastAPI, Request, Header
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse

# ----------------------------------------------------------------
# 🛡️ THE "FINAL BOSS" PATH FIX
# ----------------------------------------------------------------
# Hum absolute path calculate kar rahe hain taaki Vercel confuse na ho
current_file_path = Path(__file__).resolve()
api_dir = current_file_path.parent # /api directory
root_dir = api_dir.parent         # Root directory

# Python ko force karo 'api' folder ke andar dekhne ke liye
if str(api_dir) not in sys.path:
    sys.path.insert(0, str(api_dir))

# --- IMPORT ROUTERS ---
# Try-Except block taaki deployment fail na ho aur logs mein clear error dikhe
try:
    from routes.resend_mail import router as resend_mail_router
    from routes.auth import router as auth_router
except ImportError as e:
    print(f"❌ MODULE ERROR: {e}")
    # Local debugging ke liye fallback agar 'api.' prefix chahiye ho
    try:
        from api.routes.resend_mail import router as resend_mail_router
        from api.routes.auth import router as auth_router
    except ImportError:
        raise e

app = FastAPI()

# --- CONFIG FLAGS ---
CONFIG_FLAGS = {
    "SUPABASE_READY": os.environ.get("SUPABASE_URL") is not None,
    "RESEND_READY": os.environ.get("RESEND_API_KEY") is not None
}

# 1. Path Setup (Absolute paths are safer on Vercel)
BASE_DIR = api_dir
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

# --- CONNECT ROUTERS ---
app.include_router(resend_mail_router)
app.include_router(auth_router)

# --- PAGE ROUTES ---

# 1. Home Page
@app.get("/", response_class=HTMLResponse)
async def render_home(request: Request, x_up_target: str = Header(None)):
    return templates.TemplateResponse("app/pages/home.html", {
        "request": request,
        "title": "LUVIIO | Verified Markets",
        "active_page": "home",
        "up_fragment": x_up_target is not None
    })

# 2. Login Page (Using your new modular macros)
@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, x_up_target: str = Header(None)):
    return templates.TemplateResponse("app/auth/login.html", {
        "request": request,
        "title": "Login | LUVIIO",
        "up_fragment": x_up_target is not None,
        "supabase_url": os.environ.get("SUPABASE_URL"),
        "supabase_anon_key": os.environ.get("SUPABASE_ANON_KEY")
    })

# 3. Signup Page
@app.get("/signup", response_class=HTMLResponse)
async def signup_page(request: Request, x_up_target: str = Header(None)):
    return templates.TemplateResponse("app/auth/signup.html", {
        "request": request,
        "title": "Create Account | LUVIIO",
        "up_fragment": x_up_target is not None,
        "supabase_url": os.environ.get("SUPABASE_URL"),
        "supabase_anon_key": os.environ.get("SUPABASE_ANON_KEY")
    })

# 4. Waitlist Fragment
@app.get("/waitlist", response_class=HTMLResponse)
async def render_waitlist(request: Request, x_up_target: str = Header(None)):
    return templates.TemplateResponse("app/pages/waitlist.html", {
        "request": request,
        "title": "Join Waitlist | LUVIIO", 
        "active_page": "home",
        "up_fragment": x_up_target is not None
    })
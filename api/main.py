import os
import sys
from fastapi import FastAPI, Request, Header
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse

# ----------------------------------------------------------------
# 🔧 ROBUST VERCEL PATH FIX
# ----------------------------------------------------------------
# Ensure the 'api' directory is the first place Python looks for modules
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

# --- IMPORT ROUTERS ---
# Note: Ensure api/routes/auth.py exists as per your file structure
try:
    from routes.resend_mail import router as resend_mail_router
    from routes.auth import router as auth_router
except ImportError as e:
    print(f"❌ Critical Import Error: {e}")
    # This will show up in Vercel logs to tell exactly which file is missing
    raise e

app = FastAPI()

# --- SERVER-SIDE CONFIG FLAGS (For Checking Only) ---
# Ye flags verify karenge ki aapke credentials loaded hain
CONFIG_FLAGS = {
    "SUPABASE_READY": os.environ.get("SUPABASE_URL") is not None,
    "RESEND_READY": os.environ.get("RESEND_API_KEY") is not None,
    "SECRET_READY": os.environ.get("ADMIN_SECRET") is not None
}
print(f"🚀 Server Config Flags: {CONFIG_FLAGS}")

# 1. Path Setup
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 2. Mount Static & Templates
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

# --- CONNECT ROUTERS ---
# Fix: Using the correct imported names
app.include_router(resend_mail_router)
app.include_router(auth_router)

# --- ROUTES ---

# 1. Home Page
@app.get("/", response_class=HTMLResponse)
async def render_home(request: Request, x_up_target: str = Header(None)):
    return templates.TemplateResponse("app/pages/home.html", {
        "request": request,
        "title": "LUVIIO | Verified Markets",
        "active_page": "home",
        "up_fragment": x_up_target is not None
    })

# 2. Login Page (Modular Macros Version)
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
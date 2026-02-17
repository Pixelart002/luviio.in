import os
import sys
from pathlib import Path
from fastapi import FastAPI, Request, Header
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse

# ----------------------------------------------------------------
# 🛡️ THE PATH FIX (Vercel Compatibility)
# ----------------------------------------------------------------
current_file_path = Path(__file__).resolve()
api_dir = current_file_path.parent 

if str(api_dir) not in sys.path:
    sys.path.insert(0, str(api_dir))

# --- IMPORT ONLY EXISTING ROUTERS ---
try:
    # Sirf resend_mail import kar rahe hain kyunki wahi file exist karti hai
    from routes.resend_mail import router as resend_mail_router
except ImportError as e:
    print(f"⚠️ Resend Router missing, check api/routes/resend_mail.py: {e}")
    resend_mail_router = None

app = FastAPI()

# 1. Path Setup
BASE_DIR = api_dir
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

# --- CONNECT EXISTING ROUTERS ---
if resend_mail_router:
    app.include_router(resend_mail_router)

# --- PAGE ROUTES (Directly in main.py) ---

# 1. Home Page
@app.get("/", response_class=HTMLResponse)
async def render_home(request: Request, x_up_target: str = Header(None)):
    return templates.TemplateResponse("app/pages/home.html", {
        "request": request,
        "title": "LUVIIO | Verified Markets",
        "active_page": "home",
        "up_fragment": x_up_target is not None
    })

# 2. Login Page (Path based on Screenshot 10)
@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, x_up_target: str = Header(None)):
    return templates.TemplateResponse("app/auth/login.html", {
        "request": request,
        "title": "Login | LUVIIO",
        "up_fragment": x_up_target is not None,
        # 🔒 Macros ke liye Env Variables yahan se pass honge
        "supabase_url": os.environ.get("SUPABASE_URL"),
        "supabase_anon_key": os.environ.get("SUPABASE_ANON_KEY")
    })

# 3. Signup Page (Path based on Screenshot 10)
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
import os
import sys
from pathlib import Path
from fastapi import FastAPI, Request, Header
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, RedirectResponse

# 🛡️ THE ULTIMATE PATH FIX (Vercel Compatibility)
# Parent of 'api' ko path mein daal rahe hain taaki absolute imports fail na hon
BASE_DIR = Path(__file__).resolve().parent 
ROOT_DIR = BASE_DIR.parent                  
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

# --- MODULAR IMPORTS ---
# Ensure karo ki api/middleware/__init__.py exist karta hai
try:
    from api.middleware.cors_setup import setup_cors
    from api.middleware.domain_guard import AuthDomainGuard
except ImportError:
    # Fallback for local dev environments
    from middleware.cors_setup import setup_cors
    from middleware.domain_guard import AuthDomainGuard

app = FastAPI()

# --- 1. SETUP CORS (MANDATORY FIRST) ---
# Unpoly AJAX requests aur Preflight checks ke liye rasta saaf karta hai
setup_cors(app)

# --- 2. REGISTER DOMAIN GUARD ---
# Ye domain isolation aur unauthorized path protection handle karta hai
app.add_middleware(AuthDomainGuard)

# Mount Static & Templates
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

# --- 3. ERROR HANDLERS ---

@app.get("/error", response_class=HTMLResponse)
async def error_page(request: Request):
    """Serve the professional 404/Access Denied page."""
    # Context pass karna MANDATORY hai taaki 500 error na aaye
    return templates.TemplateResponse("app/err/404.html", {
        "request": request,
        "title": "404 - Access Denied | LUVIIO"
    })

@app.exception_handler(404)
async def custom_404_handler(request: Request, __):
    """Redirect all actual 404s to our custom security error page."""
    return RedirectResponse(url="/error")

# --- 4. AUTH ROUTES (Accessible via auth.luviio.in) ---

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, x_up_target: str = Header(None)):
    return templates.TemplateResponse("app/auth/login.html", {
        "request": request,
        "title": "Login | LUVIIO",
        "up_fragment": x_up_target is not None,
        "supabase_url": os.environ.get("SUPABASE_URL"),
        "supabase_key": os.environ.get("SUPABASE_KEY") or os.environ.get("SUPABASE_ANON_KEY")
    })

@app.get("/signup", response_class=HTMLResponse)
async def signup_page(request: Request, x_up_target: str = Header(None)):
    return templates.TemplateResponse("app/auth/signup.html", {
        "request": request,
        "title": "Create Account | LUVIIO",
        "up_fragment": x_up_target is not None,
        "supabase_url": os.environ.get("SUPABASE_URL"),
        "supabase_key": os.environ.get("SUPABASE_KEY") or os.environ.get("SUPABASE_ANON_KEY")
    })

# --- 5. MAIN PAGE ROUTES (Accessible via luviio.in) ---

@app.get("/", response_class=HTMLResponse)
async def render_home(request: Request, x_up_target: str = Header(None)):
    return templates.TemplateResponse("app/pages/home.html", {
        "request": request,
        "title": "LUVIIO | Verified Markets",
        "active_page": "home",
        "up_fragment": x_up_target is not None
    })

@app.get("/waitlist", response_class=HTMLResponse)
async def render_waitlist(request: Request, x_up_target: str = Header(None)):
    return templates.TemplateResponse("app/pages/waitlist.html", {
        "request": request,
        "title": "Join Waitlist | LUVIIO", 
        "up_fragment": x_up_target is not None
    })
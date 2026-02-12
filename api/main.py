import os
import sys
from pathlib import Path
from fastapi import FastAPI, Request, Header
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, RedirectResponse

# 🛡️ THE PATH FIX (Vercel Compatibility)
# Parent of 'api' ko path mein daal rahe hain taaki package imports fail na hon
BASE_DIR = Path(__file__).resolve().parent 
ROOT_DIR = BASE_DIR.parent                  
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

# Absolute package import for Middleware
try:
    from api.middleware.domain_guard import AuthDomainGuard
except ImportError:
    # Fallback for local dev environments
    from middleware.domain_guard import AuthDomainGuard

app = FastAPI()

# --- REGISTER MIDDLEWARE ---
# Ye domain isolation handle karega aur unauthorized access ko /error par bhejega
app.add_middleware(AuthDomainGuard)

# Mount Static & Templates
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

# --- ERROR HANDLERS ---

@app.get("/error", response_class=HTMLResponse)
async def error_page(request: Request):
    # Context pass karna MANDATORY hai taaki 500 error na aaye
    return templates.TemplateResponse("app/err/404.html", {
        "request": request,
        "title": "404 - Access Denied | LUVIIO"
    })

@app.exception_handler(404)
async def custom_404_handler(request: Request, __):
    # Asli 404 hone par bhi user hamare custom error page par jayega
    return RedirectResponse(url="/error")

# --- PAGE ROUTES ---

@app.get("/", response_class=HTMLResponse)
async def render_home(request: Request, x_up_target: str = Header(None)):
    return templates.TemplateResponse("app/pages/home.html", {
        "request": request,
        "title": "LUVIIO | Verified Markets",
        "up_fragment": x_up_target is not None
    })

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, x_up_target: str = Header(None)):
    return templates.TemplateResponse("app/auth/login.html", {
        "request": request,
        "title": "Login | LUVIIO",
        "up_fragment": x_up_target is not None,
        "supabase_url": os.environ.get("SUPABASE_URL"),
        "supabase_key": os.environ.get("SUPABASE_KEY") # Env var updated
    })

@app.get("/signup", response_class=HTMLResponse)
async def signup_page(request: Request, x_up_target: str = Header(None)):
    return templates.TemplateResponse("app/auth/signup.html", {
        "request": request,
        "title": "Create Account | LUVIIO",
        "up_fragment": x_up_target is not None,
        "supabase_url": os.environ.get("SUPABASE_URL"),
        "supabase_key": os.environ.get("SUPABASE_KEY")
    })

@app.get("/waitlist", response_class=HTMLResponse)
async def render_waitlist(request: Request, x_up_target: str = Header(None)):
    return templates.TemplateResponse("app/pages/waitlist.html", {
        "request": request,
        "title": "Join Waitlist | LUVIIO", 
        "up_fragment": x_up_target is not None
    })
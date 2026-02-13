import os
import sys
from pathlib import Path
from fastapi import FastAPI, Request, Header, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, RedirectResponse

# 🛡️ THE ULTIMATE PATH FIX (Vercel Compatibility)
BASE_DIR = Path(__file__).resolve().parent 
ROOT_DIR = BASE_DIR.parent                  
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

app = FastAPI()

# --- 1. MOUNT STATIC & TEMPLATES ---
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

# --- 2. LOG SILENCERS ---
# Inhe rehne dena taaki browser ki automatic requests se logs na bharein

@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return Response(status_code=204)

@app.get("/robots.txt", include_in_schema=False)
async def robots():
    return Response(content="User-agent: *\nDisallow:", media_type="text/plain")

# --- 3. ERROR HANDLERS ---

@app.get("/error", response_class=HTMLResponse)
async def error_page(request: Request):
    return templates.TemplateResponse("app/err/404.html", {
        "request": request,
        "title": "404 - Not Found | LUVIIO"
    })

@app.exception_handler(404)
async def custom_404_handler(request: Request, __):
    return RedirectResponse(url="/error")

# --- 4. AUTH ROUTES ---
# Ab ye routes har domain par available honge bina redirection ke

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

# --- 5. MAIN PAGE ROUTES ---

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
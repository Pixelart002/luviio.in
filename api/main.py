import os
import sys
import logging
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

# --- 🪵 LOGGING SETUP ---
# Production mein har action track karne ke liye
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("LUVIIO-APP")

# --- 📂 ROUTE IMPORTS ---
try:
    from api.routes.resend_mail import router as resend_router
except ImportError:
    from routes.resend_mail import router as resend_router

app = FastAPI()

# --- 🛠️ CONNECT ROUTERS ---
# Resend email logic ko app mein jod rahe hain
app.include_router(resend_router, prefix="/api", tags=["Auth"])

app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

# --- 2. LOG SILENCERS (Silent but Logged) ---

@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    logger.debug("Favicon requested - returning 204")
    return Response(status_code=204)

@app.get("/robots.txt", include_in_schema=False)
async def robots():
    logger.info("Bot/Crawler accessed robots.txt")
    return Response(content="User-agent: *\nDisallow:", media_type="text/plain")

# --- 3. ERROR HANDLERS ---

@app.get("/error", response_class=HTMLResponse)
async def error_page(request: Request):
    logger.error(f"Error page triggered for IP: {request.client.host}")
    return templates.TemplateResponse("app/err/404.html", {
        "request": request,
        "title": "404 - Not Found | LUVIIO"
    })

@app.exception_handler(404)
async def custom_404_handler(request: Request, __):
    logger.warning(f"404 Not Found: {request.url.path} - Redirecting to /error")
    return RedirectResponse(url="/error")

# --- 4. AUTH ROUTES (Using new SB_URL / SB_KEY) ---

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, x_up_target: str = Header(None)):
    logger.info(f"Rendering Login Page | Unpoly: {x_up_target is not None}")
    return templates.TemplateResponse("app/auth/login.html", {
        "request": request,
        "title": "Login | LUVIIO",
        "up_fragment": x_up_target is not None,
        "supabase_url": os.environ.get("SB_URL"), # Upgraded Var
        "supabase_key": os.environ.get("SB_KEY")   # Upgraded Var
    })

@app.get("/signup", response_class=HTMLResponse)
async def signup_page(request: Request, x_up_target: str = Header(None)):
    logger.info(f"Rendering Signup Page")
    return templates.TemplateResponse("app/auth/signup.html", {
        "request": request,
        "title": "Create Account | LUVIIO",
        "up_fragment": x_up_target is not None,
        "supabase_url": os.environ.get("SB_URL"),
        "supabase_key": os.environ.get("SB_KEY")
    })

# --- 5. MAIN PAGE ROUTES ---

@app.get("/", response_class=HTMLResponse)
async def render_home(request: Request, x_up_target: str = Header(None)):
    logger.info(f"Home page access from IP: {request.client.host}")
    return templates.TemplateResponse("app/pages/home.html", {
        "request": request,
        "title": "LUVIIO | Verified Markets",
        "active_page": "home",
        "up_fragment": x_up_target is not None
    })

@app.get("/waitlist", response_class=HTMLResponse)
async def render_waitlist(request: Request, x_up_target: str = Header(None)):
    logger.info("Waitlist page rendered")
    return templates.TemplateResponse("app/pages/waitlist.html", {
        "request": request,
        "title": "Join Waitlist | LUVIIO", 
        "up_fragment": x_up_target is not None,
        "supabase_url": os.environ.get("SB_URL"),
        "supabase_key": os.environ.get("SB_KEY")
    })
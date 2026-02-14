import os
import sys
import logging
from pathlib import Path
from fastapi import FastAPI, Request, Header, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.middleware.base import BaseHTTPMiddleware

# 🛡️ THE ULTIMATE PATH FIX (Vercel Compatibility)
BASE_DIR = Path(__file__).resolve().parent 
ROOT_DIR = BASE_DIR.parent                  
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

# --- 🪵 LOGGING SETUP ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("LUVIIO-APP")

# --- ✅ ENVIRONMENT VARIABLE VALIDATION ---
REQUIRED_ENV_VARS = ["SB_URL", "SB_KEY", "SB_SERVICE_ROLE_KEY"]
missing_vars = [var for var in REQUIRED_ENV_VARS if not os.environ.get(var)]

if missing_vars:
    logger.warning(f"⚠️  WARNING: Missing environment variables: {', '.join(missing_vars)}")
    logger.warning("App will continue but OAuth/Auth features may not work properly")
    logger.warning("Add these to your Vercel project settings → Environment Variables")
else:
    logger.info("✅ All required Supabase environment variables configured")

# --- 📂 ROUTE IMPORTS ---
try:
    from api.routes.resend_mail import router as resend_router
    from api.routes.auth import router as auth_router # Updated Path
except ImportError:
    from routes.resend_mail import router as resend_router
    from routes.auth import router as auth_router

app = FastAPI()

# --- 🛡️ DOMAIN GUARD: Force Non-WWW (Industry Standard) ---
class ForceNonWWWMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        host = request.headers.get("host", "")
        if host.startswith("www.luviio.in"):
            # Strictly redirecting www to root domain
            url = str(request.url).replace("www.", "", 1)
            return RedirectResponse(url=url, status_code=301)
        return await call_next(request)

app.add_middleware(ForceNonWWWMiddleware)

# --- 🛠️ CONNECT ROUTERS ---
app.include_router(resend_router, prefix="/api", tags=["Auth"])
app.include_router(auth_router, prefix="/api", tags=["Auth-Flow"]) # New Router Connected

app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

# --- 2. LOG SILENCERS ---

@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return Response(status_code=204)

@app.get("/robots.txt", include_in_schema=False)
async def robots():
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
    return RedirectResponse(url="/error")

# --- 4. AUTH ROUTES ---

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, x_up_target: str = Header(None)):
    logger.info("Rendering Login Page")
    return templates.TemplateResponse("app/auth/login.html", {
        "request": request,
        "title": "Login | LUVIIO",
        "up_fragment": x_up_target is not None,
        "supabase_url": os.environ.get("SB_URL"),
        "supabase_key": os.environ.get("SB_KEY")
    })

@app.get("/signup", response_class=HTMLResponse)
async def signup_page(request: Request, x_up_target: str = Header(None)):
    logger.info("Signup page accessed")
    return templates.TemplateResponse("app/auth/signup.html", {
        "request": request,
        "title": "Create Account | LUVIIO",
        "up_fragment": x_up_target is not None,
        "supabase_url": os.environ.get("SB_URL"),
        "supabase_key": os.environ.get("SB_KEY")
    })

@app.get("/onboarding", response_class=HTMLResponse)
async def onboarding_page(request: Request):
    logger.info("Onboarding page rendered")
    return templates.TemplateResponse("app/auth/onboarding.html", {
        "request": request,
        "title": "Setup Profile | LUVIIO",
        "supabase_url": os.environ.get("SB_URL"),
        "supabase_key": os.environ.get("SB_KEY")
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
        "up_fragment": x_up_target is not None,
        "supabase_url": os.environ.get("SB_URL"),
        "supabase_key": os.environ.get("SB_KEY")
    })

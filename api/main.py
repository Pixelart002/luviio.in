import os
import sys
import logging
from pathlib import Path
from fastapi import FastAPI, Request, Header, Response, Depends, status, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

# 🛡️ THE ULTIMATE PATH FIX (Vercel Compatibility)
BASE_DIR = Path(__file__).resolve().parent 
ROOT_DIR = BASE_DIR.parent                  
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

# --- 🪵 PRODUCTION LOGGING SETUP ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(name)s | %(levelname)s | %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("LUVIIO-CORE")

# --- 📂 CLEAN ABSOLUTE IMPORTS ---
try:
    from api.routes.resend_mail import router as resend_router
    from api.routes.auth import router as auth_router 
    from api.utils.deps import get_current_user, require_onboarded
    logger.info("✅ Core modules imported using absolute paths")
except ImportError as e:
    logger.error(f"⚠️ Import fallback triggered: {str(e)}")
    from routes.resend_mail import router as resend_router
    from routes.auth import router as auth_router
    from utils.deps import get_current_user, require_onboarded

app = FastAPI(
    title="LUVIIO Engine", 
    version="4.0.0", # Major Upgrade: Unified Domain
    docs_url="/api/docs", 
    openapi_url="/api/openapi.json"
)

# --- 🛡️ MIDDLEWARES SETUP ---

# 1. CORS (Unified Domain Security)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://luviio.in", "http://localhost:3000"], 
    allow_credentials=True, 
    allow_methods=["*"],
    allow_headers=["*"],
)

# 2. Session Middleware (OAuth states)
app.add_middleware(
    SessionMiddleware, 
    secret_key=os.environ.get("SESSION_SECRET", "prod-secret-key-v4"),
    session_cookie="luviio_session",
    same_site="lax",
    https_only=True
)

# 3. 🚫 THE SUBDOMAIN PURGE (Strict Fix)
class UnifiedDomainMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        host = request.headers.get("host", "").lower()
        path = request.url.path
        
        # A. Kisi bhi tarah ka subdomain (dashboard., www., etc.) detect hone par root domain par pheko
        if host != "luviio.in" and not any(h in host for h in ["localhost", "127.0.0.1", ".vercel.app"]):
            logger.warning(f"🚨 Unauthorized host detected: {host}. Purging to luviio.in")
            return RedirectResponse(
                url=f"https://luviio.in{path}", 
                status_code=status.HTTP_308_PERMANENT_REDIRECT
            )

        return await call_next(request)

app.add_middleware(UnifiedDomainMiddleware)

# --- 🛠️ CONNECT ROUTERS ---
app.include_router(resend_router, prefix="/api", tags=["Utility"])
app.include_router(auth_router, prefix="/api/auth", tags=["Auth-Flow"])

app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

# --- 📄 ERROR HANDLERS ---
@app.exception_handler(404)
async def custom_404_handler(request: Request, __):
    logger.warning(f"🚩 404 Attempt on: {request.url.path}")
    return templates.TemplateResponse("app/err/404.html", {"request": request, "title": "404 - Not Found"}, status_code=404)

# --- 🔐 UNIFIED PROTECTED ROUTES ---

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    # Check session directly via cookie
    if request.cookies.get("access_token"):
        logger.info("✅ Session active, bypassing login UI")
        return RedirectResponse(url="/dashboard")
    return templates.TemplateResponse("app/auth/login.html", {"request": request, "title": "Login | LUVIIO"})

@app.get("/signup", response_class=HTMLResponse)
async def signup_page(request: Request):
    if request.cookies.get("access_token"):
        return RedirectResponse(url="/dashboard")
    return templates.TemplateResponse("app/auth/signup.html", {"request": request, "title": "Sign Up | LUVIIO"})

@app.get("/onboarding", response_class=HTMLResponse)
async def onboarding_page(request: Request, user: dict = Depends(get_current_user)):
    logger.info(f"👤 Onboarding check for: {user['email']}")
    if user.get("onboarded"):
        return RedirectResponse(url="/dashboard")
    return templates.TemplateResponse("app/auth/onboarding.html", {"request": request, "user": user})

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page(request: Request):
    """
    Main Protected Application Entry Point.
    Handles redirection internally to avoid JSON error screens.
    """
    try:
        # Dependency verification
        user = await require_onboarded(await get_current_user(request))
        logger.info(f"📊 Dashboard authenticated for: {user['email']}")
        return templates.TemplateResponse("app/pages/home.html", {"request": request, "user": user})
    except HTTPException as e:
        # Unified redirection logic based on exception detail
        if e.detail == "onboarding_required":
            logger.warning("🔄 Redirecting to Onboarding flow")
            return RedirectResponse(url="/onboarding")
        return RedirectResponse(url="/login")

# --- 🌐 PUBLIC ROUTES ---

@app.get("/", response_class=HTMLResponse)
async def render_home(request: Request):
    logger.info("🏠 Rendering Landing Page")
    return templates.TemplateResponse("app/pages/home.html", {"request": request, "active_page": "home"})

@app.get("/waitlist", response_class=HTMLResponse)
async def render_waitlist(request: Request):
    return templates.TemplateResponse("app/pages/waitlist.html", {"request": request})
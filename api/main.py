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

# --- 📂 PATH FIX & IMPORTS SETUP ---
# Absolute path resolution to fix Vercel import errors
BASE_DIR = Path(__file__).resolve().parent 
ROOT_DIR = BASE_DIR.parent                  
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

# --- 🪵 LOGGING ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(name)s | %(levelname)s | %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("LUVIIO-CORE")

# --- 🛠️ IMPORTS ---
try:
    from api.routes.resend_mail import router as resend_router
    from api.routes.auth import router as auth_router 
    from api.utils.deps import get_current_user, require_onboarded
    logger.info("✅ Core modules imported successfully")
except ImportError as e:
    logger.error(f"⚠️ Import fallback triggered: {str(e)}")
    from routes.resend_mail import router as resend_router
    from routes.auth import router as auth_router
    from utils.deps import get_current_user, require_onboarded

# --- 🚀 APP INIT ---
app = FastAPI(
    title="LUVIIO Engine", 
    version="4.1.0", 
    docs_url="/api/docs", 
    openapi_url="/api/openapi.json"
)

# ==========================================
# 🛡️ MIDDLEWARES (Security & Routing)
# ==========================================

# 1. Security Headers (Best Practice for Cookies)
class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response

app.add_middleware(SecurityHeadersMiddleware)

# 2. CORS (Unified Domain)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://luviio.in", "http://localhost:3000"], 
    allow_credentials=True, 
    allow_methods=["*"],
    allow_headers=["*"],
)

# 3. Session Middleware (Required for OAuth State)
app.add_middleware(
    SessionMiddleware, 
    secret_key=os.environ.get("SESSION_SECRET", "prod-secret-key-v4"),
    session_cookie="luviio_session",
    same_site="lax",
    https_only=True
)

# 4. 🚫 THE SUBDOMAIN PURGE (Strict Fix)
class UnifiedDomainMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        host = request.headers.get("host", "").lower()
        path = request.url.path
        
        # Development bypass
        is_dev = any(h in host for h in ["localhost", "127.0.0.1", ".vercel.app"])
        
        # A. Force redirect to root domain if not on luviio.in (and not dev)
        if host != "luviio.in" and not is_dev:
            logger.warning(f"🚨 Unauthorized host: {host}. Purging to luviio.in")
            return RedirectResponse(
                url=f"https://luviio.in{path}", 
                status_code=status.HTTP_308_PERMANENT_REDIRECT
            )

        # B. Force Non-WWW (e.g. www.luviio.in -> luviio.in)
        if host.startswith("www."):
            url = str(request.url).replace("www.", "", 1)
            return RedirectResponse(url=url, status_code=status.HTTP_301_MOVED_PERMANENTLY)

        return await call_next(request)

app.add_middleware(UnifiedDomainMiddleware)

# --- 🔗 ROUTERS ---
app.include_router(resend_router, prefix="/api", tags=["Utility"])
app.include_router(auth_router, prefix="/api/auth", tags=["Auth-Flow"])

app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

# --- 📄 EXCEPTION HANDLERS ---
@app.exception_handler(404)
async def custom_404_handler(request: Request, __):
    logger.warning(f"🚩 404 Attempt on: {request.url.path}")
    return templates.TemplateResponse("app/err/404.html", {"request": request, "title": "404 - Not Found"}, status_code=404)

# ==========================================
# 🔐 UNIFIED PROTECTED ROUTES
# ==========================================

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """
    Login Page. Skips UI if session cookie exists.
    """
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
        
        # 🔥 UPDATE: Pointing to dashboard.html strictly
        return templates.TemplateResponse("app/pages/dashboard.html", {"request": request, "user": user})
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
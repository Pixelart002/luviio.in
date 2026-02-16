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
    # Database import for profile fetching
    from api.routes.database import supabase_admin
    logger.info("✅ Core modules imported successfully")
except ImportError as e:
    logger.error(f"⚠️ Import fallback triggered: {str(e)}")
    from routes.resend_mail import router as resend_router
    from routes.auth import router as auth_router
    from utils.deps import get_current_user, require_onboarded
    from routes.database import supabase_admin

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

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response

app.add_middleware(SecurityHeadersMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://luviio.in", "http://localhost:3000"], 
    allow_credentials=True, 
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(
    SessionMiddleware, 
    secret_key=os.environ.get("SESSION_SECRET", "prod-secret-key-v4"),
    session_cookie="luviio_session",
    same_site="lax",
    https_only=True
)

class UnifiedDomainMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        host = request.headers.get("host", "").lower()
        path = request.url.path
        is_dev = any(h in host for h in ["localhost", "127.0.0.1", ".vercel.app"])
        if host != "luviio.in" and not is_dev:
            logger.warning(f"🚨 Unauthorized host: {host}. Purging to luviio.in")
            return RedirectResponse(
                url=f"https://luviio.in{path}", 
                status_code=status.HTTP_308_PERMANENT_REDIRECT
            )
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
    if request.cookies.get("access_token"):
        return RedirectResponse(url="/dashboard")
    return templates.TemplateResponse("app/auth/login.html", {"request": request, "title": "Login | LUVIIO"})

@app.get("/signup", response_class=HTMLResponse)
async def signup_page(request: Request):
    if request.cookies.get("access_token"):
        return RedirectResponse(url="/dashboard")
    return templates.TemplateResponse("app/auth/signup.html", {"request": request, "title": "Sign Up | LUVIIO"})

@app.get("/onboarding", response_class=HTMLResponse)
async def onboarding_page(request: Request, user: dict = Depends(get_current_user)):
    if user.get("onboarded"):
        return RedirectResponse(url="/dashboard")
    return templates.TemplateResponse("app/auth/onboarding.html", {"request": request, "user": user})

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page(request: Request):
    """
    Main Protected Application Entry Point.
    🔥 ULTRA UPGRADE: Fetches 'profiles' table data to show real Name & Role.
    """
    try:
        # 1. Identity Verification
        user_auth = await require_onboarded(await get_current_user(request))
        
        # 2. Fetch Onboarding Details (Name, Role) from Supabase Profiles
        profile_query = supabase_admin.table("profiles").select("*").eq("id", user_auth["id"]).execute()
        
        # Default context if profile fetch fails or is partial
        full_name = "User"
        role = "member"
        
        if profile_query.data:
            profile = profile_query.data[0]
            full_name = profile.get("full_name", "User")
            role = profile.get("role", "member")
        
        # 3. Final User Context for Jinja2
        user_context = {
            "id": user_auth["id"],
            "email": user_auth["email"],
            "full_name": full_name,
            "role": role
        }

        logger.info(f"📊 Dashboard authenticated for: {user_context['full_name']}")
        return templates.TemplateResponse("app/pages/dashboard.html", {
            "request": request, 
            "user": user_context # Pass merged data
        })
    except HTTPException as e:
        if e.detail == "onboarding_required":
            return RedirectResponse(url="/onboarding")
        response = RedirectResponse(url="/login")
        response.delete_cookie("access_token", path="/")
        return response

# --- 🌐 PUBLIC ROUTES ---

@app.get("/", response_class=HTMLResponse)
async def render_home(request: Request):
    return templates.TemplateResponse("app/pages/home.html", {"request": request, "active_page": "home"})

@app.get("/waitlist", response_class=HTMLResponse)
async def render_waitlist(request: Request):
    return templates.TemplateResponse("app/pages/waitlist.html", {"request": request})
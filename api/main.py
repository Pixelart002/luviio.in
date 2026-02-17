import os
import sys
import logging
from pathlib import Path
from fastapi import FastAPI, Request, Response, Depends, status, HTTPException
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
    from api.routes.database import supabase_admin
    logger.info("✅ Core modules imported successfully")
except ImportError as e:
    logger.error(f"⚠️ Import fallback triggered: {str(e)}")
    # Fallback for local/different structure
    from routes.resend_mail import router as resend_router
    from routes.auth import router as auth_router
    from utils.deps import get_current_user, require_onboarded
    from routes.database import supabase_admin

# --- 🚀 APP INIT ---
app = FastAPI(
    title="LUVIIO Engine", 
    version="4.5.0", 
    docs_url="/api/docs", 
    openapi_url="/api/openapi.json"
)

# Template Setup
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

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

# --- 📄 EXCEPTION HANDLERS ---
@app.exception_handler(404)
async def custom_404_handler(request: Request, __):
    logger.warning(f"🚩 404 Attempt on: {request.url.path}")
    return templates.TemplateResponse("app/err/404.html", {"request": request, "title": "404 - Not Found"}, status_code=404)

# ==========================================
# 🔐 PROTECTED APPLICATION ROUTES
# ==========================================

@app.get("/onboarding", response_class=HTMLResponse)
async def onboarding_page(request: Request, user: dict = Depends(get_current_user)):
    """
    Onboarding Form: Only for users where onboarded=False.
    """
    if user.get("onboarded"):
        return RedirectResponse(url="/dashboard", status_code=303)
    
    logger.info(f"📄 Rendering Onboarding for {user['email']}")
    return templates.TemplateResponse("app/auth/onboarding.html", {"request": request, "user": user})

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page(request: Request):
    """
    ELITE PROTECTED ROUTE:
    1. Authenticates User
    2. Validates Onboarding
    3. Fetches Profile Data (Name/Role)
    4. Handles Unpoly Location Headers
    """
    try:
        # Step A: Security Guards (Nested Dependency Logic)
        user_auth = await require_onboarded(await get_current_user(request))
        
        # Step B: Fetch Profile Data from 'profiles' table (Elite Sync)
        profile_res = supabase_admin.table("profiles").select("full_name, role").eq("id", user_auth["id"]).single().execute()
        
        profile = profile_res.data if profile_res.data else {}
        
        user_context = {
            "email": user_auth["email"],
            "full_name": profile.get("full_name", "Valued Member"),
            "role": profile.get("role", "member"),
            "id": user_auth["id"]
        }

        logger.info(f"🚀 [DASHBOARD] Access granted: {user_context['full_name']} ({user_context['role']})")
        
        return templates.TemplateResponse("app/pages/dashboard.html", {
            "request": request,
            "user": user_context
        })

    except HTTPException as e:
        # 🔥 UNPOLY / HTMX REDIRECT LOGIC
        if e.detail == "onboarding_required":
            logger.info("↪️ Redirecting to /onboarding (Status: 307)")
            res = RedirectResponse(url="/onboarding", status_code=status.HTTP_307_TEMPORARY_REDIRECT)
            res.headers["X-Up-Location"] = "/onboarding" # Unpoly specific header
            return res
            
        # Standard Unauthorized Cleanup
        logger.warning(f"🚫 [AUTH-FAIL] Redirecting to /login. Reason: {e.detail}")
        res = RedirectResponse(url="/login", status_code=303)
        res.headers["X-Up-Location"] = "/login"
        res.delete_cookie("access_token", path="/")
        res.delete_cookie("session_id", path="/")
        return res

# ==========================================
# 🌐 PUBLIC & AUTH ROUTES
# ==========================================

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    if request.cookies.get("access_token"):
        return RedirectResponse(url="/dashboard", status_code=303)
    return templates.TemplateResponse("app/auth/login.html", {"request": request, "title": "Login | LUVIIO"})

@app.get("/signup", response_class=HTMLResponse)
async def signup_page(request: Request):
    if request.cookies.get("access_token"):
        return RedirectResponse(url="/dashboard", status_code=303)
    return templates.TemplateResponse("app/auth/signup.html", {"request": request, "title": "Sign Up | LUVIIO"})

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("app/pages/home.html", {"request": request, "active_page": "home"})

@app.get("/waitlist", response_class=HTMLResponse)
async def render_waitlist(request: Request):
    return templates.TemplateResponse("app/pages/waitlist.html", {"request": request})
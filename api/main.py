import os
import logging
from fastapi import FastAPI, Request, Response
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from api.routes.auth import router as auth_router

# Configure Logger
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("LUVIIO-CORE")

app = FastAPI(
    title="LUVIIO Enterprise",
    description="Secure, Scalable Auth & App Engine",
    version="2.0.0"
)

# --- Security & Optimization Middleware ---

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response

app.add_middleware(SecurityHeadersMiddleware)

# Session Middleware (Encrypted state for PKCE)
app.add_middleware(
    SessionMiddleware,
    secret_key=os.environ.get("SESSION_SECRET", "luviio-enterprise-fallback-secret-key-32-chars"),
    session_cookie="luviio_state",
    same_site="lax",
    https_only=True,
    max_age=1800 # 30 minutes state TTL
)

# --- Routing ---

app.include_router(auth_router, prefix="/api/auth", tags=["Authentication"])

# Static Assets
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

# --- Page Handlers ---

@app.get("/")
async def index(request: Request):
    """Public landing page."""
    is_auth = request.cookies.get("sb-access-token") is not None
    return templates.TemplateResponse("app/pages/home.html", {
        "request": request,
        "user_logged_in": is_auth
    })

@app.get("/login")
async def login_page(request: Request):
    """Authentication entry point."""
    if request.cookies.get("sb-access-token"):
        return RedirectResponse(url="/dashboard")
    return templates.TemplateResponse("app/auth/login.html", {"request": request})

@app.get("/dashboard")
async def dashboard_page(request: Request):
    """Protected user dashboard."""
    if not request.cookies.get("sb-access-token") and not request.cookies.get("sb-refresh-token"):
        return RedirectResponse(url="/login?error=auth_required")
    
    return templates.TemplateResponse("app/pages/home.html", {
        "request": request, 
        "user_logged_in": True,
        "is_dashboard": True
    })

# Global Exception Handling
@app.exception_handler(404)
async def custom_404_handler(request: Request, __):
    return templates.TemplateResponse("app/err/404.html", {"request": request}, status_code=404)

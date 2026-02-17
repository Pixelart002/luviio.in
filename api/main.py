import sys
import logging
from pathlib import Path
from fastapi import FastAPI, Request, status
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, RedirectResponse

# --- 📂 PATH SETUP ---
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
    from api.utils.cookies import CookieConfig 
except ImportError:
    # Fallback
    from routes.resend_mail import router as resend_router
    from routes.auth import router as auth_router
    from utils.cookies import CookieConfig

# --- 🚀 APP INIT ---
app = FastAPI(
    title="LUVIIO Engine", 
    version="4.5.0", 
    docs_url="/api/docs", 
    openapi_url="/api/openapi.json"
)

templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

# --- 🔗 ROUTERS ---
app.include_router(resend_router, prefix="/api", tags=["Utility"])
app.include_router(auth_router, prefix="/api/auth", tags=["Auth-Flow"])

app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

# --- 📄 EXCEPTION HANDLERS ---
@app.exception_handler(404)
async def custom_404_handler(request: Request, __):
    return templates.TemplateResponse("app/err/404.html", {"request": request, "title": "404 - Not Found"}, status_code=404)

# ==========================================
# 🌐 PUBLIC ROUTES
# ==========================================

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("app/pages/home.html", {"request": request, "active_page": "home"})

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    # Agar token hai to seedha home bhej do
    if request.cookies.get(CookieConfig.ACCESS_KEY):
        return RedirectResponse(url="/", status_code=303)
    return templates.TemplateResponse("app/auth/login.html", {"request": request, "title": "Login"})

@app.get("/signup", response_class=HTMLResponse)
async def signup_page(request: Request):
    if request.cookies.get(CookieConfig.ACCESS_KEY):
        return RedirectResponse(url="/", status_code=303)
    return templates.TemplateResponse("app/auth/signup.html", {"request": request, "title": "Sign Up"})

@app.get("/waitlist", response_class=HTMLResponse)
async def render_waitlist(request: Request):
    return templates.TemplateResponse("app/pages/waitlist.html", {"request": request})

@app.get("/onboarding", response_class=HTMLResponse)
async def onboarding_page(request: Request):
    # Sirf logged-in users ke liye
    if not request.cookies.get(CookieConfig.ACCESS_KEY):
        return RedirectResponse(url="/login", status_code=303)
    return templates.TemplateResponse("app/auth/onboarding.html", {"request": request})
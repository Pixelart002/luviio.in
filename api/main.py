import os
from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from api.routes.auth import router as auth_router

app = FastAPI(title="LUVIIO")

# --- Middleware ---

# 1. Session Middleware (Crucial for PKCE)
app.add_middleware(
    SessionMiddleware,
    secret_key=os.environ.get("SESSION_SECRET", "luviio-super-secret-key-change-this"),
    session_cookie="luviio_session",
    same_site="lax",
    https_only=True, # Vercel handles HTTPS
    max_age=3600 # 1 hour is enough for the flow
)

# 2. Force Non-WWW (Optional but good for consistency)
class ForceNonWWWMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        host = request.headers.get("host", "")
        if host.startswith("www."):
            url = str(request.url).replace("www.", "", 1)
            return RedirectResponse(url=url, status_code=301)
        return await call_next(request)

app.add_middleware(ForceNonWWWMiddleware)

# --- Routes ---

app.include_router(auth_router, prefix="/api/auth", tags=["Authentication"])

# Static and Template Paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

@app.get("/")
async def home(request: Request):
    return templates.TemplateResponse("app/pages/home.html", {"request": request})

@app.get("/login")
async def login_page(request: Request):
    return templates.TemplateResponse("app/auth/login.html", {"request": request})

@app.get("/dashboard")
async def dashboard(request: Request):
    # Basic check - in production use a dependency
    if not request.cookies.get("sb-access-token"):
        return RedirectResponse(url="/login")
    return templates.TemplateResponse("app/pages/home.html", {"request": request, "user_logged_in": True})

# Handle 404
@app.exception_handler(404)
async def not_found_exception_handler(request: Request, exc):
    return templates.TemplateResponse("app/err/404.html", {"request": request}, status_code=404)

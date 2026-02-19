import os
import logging
import uuid
from datetime import datetime
from typing import Optional, List, Dict, Any
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.middleware.base import BaseHTTPMiddleware

# ------------------ Logging Configuration ------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# ------------------ Lifespan (Startup/Shutdown) ------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 App starting...")
    yield
    logger.info("🛑 App shutting down...")

app = FastAPI(
    title="Luviio Enterprise",
    version="1.0.0",
    lifespan=lifespan,
)

# ------------------ Static Files (Conditional Mount) ------------------
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATIC_DIR = os.path.join(BASE_DIR, "static")
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")

if os.path.exists(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
else:
    logger.warning("Static directory not found – skipping mount.")

# ------------------ Templates with Absolute Path ------------------
templates = Jinja2Templates(directory=TEMPLATES_DIR)
templates.env.enable_async = True

# ------------------ Middleware: Request ID & Logging ------------------
class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id
        logger.info(f"Req {request_id}: {request.method} {request.url.path}")
        response = await call_next(request)
        logger.info(f"Req {request_id} completed: {response.status_code}")
        return response

app.add_middleware(RequestLoggingMiddleware)

# ------------------ Security Headers Middleware ------------------
class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' https://unpkg.com https://cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline' https://unpkg.com https://cdn.tailwindcss.com;"
        )
        return response

app.add_middleware(SecurityHeadersMiddleware)

# ------------------ Global Exception Handler ------------------
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled error: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error", "request_id": request.state.request_id}
    )

# ------------------ Pydantic Model for UI State ------------------
class UIState(BaseModel):
    page_title: str
    nav_items: List[Dict[str, Any]]
    sidebar_categories: List[Dict[str, Any]]
    featured_material: Optional[Dict[str, Any]] = None
    user_status: str = "Studio Access"
    server_time: str = datetime.now().strftime("%H:%M:%S")
    footer_sections: List[Dict[str, Any]] = []

# ------------------ Debug Endpoint (Temporary) ------------------
@app.get("/debug-templates")
async def debug_templates():
    """Check which template files are actually deployed"""
    file_list = []
    for root, dirs, files in os.walk(TEMPLATES_DIR):
        for file in files:
            rel_path = os.path.relpath(os.path.join(root, file), TEMPLATES_DIR)
            file_list.append(rel_path)
    return {
        "templates_root": TEMPLATES_DIR,
        "files": file_list,
        "exists": os.path.exists(TEMPLATES_DIR)
    }

# ------------------ Home Route ------------------
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    state = UIState(
        page_title="Home | Luviio",
        nav_items=[
            {"label": "The Studio", "url": "/studio", "active": True},
            {"label": "Materials", "url": "/materials", "active": False}
        ],
        sidebar_categories=[
            {"label": "Ceramics", "url": "/ceramics"},
            {"label": "Water Systems", "url": "/water"}
        ],
        featured_material={
            "name": "Arctic Matte Stone",
            "url": "/materials/arctic-stone"
        },
        footer_sections=[
            {
                "title": "Resources",
                "links": [{"label": "Gallery", "url": "/gallery"}]
            }
        ]
    )
    
    # Try multiple possible template paths
    possible_paths = [
        "app/pages/index.html",
        "pages/index.html", 
        "index.html"
    ]
    
    for template_path in possible_paths:
        try:
            return templates.TemplateResponse(
                template_path, 
                {"request": request, "state": state.model_dump()}
            )
        except:
            continue
    
    # Agar koi bhi path kaam na kare to error do
    return JSONResponse(
        status_code=500,
        content={
            "error": "Template not found",
            "tried_paths": possible_paths,
            "debug_endpoint": "/debug-templates"
        }
    )
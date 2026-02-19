import os
import logging
import uuid
from datetime import datetime
from typing import Optional, List, Dict, Any
from contextlib import asynccontextmanager
import glob

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.middleware.base import BaseHTTPMiddleware

# ------------------ Logging ------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# ------------------ Lifespan ------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 App starting...")
    yield
    logger.info("🛑 App shutting down...")

app = FastAPI(title="Luviio Enterprise", version="1.0.0", lifespan=lifespan)

# ------------------ Paths ------------------
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATIC_DIR = os.path.join(BASE_DIR, "static")
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")

# ------------------ Static Files ------------------
if os.path.exists(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    logger.info("✅ Static directory mounted")
else:
    logger.warning("⚠️ Static directory not found – skipping mount.")

# ------------------ Templates ------------------
templates = Jinja2Templates(directory=TEMPLATES_DIR)
templates.env.enable_async = True
logger.info(f"📁 Templates directory: {TEMPLATES_DIR}")

# ------------------ Middleware ------------------
class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id
        logger.info(f"Req {request_id}: {request.method} {request.url.path}")
        response = await call_next(request)
        logger.info(f"Req {request_id} completed: {response.status_code}")
        return response

app.add_middleware(RequestLoggingMiddleware)

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

# ------------------ Exception Handler ------------------
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled error: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error", "request_id": request.state.request_id}
    )

# ------------------ UI State Model ------------------
class UIState(BaseModel):
    page_title: str
    nav_items: List[Dict[str, Any]]
    sidebar_categories: List[Dict[str, Any]]
    featured_material: Optional[Dict[str, Any]] = None
    user_status: str = "Studio Access"
    server_time: str = datetime.now().strftime("%H:%M:%S")
    footer_sections: List[Dict[str, Any]] = []

# ------------------ Debug Templates Endpoint ------------------
@app.get("/debug")
async def debug_templates():
    """See all available templates"""
    files = []
    for root, dirs, filenames in os.walk(TEMPLATES_DIR):
        for f in filenames:
            if f.endswith('.html'):
                rel = os.path.relpath(os.path.join(root, f), TEMPLATES_DIR)
                files.append(rel)
    
    return {
        "templates_dir_exists": os.path.exists(TEMPLATES_DIR),
        "templates_dir": TEMPLATES_DIR,
        "files": files,
        "static_dir_exists": os.path.exists(STATIC_DIR)
    }

# ------------------ HOME ROUTE - FULLY AUTOMATIC ------------------
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    # State data
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
    
    # FIRST: Try to find ANY index.html file in templates
    try:
        for root, dirs, files in os.walk(TEMPLATES_DIR):
            for file in files:
                if file == "index.html":
                    rel_path = os.path.relpath(os.path.join(root, file), TEMPLATES_DIR)
                    logger.info(f"✅ Found index.html at: {rel_path}")
                    return templates.TemplateResponse(
                        rel_path,
                        {"request": request, "state": state.model_dump()}
                    )
    except Exception as e:
        logger.error(f"Error scanning templates: {e}")
    
    # SECOND: Try common paths
    common_paths = [
        "index.html",
        "pages/index.html",
        "app/pages/index.html",
        "home.html",
        "pages/home.html"
    ]
    
    for path in common_paths:
        try:
            return templates.TemplateResponse(
                path,
                {"request": request, "state": state.model_dump()}
            )
        except:
            continue
    
    # LAST: If nothing works, show debug info
    return HTMLResponse(
        content=f"""
        <html>
            <head><title>Setup Required</title></head>
            <body style="font-family: sans-serif; padding: 2rem;">
                <h1>🔧 Template Not Found</h1>
                <p>Please check your template structure.</p>
                <h2>Debug Info:</h2>
                <ul>
                    <li>Templates directory: <code>{TEMPLATES_DIR}</code></li>
                    <li>Directory exists: <code>{os.path.exists(TEMPLATES_DIR)}</code></li>
                </ul>
                <p>👉 Visit <a href="/debug">/debug</a> to see available templates</p>
                <p>👉 Make sure your templates are in the correct folder:</p>
                <pre>
project-root/
├── api/
│   └── main.py
├── templates/
│   ├── base.html
│   ├── index.html  (or app/pages/index.html)
│   └── macros/
                </pre>
            </body>
        </html>
        """,
        status_code=200
    )
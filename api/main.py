import logging
import os
from datetime import datetime
from typing import List, Dict, Any, Optional

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

# --- STEP 1: BEAST LEVEL LOGGING ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s"
)
logger = logging.getLogger("LuviioSystem")

app = FastAPI(
    title="Luviio.in | Cinematic Bath Architecture",
    version="3.1.2", # Jinja 3.1.2 / SPA Optimized
)

# --- STEP 2: STRICT PATH ARCHITECTURE ---
# BASE_DIR should point to the 'api' folder
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_DIR = os.path.join(BASE_DIR, "templates")
STATIC_DIR = os.path.join(BASE_DIR, "static")

# BEAST CHECK: Startup Diagnostic for SPA Assets
# Ensures /api/static/css/main.css is reachable
css_diagnostic_path = os.path.join(STATIC_DIR, "css", "main.css")
if os.path.exists(css_diagnostic_path):
    logger.info(f">>> [CONNECTED] SPA Core Asset Found: {css_diagnostic_path}")
else:
    logger.warning(f">>> [WARNING] SPA Core Asset Missing at: {css_diagnostic_path}")

# Jinja2 Setup with Async support
templates = Jinja2Templates(directory=TEMPLATE_DIR)
templates.env.enable_async = True 

# --- STEP 3: STATE MODELS (Strictly Typed) ---
class NavItem(BaseModel):
    label: str
    url: str
    active: bool = False

class SidebarCategory(BaseModel):
    label: str
    url: str

class FooterSection(BaseModel):
    title: str
    links: List[Dict[str, str]]

class UIState(BaseModel):
    """The complete State-Driven UI Schema for SPA"""
    page_title: str
    user_status: str = "Studio Access"
    nav_items: List[NavItem]
    sidebar_categories: List[SidebarCategory]
    footer_sections: List[FooterSection]
    featured_material: Optional[Dict[str, str]] = None
    server_time: str = datetime.now().strftime("%H:%M:%S")

# --- STEP 4: GLOBAL ASSET MOUNTING ---
# Naming it 'static' allows url_for('static', filename='css/main.css')
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# --- STEP 5: JINJA GLOBALS ---
templates.env.globals.update(now=datetime.now)

# --- STEP 6: ADVANCED EXCEPTION HANDLING ---
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"SPA Glitch: {str(exc)}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "error": "Connectivity Issue",
            "detail": str(exc),
            "path_searched": TEMPLATE_DIR,
            "hint": "Ensure macro imports in index.html match the new directory structure."
        }
    )

# --- STEP 7: SPA ROUTE HANDLING (STATE-DRIVEN) ---
@app.get("/", response_class=HTMLResponse)
async def home_route(request: Request):
    """
    Landing Page: High-End SPA Experience.
    Notice: Returning full state for dynamic UI components.
    """
    try:
        # Constructing the State Object
        state = UIState(
            page_title="Home | Luviio Luxury Bath",
            nav_items=[
                NavItem(label="The Studio", url="/studio", active=True),
                NavItem(label="Materials", url="/materials"),
                NavItem(label="Bespoke", url="/bespoke"),
            ],
            sidebar_categories=[
                SidebarCategory(label="Ceramics", url="/collections/ceramics"),
                SidebarCategory(label="Water Systems", url="/collections/water"),
            ],
            footer_sections=[
                {
                    "title": "Experience",
                    "links": [{"label": "Gallery", "url": "/gallery"}, {"label": "Process", "url": "/process"}]
                }
            ],
            featured_material={"name": "Arctic Matte Stone", "url": "/materials/arctic-stone"}
        )

        logger.info(f">>> Serving Index via SPA Engine: {state.page_title}")
        
        # Support for both Pydantic v1 (dict) and v2 (model_dump)
        state_data = state.model_dump() if hasattr(state, 'model_dump') else state.dict()

        return templates.TemplateResponse(
            "app/pages/index.html", 
            {
                "request": request,
                "state": state_data
            }
        )
    except Exception as e:
        raise e

@app.get("/docs", response_class=HTMLResponse)
async def documentation_route(request: Request):
    try:
        return templates.TemplateResponse("app/pages/docss.html", {"request": request})
    except Exception:
        raise HTTPException(status_code=404, detail="SPA Documentation not found.")

# --- STEP 10: SERVING ---
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
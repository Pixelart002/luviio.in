import logging
import os
from datetime import datetime
from typing import List, Dict, Any, Optional

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

# --- STEP 1: BEAST LOGGING & CONFIG ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s"
)
logger = logging.getLogger("LuviioSystem")

app = FastAPI(
    title="Luviio.in | Cinematic Bath Architecture",
    version="3.1.2", # Strictly Jinja 3.1.2 compatible
)

# --- STEP 2: STRICT PATH ARCHITECTURE ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_DIR = os.path.join(BASE_DIR, "templates")
STATIC_DIR = os.path.join(BASE_DIR, "static")

# Jinja2 Setup with Async support for extreme speed
templates = Jinja2Templates(directory=TEMPLATE_DIR)
templates.env.enable_async = True 

# --- STEP 3: STATE MODELS (The Foundation) ---
# Ensuring UI doesn't break due to missing data keys
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
    """The complete State-Driven UI Schema"""
    page_title: str
    user_status: str = "Studio Access"
    nav_items: List[NavItem]
    sidebar_categories: List[SidebarCategory]
    footer_sections: List[FooterSection]
    featured_material: Optional[Dict[str, str]] = None
    server_time: str = datetime.now().strftime("%H:%M:%S")

# --- STEP 4: GLOBAL ASSET MOUNTING ---
# Resolves the "No route exists for name 'static'" error
if os.path.exists(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    logger.info(">>> [CONNECTED] Static Assets Mounted Successfully.")
else:
    logger.error(">>> [CRITICAL] Static Directory Missing. Assets will fail.")

# --- STEP 5: BEAST LOGIC INJECTION (Jinja Globals) ---
templates.env.globals.update(now=datetime.now)

# --- STEP 6: ADVANCED EXCEPTION HANDLING ---
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"System Glitch: {str(exc)}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "error": "Connectivity Issue",
            "detail": str(exc),
            "path_searched": TEMPLATE_DIR,
            "hint": "Check if Macro paths are correct in Index.html"
        }
    )

# --- STEP 7: STATE-DRIVEN ROUTE HANDLING ---
@app.get("/", response_class=HTMLResponse)
async def home_route(request: Request):
    """
    Landing Page: High-End Cinematic Experience.
    Strictly State-Driven.
    """
    try:
        # Constructing the 'Beast' State
        state = UIState(
            page_title="Home | Luviio Luxury Bath",
            user_status="Exclusive Studio Access",
            nav_items=[
                NavItem(label="The Studio", url="/studio", active=True),
                NavItem(label="Materials", url="/materials"),
                NavItem(label="Bespoke", url="/bespoke"),
            ],
            sidebar_categories=[
                SidebarCategory(label="Ceramics", url="/collections/ceramics"),
                SidebarCategory(label="Water Systems", url="/collections/water"),
                SidebarCategory(label="Natural Stone", url="/collections/stone"),
            ],
            footer_sections=[
                {
                    "title": "Experience",
                    "links": [{"label": "Gallery", "url": "/gallery"}, {"label": "Process", "url": "/process"}]
                },
                {
                    "title": "Studio",
                    "links": [{"label": "Contact", "url": "/contact"}, {"label": "Privacy", "url": "/privacy"}]
                }
            ],
            featured_material={"name": "Arctic Matte Stone", "url": "/materials/arctic-stone"}
        )

        logger.info(f">>> Serving Index with State: {state.page_title}")
        
        return templates.TemplateResponse(
            "app/pages/index.html", 
            {
                "request": request,
                "state": state.dict() # Passing raw dict to Jinja
            }
        )
    except Exception as e:
        # This will be caught by the global exception handler
        raise e

@app.get("/docs", response_class=HTMLResponse)
async def documentation_route(request: Request):
    """Clean technical documentation route."""
    try:
        return templates.TemplateResponse("app/pages/docss.html", {"request": request})
    except Exception:
        raise HTTPException(status_code=404, detail="Documentation file not found.")

# --- STEP 10: SERVING CHECK ---
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
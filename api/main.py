import os
from datetime import datetime
from typing import List, Dict, Any, Optional
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_DIR = os.path.join(BASE_DIR, "templates")

app = FastAPI(title="Luviio.in | Vercel Optimized")
templates = Jinja2Templates(directory=TEMPLATE_DIR)

class UIState(BaseModel):
    page_title: str
    nav_items: List[Dict[str, Any]]
    sidebar_categories: List[Dict[str, Any]]
    footer_sections: List[Dict[str, Any]]
    featured_material: Optional[Dict[str, Any]] = None
    user_status: str = "Studio Access"

# Helper function to get state
def get_ui_state():
    return UIState(
        page_title="Home | Luviio Luxury Studio",
        nav_items=[
            {"label": "The Studio", "url": "/studio", "active": True},
            {"label": "Materials", "url": "/materials", "active": False}
        ],
        sidebar_categories=[
            {"label": "Ceramics", "url": "/ceramics"},
            {"label": "Water Systems", "url": "/water"}
        ],
        featured_material={"name": "Arctic Matte Stone", "url": "/materials/arctic-stone"},
        footer_sections=[{"title": "Resources", "links": [{"label": "Gallery", "url": "/gallery"}]}]
    )

@app.get("/", response_class=HTMLResponse)
async def home_route(request: Request):
    # Main page render
    return templates.TemplateResponse(
        "app/pages/index.html", 
        {"request": request, "state": get_ui_state().model_dump()}
    )

# NEW: Dedicated Drawer Route
@app.get("/drawer", response_class=HTMLResponse)
async def drawer_route(request: Request):
    return templates.TemplateResponse(
        "app/macros/index_page/drawer.html", 
        {"request": request, "state": get_ui_state().model_dump()}
    )
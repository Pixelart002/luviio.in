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
    state = get_ui_state()

    # FastAPI headers are case-insensitive, so we use 'x-up-target'
    target = request.headers.get("x-up-target")

    # UNPOLY 3.0 LOGIC: Catch exact target requested by the frontend
    if target == "#drawer-content":
        response = templates.TemplateResponse(
            "macros/index_page/drawer.html", 
            {"request": request, "state": state.model_dump()}
        )
        # CRITICAL FIX FOR UNPOLY 3.0 CACHING
        # This tells the browser NOT to cache the drawer as the full page
        response.headers["Vary"] = "X-Up-Target"
        return response
    
    # Default: Return the full page
    return templates.TemplateResponse(
        "app/pages/index.html", 
        {"request": request, "state": state.model_dump()}
    )
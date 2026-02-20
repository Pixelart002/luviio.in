import os
from datetime import datetime
from typing import List, Dict, Any, Optional

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_DIR = os.path.join(BASE_DIR, "templates")

app = FastAPI(title="Luviio.in")
templates = Jinja2Templates(directory=TEMPLATE_DIR)

# --- Helper Function for State ---
def get_base_state():
    """Returns complete state dictionary with all required fields"""
    return {
        "page_title": "Home | Luviio Luxury Studio",
        "nav_items": [
            {"label": "The Studio", "url": "/studio", "active": True},
            {"label": "Materials", "url": "/materials", "active": False},
            {"label": "Projects", "url": "/projects", "active": False},
            {"label": "Journal", "url": "/journal", "active": False}
        ],
        "sidebar_categories": [
            {"label": "Ceramics", "url": "/ceramics"},
            {"label": "Water Systems", "url": "/water"},
            {"label": "Stone Collection", "url": "/stone"},
            {"label": "Bath Fixtures", "url": "/fixtures"}
        ],
        "footer_sections": [
            {
                "title": "Studio",
                "links": [
                    {"label": "About", "url": "/about"},
                    {"label": "Philosophy", "url": "/philosophy"},
                    {"label": "Team", "url": "/team"}
                ]
            },
            {
                "title": "Collections",
                "links": [
                    {"label": "Ceramics", "url": "/ceramics"},
                    {"label": "Water", "url": "/water"},
                    {"label": "Stone", "url": "/stone"}
                ]
            },
            {
                "title": "Connect",
                "links": [
                    {"label": "Instagram", "url": "https://instagram.com/luviio"},
                    {"label": "LinkedIn", "url": "https://linkedin.com/company/luviio"},
                    {"label": "Contact", "url": "/contact"}
                ]
            }
        ],
        "featured_material": {
            "name": "Arctic Matte Stone",
            "url": "/materials/arctic-stone"
        },
        "user_status": "Studio Access",
        "footer_about": "Architecture for the most private spaces of your life.",
        "server_time": datetime.now().strftime("%H:%M:%S")
    }

# --- Routes ---
@app.get("/", response_class=HTMLResponse)
async def home_route(request: Request):
    """Home page"""
    try:
        state = get_base_state()
        return templates.TemplateResponse(
            "app/pages/index.html", 
            {"request": request, "state": state}
        )
    except Exception as e:
        # Fallback state
        fallback_state = {
            "nav_items": [{"label": "Home", "url": "/", "active": True}],
            "sidebar_categories": [],
            "footer_sections": [],
            "user_status": "Studio Access",
            "footer_about": "Luviio Studio",
            "page_title": "Luviio"
        }
        return templates.TemplateResponse(
            "app/pages/index.html",
            {"request": request, "state": fallback_state}
        )

@app.get("/drawer-content", response_class=HTMLResponse)
async def drawer_content(request: Request):
    """Drawer content for Unpoly layer"""
    state = get_base_state()
    return templates.TemplateResponse(
        "app/partials/drawer_content.html",
        {"request": request, "state": state}
    )

@app.get("/health")
async def health_check():
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}

# For local development
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
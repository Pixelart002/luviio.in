import os
from datetime import datetime
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_DIR = os.path.join(BASE_DIR, "templates")

app = FastAPI(title="Luviio.in")
templates = Jinja2Templates(directory=TEMPLATE_DIR)

def get_base_state():
    """Centralised state – all data for the whole site"""
    return {
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
        "footer_about": "Architecture for the most private spaces of your life."
    }

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    state = get_base_state()
    return templates.TemplateResponse(
        "app/pages/index.html",
        {"request": request, "state": state}
    )

# Optional health check (for Vercel)
@app.get("/health")
async def health():
    return {"status": "ok", "time": datetime.now().isoformat()}
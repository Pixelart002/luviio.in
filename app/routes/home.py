from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse
from app.core.config import settings
from app.db.client import get_db
from app.models.ui_state import UIState

router = APIRouter()

@router.get("/", response_class=HTMLResponse)
async def home(request: Request, db=Depends(get_db)):
    # Build state from database
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
        featured_materials=[],  # populate from DB
        footer_sections=[
            {
                "title": "Resources",
                "links": [{"label": "Gallery", "url": "/gallery"}]
            }
        ],
        user_status="Studio Access"
    )
    return request.state.templates.TemplateResponse(
        "app/pages/index.html",
        {"request": request, "state": state.dict()}
    )
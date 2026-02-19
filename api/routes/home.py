from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from api.services.data_fetcher import fetch_ui_state
from api.templates import templates   # we'll set this in main.py

router = APIRouter()

@router.get("/", response_class=HTMLResponse)
async def home_page(request: Request):
    # Fetch state from Supabase
    state = await fetch_ui_state(page_name="home")
    return templates.TemplateResponse(
        "app/pages/index.html",
        {"request": request, "state": state.model_dump()}
    )
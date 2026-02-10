from fastapi import APIRouter, Request, Header
from fastapi.responses import HTMLResponse

router = APIRouter()

@router.get("/", response_class=HTMLResponse)
async def render_home(request: Request, x_up_target: str = Header(None)):
    templates = request.app.state.templates
    
    return templates.TemplateResponse("app/pages/home.html", {
        "request": request,
        "title": "Luviio - The Trust Layer for Marketplaces",
        "description": "Verified operating system for online listings.",
        "active_page": "home",
        "up_fragment": x_up_target is not None
    })